"""
High-Performance SQLite Manager - PRODUCTION VERSION
Uses BotConfig for all settings, emits events, database-only configuration
"""

import aiosqlite
import asyncio
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from config import BotConfig
from events import get_event_bus, EventType

logger = logging.getLogger(__name__)

class SQLiteManager:
    def __init__(self, config: BotConfig):
        self.config = config
        self.db_path = config.DATABASE_PATH
        self._pool_size = config.DB_POOL_SIZE
        self._available_connections = asyncio.Queue(maxsize=self._pool_size)
        self._initialized = False
        self._lock = asyncio.Lock()
        self.event_bus = get_event_bus()
        
    async def initialize(self):
        """Initialize database with optimizations for high performance"""
        async with self._lock:
            if self._initialized:
                return
        
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                
                # Test database access first
                async with aiosqlite.connect(self.db_path) as test_conn:
                    await test_conn.execute("SELECT 1")
                    logger.info("✅ Database file accessible")
                
                # Create connection pool
                self._initialized = True
                
                for i in range(self._pool_size):
                    conn = await aiosqlite.connect(self.db_path)
                    await self._configure_connection(conn)
                    await self._available_connections.put(conn)
                
                # Initialize schema with a separate connection
                async with self._get_connection() as conn:
                    await self._create_schema(conn)
                
                logger.info(f"✅ SQLite initialized: {self.db_path} (pool size: {self._pool_size})")
                
                # Emit startup event
                await self.event_bus.emit(EventType.SYSTEM_STARTUP, {
                    'component': 'database',
                    'pool_size': self._pool_size,
                    'db_path': self.db_path
                }, source='sqlite_manager')
                
            except Exception as e:
                self._initialized = False
                logger.error(f"❌ Database initialization failed: {e}")
                await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                    'component': 'database',
                    'error': str(e),
                    'operation': 'initialize'
                }, source='sqlite_manager')
                raise
    
    async def _configure_connection(self, conn):
        """Configure connection for maximum performance"""
        try:
            # Performance optimizations using config values
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute(f"PRAGMA cache_size={self.config.CACHE_SIZE}")
            await conn.execute("PRAGMA temp_store=memory")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA wal_autocheckpoint=1000")
            await conn.execute(f"PRAGMA busy_timeout={self.config.DB_BUSY_TIMEOUT}")
            
        except Exception as e:
            logger.error(f"Error configuring connection: {e}")
            raise
        
    async def _create_schema(self, conn):
        """Create optimized database schema with enhanced channel support"""
        
        try:
            # Create monitored_channels table (current enhanced format)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS monitored_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    username TEXT,
                    type TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    added_at TEXT DEFAULT (datetime('now')),
                    last_updated TEXT DEFAULT (datetime('now')),
                    UNIQUE(chat_id, type)
                )
            """)
            await self._create_channel_indexes(conn)
            
            # Users table with language support
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT DEFAULT (datetime('now')),
                    last_active TEXT DEFAULT (datetime('now')),
                    total_forwards INTEGER DEFAULT 0,
                    daily_forwards INTEGER DEFAULT 0,
                    last_forward_date TEXT DEFAULT (date('now')),
                    language TEXT DEFAULT ?
                )
            """, (self.config.DEFAULT_LANGUAGE,))
            
            # Add new columns to existing users table (safe migrations)
            try:
                await conn.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT ?", (self.config.DEFAULT_LANGUAGE,))
            except Exception:
                pass  # Column already exists
            
            try:
                await conn.execute("ALTER TABLE users ADD COLUMN daily_forwards INTEGER DEFAULT 0")
            except Exception:
                pass
                
            try:
                await conn.execute("ALTER TABLE users ADD COLUMN last_forward_date TEXT DEFAULT (date('now'))")
            except Exception:
                pass
            
            # User keywords
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    keyword TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    UNIQUE(user_id, keyword)
                )
            """)
            
            # User ignore keywords
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_ignore_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    keyword TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    UNIQUE(user_id, keyword)
                )
            """)
            
            # Message forwards for analytics
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS message_forwards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    keywords_matched TEXT,
                    forwarded_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    UNIQUE(user_id, channel_id, message_id)
                )
            """)
            
            # Performance indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_user_keywords_user_id ON user_keywords(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_user_keywords_lookup ON user_keywords(user_id, keyword)",
                "CREATE INDEX IF NOT EXISTS idx_user_ignore_keywords_user_id ON user_ignore_keywords(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_message_forwards_user_id ON message_forwards(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_message_forwards_dedup ON message_forwards(user_id, channel_id, message_id)",
                "CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)",
                "CREATE INDEX IF NOT EXISTS idx_message_forwards_forwarded_at ON message_forwards(forwarded_at)",
                "CREATE INDEX IF NOT EXISTS idx_users_language ON users(language)",
                "CREATE INDEX IF NOT EXISTS idx_users_daily_forwards ON users(daily_forwards, last_forward_date)"
            ]
            
            for index in indexes:
                try:
                    await conn.execute(index)
                except Exception as e:
                    logger.debug(f"Index creation warning: {e}")
            
            await conn.commit()
            logger.info("✅ Database schema created/updated")
            
        except Exception as e:
            logger.error(f"❌ Schema creation failed: {e}")
            await conn.rollback()
            raise

    async def _create_channel_indexes(self, conn):
        """Create indexes for channels table"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_monitored_channels_chat_id ON monitored_channels(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_monitored_channels_username ON monitored_channels(username)",
            "CREATE INDEX IF NOT EXISTS idx_monitored_channels_type_status ON monitored_channels(type, status)",
            "CREATE INDEX IF NOT EXISTS idx_monitored_channels_type ON monitored_channels(type)"
        ]
        for index in indexes:
            try:
                await conn.execute(index)
            except Exception as e:
                logger.debug(f"Index creation warning: {e}")
    
    def _get_connection(self):
        """Get database connection from pool"""
        if not self._initialized:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return ConnectionContext(self._available_connections, self.config.CONNECTION_POOL_TIMEOUT)
    
    async def close(self):
        """Close all connections"""
        async with self._lock:
            try:
                connections_closed = 0
                while not self._available_connections.empty():
                    try:
                        conn = await asyncio.wait_for(self._available_connections.get(), timeout=1.0)
                        await conn.close()
                        connections_closed += 1
                    except asyncio.TimeoutError:
                        break
                    except Exception as e:
                        logger.error(f"Error closing connection: {e}")
                
                self._initialized = False
                logger.info(f"✅ SQLite connections closed ({connections_closed} connections)")
                
                await self.event_bus.emit(EventType.SYSTEM_SHUTDOWN, {
                    'component': 'database',
                    'connections_closed': connections_closed
                }, source='sqlite_manager')
                
            except Exception as e:
                logger.error(f"Error during database close: {e}")
    
    # Enhanced Channel Management Methods
    
    async def add_channel_simple(self, chat_id: int, username: str = None, channel_type: str = 'bot') -> bool:
        """Add channel with chat_id and optional username"""
        try:
            async with self._get_connection() as conn:
                await conn.execute("""
                    INSERT INTO monitored_channels (chat_id, username, type, last_updated)
                    VALUES (?, ?, ?, datetime('now'))
                """, (chat_id, username, channel_type))
                await conn.commit()
                logger.info(f"✅ Added {channel_type} channel: {username or chat_id}")
                
                # Emit event
                await self.event_bus.emit(EventType.CHANNEL_ADDED, {
                    'chat_id': chat_id,
                    'username': username,
                    'type': channel_type
                }, source='sqlite_manager')
                
                return True
        except aiosqlite.IntegrityError:
            logger.warning(f"Channel already exists: {username or chat_id}")
            return False
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            return False

    async def update_channel_username(self, chat_id: int, username: str) -> bool:
        """Update channel username when it changes"""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("""
                    UPDATE monitored_channels 
                    SET username = ?, last_updated = datetime('now')
                    WHERE chat_id = ?
                """, (username, chat_id))
                await conn.commit()
                success = cursor.rowcount > 0
                if success:
                    logger.info(f"✅ Updated channel username: {chat_id} -> {username}")
                return success
        except Exception as e:
            logger.error(f"Error updating channel username: {e}")
            return False

    async def get_channel_display_name(self, chat_id: int) -> str:
        """Get display name for channel (username or chat_id)"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT username FROM monitored_channels WHERE chat_id = ?", (chat_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        return row[0]  # Return @username
                    return f"Channel {chat_id}"  # Fallback to chat_id
        except Exception as e:
            logger.error(f"Error getting channel display name: {e}")
            return f"Channel {chat_id}"

    async def remove_channel_simple(self, chat_id: int, channel_type: str) -> bool:
        """Remove channel by chat_id"""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM monitored_channels WHERE chat_id = ? AND type = ?",
                    (chat_id, channel_type)
                )
                await conn.commit()
                success = cursor.rowcount > 0
                if success:
                    logger.info(f"✅ Removed {channel_type} channel: {chat_id}")
                    
                    # Emit event
                    await self.event_bus.emit(EventType.CHANNEL_REMOVED, {
                        'chat_id': chat_id,
                        'type': channel_type
                    }, source='sqlite_manager')
                    
                return success
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            return False

    async def get_simple_bot_channels(self) -> List[int]:
        """Get bot channel chat_ids"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT chat_id FROM monitored_channels WHERE type = 'bot' AND status = 'active'"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error getting bot channels: {e}")
            return []

    async def get_simple_user_channels(self) -> List[int]:
        """Get user channel chat_ids"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT chat_id FROM monitored_channels WHERE type = 'user' AND status = 'active'"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error getting user channels: {e}")
            return []

    async def get_all_channels_with_usernames(self) -> dict:
        """Get all channels with their usernames for display"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute("""
                    SELECT chat_id, username, type 
                    FROM monitored_channels 
                    WHERE status = 'active'
                    ORDER BY type, username
                """) as cursor:
                    rows = await cursor.fetchall()
                    
                    result = {}
                    for chat_id, username, channel_type in rows:
                        display_name = username if username else f"Channel {chat_id}"
                        result[chat_id] = {
                            'display_name': display_name,
                            'username': username,
                            'type': channel_type
                        }
                    
                    return result
        except Exception as e:
            logger.error(f"Error getting channels with usernames: {e}")
            return {}

    # User management methods with config integration
    async def ensure_user_exists(self, user_id: int, language: str = None):
        """Ensure user exists in database with language preference"""
        try:
            if language is None:
                language = self.config.DEFAULT_LANGUAGE
                
            async with self._get_connection() as conn:
                # Check if user exists
                async with conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cursor:
                    exists = await cursor.fetchone()
                
                if not exists:
                    # Create new user
                    await conn.execute("""
                        INSERT INTO users (id, last_active, language) 
                        VALUES (?, datetime('now'), ?)
                    """, (user_id, language))
                    
                    # Emit user registered event
                    await self.event_bus.emit(EventType.USER_REGISTERED, {
                        'user_id': user_id,
                        'language': language
                    }, source='sqlite_manager')
                else:
                    # Update last active
                    await conn.execute("""
                        UPDATE users SET last_active = datetime('now') 
                        WHERE id = ?
                    """, (user_id,))
                
                await conn.commit()
        except Exception as e:
            logger.error(f"Error ensuring user exists: {e}")
    
    async def set_user_keywords(self, user_id: int, keywords: List[str]):
        """Set keywords for a specific user (replaces all existing)"""
        # Validate keyword limits
        if len(keywords) > self.config.MAX_KEYWORDS_PER_USER:
            raise ValueError(f"Too many keywords. Maximum allowed: {self.config.MAX_KEYWORDS_PER_USER}")
        
        # Validate keyword length
        for keyword in keywords:
            if len(keyword) > self.config.MAX_KEYWORD_LENGTH:
                raise ValueError(f"Keyword too long: {keyword}. Maximum length: {self.config.MAX_KEYWORD_LENGTH}")
        
        try:
            await self.ensure_user_exists(user_id)
            
            async with self._get_connection() as conn:
                await conn.execute("BEGIN TRANSACTION")
                try:
                    await conn.execute("DELETE FROM user_keywords WHERE user_id = ?", (user_id,))
                    if keywords:
                        await conn.executemany(
                            "INSERT INTO user_keywords (user_id, keyword) VALUES (?, ?)",
                            [(user_id, keyword.lower()) for keyword in keywords]
                        )
                    await conn.commit()
                    logger.info(f"✅ Set {len(keywords)} keywords for user {user_id}")
                    
                    # Emit event
                    await self.event_bus.emit(EventType.USER_KEYWORDS_UPDATED, {
                        'user_id': user_id,
                        'keywords': keywords,
                        'keyword_count': len(keywords)
                    }, source='sqlite_manager')
                    
                except Exception:
                    await conn.rollback()
                    raise
        except Exception as e:
            logger.error(f"Error setting user keywords: {e}")
            raise
    
    async def set_user_ignore_keywords(self, user_id: int, keywords: List[str]):
        """Set ignore keywords for a specific user"""
        # Validate ignore keyword limits
        if len(keywords) > self.config.MAX_IGNORE_KEYWORDS:
            raise ValueError(f"Too many ignore keywords. Maximum allowed: {self.config.MAX_IGNORE_KEYWORDS}")
        
        try:
            await self.ensure_user_exists(user_id)
            
            async with self._get_connection() as conn:
                await conn.execute("BEGIN TRANSACTION")
                try:
                    await conn.execute("DELETE FROM user_ignore_keywords WHERE user_id = ?", (user_id,))
                    if keywords:
                        await conn.executemany(
                            "INSERT INTO user_ignore_keywords (user_id, keyword) VALUES (?, ?)",
                            [(user_id, keyword.lower()) for keyword in keywords]
                        )
                    await conn.commit()
                    logger.info(f"✅ Set {len(keywords)} ignore keywords for user {user_id}")
                except Exception:
                    await conn.rollback()
                    raise
        except Exception as e:
            logger.error(f"Error setting user ignore keywords: {e}")
            raise
    
    async def check_user_limit(self, user_id: int) -> bool:
        """Check if user has reached daily limit"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute("""
                    SELECT daily_forwards, last_forward_date 
                    FROM users WHERE id = ?
                """, (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    
                    if not row:
                        return True  # New user, allow
                    
                    daily_forwards, last_date = row
                    today = datetime.now().date().isoformat()
                    
                    # Reset counter if new day
                    if last_date != today:
                        await conn.execute("""
                            UPDATE users 
                            SET daily_forwards = 0, last_forward_date = ? 
                            WHERE id = ?
                        """, (today, user_id))
                        await conn.commit()
                        return True
                    
                    # Check limit
                    return daily_forwards < self.config.MAX_DAILY_FORWARDS_PER_USER
                    
        except Exception as e:
            logger.error(f"Error checking user limit: {e}")
            return True  # On error, allow (fail open)
    
    async def log_message_forward(self, user_id: int, channel_id: int, message_id: int, 
                                keywords_matched: List[str] = None):
        """Log a forwarded message with enhanced tracking"""
        try:
            keywords_str = ",".join(keywords_matched) if keywords_matched else ""
            
            async with self._get_connection() as conn:
                await conn.execute("BEGIN TRANSACTION")
                try:
                    await conn.execute(
                        "INSERT INTO message_forwards (user_id, channel_id, message_id, keywords_matched) VALUES (?, ?, ?, ?)",
                        (user_id, channel_id, message_id, keywords_str)
                    )
                    await conn.execute(
                        "UPDATE users SET total_forwards = total_forwards + 1, daily_forwards = daily_forwards + 1, last_forward_date = date('now') WHERE id = ?",
                        (user_id,)
                    )
                    await conn.commit()
                    
                    # Emit event
                    await self.event_bus.emit(EventType.JOB_MESSAGE_FORWARDED, {
                        'user_id': user_id,
                        'channel_id': channel_id,
                        'message_id': message_id,
                        'keywords_matched': keywords_matched or []
                    }, source='sqlite_manager')
                    
                except aiosqlite.IntegrityError:
                    # Duplicate forward - ignore
                    await conn.rollback()
                except Exception:
                    await conn.rollback()
                    raise
        except Exception as e:
            logger.error(f"Error logging message forward: {e}")
    
    # Language support methods
    async def get_user_language(self, user_id: int) -> str:
        """Get user's preferred language"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT language FROM users WHERE id = ?", (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row[0] or self.config.DEFAULT_LANGUAGE
                    else:
                        # Create user with default language
                        await self.ensure_user_exists(user_id)
                        return self.config.DEFAULT_LANGUAGE
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            return self.config.DEFAULT_LANGUAGE

    async def set_user_language(self, user_id: int, language: str):
        """Set user's preferred language"""
        try:
            await self.ensure_user_exists(user_id)
            async with self._get_connection() as conn:
                await conn.execute(
                    "UPDATE users SET language = ?, last_active = datetime('now') WHERE id = ?",
                    (language, user_id)
                )
                await conn.commit()
                logger.info(f"✅ Set user {user_id} language to {language}")
                
                # Emit event
                await self.event_bus.emit(EventType.USER_LANGUAGE_CHANGED, {
                    'user_id': user_id,
                    'language': language
                }, source='sqlite_manager')
                
        except Exception as e:
            logger.error(f"Error setting user language: {e}")

    # Standard methods (keeping existing functionality)
    async def get_user_keywords(self, user_id: int) -> List[str]:
        """Get keywords for a specific user"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT keyword FROM user_keywords WHERE user_id = ? ORDER BY created_at",
                    (user_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error getting user keywords: {e}")
            return []
    
    async def get_user_ignore_keywords(self, user_id: int) -> List[str]:
        """Get ignore keywords for a specific user"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT keyword FROM user_ignore_keywords WHERE user_id = ? ORDER BY created_at",
                    (user_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error getting user ignore keywords: {e}")
            return []
    
    async def purge_user_ignore_keywords(self, user_id: int) -> bool:
        """Remove all ignore keywords for a user"""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM user_ignore_keywords WHERE user_id = ?",
                    (user_id,)
                )
                await conn.commit()
                success = cursor.rowcount > 0
                if success:
                    logger.info(f"✅ Purged ignore keywords for user {user_id}")
                return success
        except Exception as e:
            logger.error(f"Error purging user ignore keywords: {e}")
            return False
    
    async def get_all_users_with_keywords(self) -> Dict[int, List[str]]:
        """Get all users who have keywords set"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute("""
                    SELECT user_id, GROUP_CONCAT(keyword, '|||') as keywords
                    FROM user_keywords 
                    GROUP BY user_id
                """) as cursor:
                    rows = await cursor.fetchall()
                    
                    result = {}
                    for user_id, keywords_str in rows:
                        if keywords_str:
                            keywords = keywords_str.split('|||')
                            result[user_id] = keywords
                    
                    return result
        except Exception as e:
            logger.error(f"Error getting all users with keywords: {e}")
            return {}
    
    async def cleanup_old_data(self, days: int = None):
        """Clean up old message forward logs"""
        if days is None:
            days = self.config.BACKUP_RETENTION_DAYS
            
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    f"DELETE FROM message_forwards WHERE forwarded_at < datetime('now', '-{days} days')"
                )
                await conn.commit()
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    logger.info(f"✅ Cleaned up {deleted_count} old message forward records")
                return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return 0
    
    # Statistics and monitoring methods
    async def get_system_stats(self) -> Dict[str, any]:
        """Get comprehensive system statistics"""
        try:
            async with self._get_connection() as conn:
                stats = {}
                
                # User stats
                async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
                    stats['total_users'] = (await cursor.fetchone())[0]
                
                # Channel stats
                async with conn.execute("SELECT type, COUNT(*) FROM monitored_channels WHERE status='active' GROUP BY type") as cursor:
                    channel_stats = await cursor.fetchall()
                    stats['channels'] = {row[0]: row[1] for row in channel_stats}
                
                # Keyword stats
                async with conn.execute("SELECT COUNT(*) FROM user_keywords") as cursor:
                    stats['total_keywords'] = (await cursor.fetchone())[0]
                
                # Forward stats (last 24h)
                async with conn.execute("SELECT COUNT(*) FROM message_forwards WHERE forwarded_at > datetime('now', '-1 day')") as cursor:
                    stats['forwards_24h'] = (await cursor.fetchone())[0]
                
                # Language distribution
                async with conn.execute("SELECT language, COUNT(*) FROM users GROUP BY language") as cursor:
                    language_stats = await cursor.fetchall()
                    stats['languages'] = {row[0]: row[1] for row in language_stats}
                
                return stats
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            return {}
    
    # Legacy compatibility methods
    async def init_channels_table(self):
        """Legacy compatibility - already handled in _create_schema"""
        pass


class ConnectionContext:
    """Context manager for database connections with timeout"""
    def __init__(self, connection_queue, timeout: int = 30):
        self.connection_queue = connection_queue
        self.connection = None
        self.timeout = timeout
    
    async def __aenter__(self):
        try:
            self.connection = await asyncio.wait_for(
                self.connection_queue.get(), 
                timeout=self.timeout
            )
            return self.connection
        except asyncio.TimeoutError:
            raise RuntimeError(f"Database connection timeout after {self.timeout}s - pool may be exhausted")
        except Exception as e:
            raise RuntimeError(f"Failed to get database connection: {e}")
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            try:
                # If there was an exception, rollback any uncommitted transaction
                if exc_type:
                    await self.connection.rollback()
                
                # Return connection to pool
                await self.connection_queue.put(self.connection)
            except Exception as e:
                logger.error(f"Error returning connection to pool: {e}")
                # Don't raise here to avoid masking the original exception