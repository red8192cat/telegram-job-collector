"""
High-Performance SQLite Manager - FIXED VERSION
Enhanced with Simple Channel Management and proper connection handling
"""

import aiosqlite
import asyncio
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SQLiteManager:
    def __init__(self, db_path: str = "data/bot.db"):
        self.db_path = db_path
        self._pool_size = 5  # Reduced pool size to prevent issues
        self._available_connections = asyncio.Queue(maxsize=self._pool_size)
        self._initialized = False
        self._lock = asyncio.Lock()  # Added lock for thread safety
        
    async def initialize(self):
        """Initialize database with optimizations for high performance - FIXED"""
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
                
                # Create connection pool AFTER setting initialized flag
                self._initialized = True
                
                for i in range(self._pool_size):
                    conn = await aiosqlite.connect(self.db_path)
                    await self._configure_connection(conn)
                    await self._available_connections.put(conn)
                
                # Initialize schema with a separate connection
                async with self._get_connection() as conn:
                    await self._create_schema(conn)
                
                logger.info(f"✅ SQLite initialized: {self.db_path} (pool size: {self._pool_size})")
                
            except Exception as e:
                self._initialized = False
                logger.error(f"❌ Database initialization failed: {e}")
                raise
    
    async def _configure_connection(self, conn):
        """Configure connection for maximum performance - IMPROVED"""
        try:
            # Performance optimizations
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA cache_size=10000")  # Reduced cache size
            await conn.execute("PRAGMA temp_store=memory")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA wal_autocheckpoint=1000")
            
            # Set busy timeout to handle concurrent access
            await conn.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
            
        except Exception as e:
            logger.error(f"Error configuring connection: {e}")
            raise
        
    async def _create_schema(self, conn):
        """Create optimized database schema with enhanced channel support - FIXED"""
        
        try:
            # Migrate channels table to enhanced format
            await self._migrate_channels_table_simple(conn)
            
            # Users table with language support
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT DEFAULT (datetime('now')),
                    last_active TEXT DEFAULT (datetime('now')),
                    total_forwards INTEGER DEFAULT 0,
                    language TEXT DEFAULT 'en'
                )
            """)
            
            # Add language column to existing users table (migration)
            try:
                await conn.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
            except Exception:
                # Column already exists, ignore error
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
                "CREATE INDEX IF NOT EXISTS idx_users_language ON users(language)"
            ]
            
            for index in indexes:
                try:
                    await conn.execute(index)
                except Exception as e:
                    # Index might already exist, log but continue
                    logger.debug(f"Index creation warning: {e}")
            
            await conn.commit()
            logger.info("✅ Database schema created/updated")
            
        except Exception as e:
            logger.error(f"❌ Schema creation failed: {e}")
            await conn.rollback()
            raise
    
    async def _migrate_channels_table_simple(self, conn):
        """Migrate to simple enhanced format: chat_id + username - FIXED"""
        try:
            # Check if old table exists
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='monitored_channels'"
            ) as cursor:
                old_exists = await cursor.fetchone()
            
            if not old_exists:
                # No old table, create new enhanced one
                await conn.execute("""
                    CREATE TABLE monitored_channels (
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
                logger.info("✅ Created new monitored_channels table")
                return
            
            # Check if already migrated (has chat_id column)
            try:
                await conn.execute("SELECT chat_id FROM monitored_channels LIMIT 1")
                logger.debug("Channels table already migrated")
                return  # Already migrated
            except:
                pass  # Needs migration
            
            # Migrate from old format
            logger.info("🔄 Migrating channels table to new format...")
            await conn.execute("""
                CREATE TABLE monitored_channels_new (
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
            
            # Migrate data if old table has data
            try:
                async with conn.execute("SELECT identifier, type, status, added_at FROM monitored_channels") as cursor:
                    old_channels = await cursor.fetchall()
                
                for identifier, channel_type, status, added_at in old_channels:
                    chat_id, username = self._parse_old_identifier(identifier)
                    
                    await conn.execute("""
                        INSERT OR IGNORE INTO monitored_channels_new 
                        (chat_id, username, type, status, added_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (chat_id, username, channel_type, status, added_at))
                
                logger.info(f"✅ Migrated {len(old_channels)} channels to new format")
            except Exception as e:
                logger.warning(f"Migration warning: {e}")
            
            # Replace tables
            await conn.execute("DROP TABLE monitored_channels")
            await conn.execute("ALTER TABLE monitored_channels_new RENAME TO monitored_channels")
            await self._create_channel_indexes(conn)
            
            await conn.commit()
            logger.info("✅ Channels table migration completed")
            
        except Exception as e:
            logger.error(f"❌ Channel migration error: {e}")
            # Don't raise - let it create new table instead

    def _parse_old_identifier(self, identifier: str) -> tuple:
        """Parse old identifier format to (chat_id, username) - IMPROVED"""
        if not identifier:
            return 0, None
        
        if identifier.startswith('@'):
            # Old @username format - generate consistent hash-based ID
            chat_id = -abs(hash(identifier) % 1000000000)  # Ensure negative for channels
            return chat_id, identifier
        elif identifier.lstrip('-').isdigit():
            # Old chat_id format
            return int(identifier), None
        else:
            # Unknown old format - generate negative ID
            chat_id = -abs(hash(identifier) % 1000000000)
            return chat_id, identifier if identifier.startswith('@') else None

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
        """Get database connection from pool - FIXED with proper error handling"""
        if not self._initialized:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return ConnectionContext(self._available_connections)
    
    async def close(self):
        """Close all connections - IMPROVED"""
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
                
            except Exception as e:
                logger.error(f"Error during database close: {e}")
    
    # Enhanced Channel Management Methods - FIXED
    
    async def add_channel_simple(self, chat_id: int, username: str = None, channel_type: str = 'bot') -> bool:
        """Add channel with chat_id and optional username - IMPROVED error handling"""
        try:
            async with self._get_connection() as conn:
                await conn.execute("""
                    INSERT INTO monitored_channels (chat_id, username, type, last_updated)
                    VALUES (?, ?, ?, datetime('now'))
                """, (chat_id, username, channel_type))
                await conn.commit()
                logger.info(f"✅ Added {channel_type} channel: {username or chat_id}")
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
        """Get display name for channel (username or chat_id) - IMPROVED"""
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
                return success
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            return False

    async def get_simple_bot_channels(self) -> List[int]:
        """Get bot channel chat_ids - IMPROVED error handling"""
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
        """Get user channel chat_ids - IMPROVED error handling"""
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
        """Get all channels with their usernames for display - IMPROVED"""
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

    async def find_channel_by_chat_id(self, chat_id: int) -> Optional[dict]:
        """Find channel by chat_id"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute("""
                    SELECT chat_id, username, type 
                    FROM monitored_channels 
                    WHERE chat_id = ? AND status = 'active'
                """, (chat_id,)) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        return {
                            'chat_id': row[0],
                            'username': row[1],
                            'type': row[2]
                        }
                    
                    return None
        except Exception as e:
            logger.error(f"Error finding channel: {e}")
            return None

    # Legacy compatibility methods for existing code - IMPROVED
    async def init_channels_table(self):
        """Legacy compatibility - already handled in _create_schema"""
        pass
    
    async def add_channel_db(self, identifier: str, channel_type: str):
        """Legacy compatibility - parse identifier and add"""
        chat_id, username = self._parse_identifier_for_legacy(identifier)
        return await self.add_channel_simple(chat_id, username, channel_type)

    async def remove_channel_db(self, identifier: str, channel_type: str):
        """Legacy compatibility - parse identifier and remove"""
        chat_id, username = self._parse_identifier_for_legacy(identifier)
        return await self.remove_channel_simple(chat_id, channel_type)

    async def get_bot_monitored_channels_db(self):
        """Legacy compatibility"""
        return await self.get_simple_bot_channels()

    async def get_user_monitored_channels_db(self):
        """Legacy compatibility"""
        return await self.get_simple_user_channels()

    def _parse_identifier_for_legacy(self, identifier: str) -> tuple:
        """Parse identifier for legacy compatibility - IMPROVED"""
        if not identifier:
            return 0, None
        
        if identifier.startswith('@'):
            chat_id = -abs(hash(identifier) % 1000000000)  # Ensure negative for channels
            return chat_id, identifier
        elif identifier.lstrip('-').isdigit():
            return int(identifier), None
        else:
            chat_id = -abs(hash(identifier) % 1000000000)
            return chat_id, identifier if identifier.startswith('@') else None
    
    # Language Support Methods - IMPROVED
    async def get_user_language(self, user_id: int) -> str:
        """Get user's preferred language"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT language FROM users WHERE id = ?", (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row[0] or 'en'
                    else:
                        # Create user with default language
                        await self.ensure_user_exists(user_id)
                        return 'en'
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            return 'en'

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
        except Exception as e:
            logger.error(f"Error setting user language: {e}")

    async def get_users_by_language(self, language: str) -> List[int]:
        """Get list of user IDs who use specific language"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT id FROM users WHERE language = ?", (language,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error getting users by language: {e}")
            return []

    async def get_language_statistics(self) -> Dict[str, int]:
        """Get statistics about language usage"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT language, COUNT(*) as count FROM users GROUP BY language"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"Error getting language statistics: {e}")
            return {}
    
    # User management methods - IMPROVED
    async def ensure_user_exists(self, user_id: int, language: str = 'en'):
        """Ensure user exists in database with language preference"""
        try:
            async with self._get_connection() as conn:
                await conn.execute("""
                    INSERT OR IGNORE INTO users (id, last_active, language) 
                    VALUES (?, datetime('now'), ?)
                """, (user_id, language))
                await conn.execute("""
                    UPDATE users SET last_active = datetime('now') 
                    WHERE id = ?
                """, (user_id,))
                await conn.commit()
        except Exception as e:
            logger.error(f"Error ensuring user exists: {e}")
    
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
    
    async def set_user_keywords(self, user_id: int, keywords: List[str]):
        """Set keywords for a specific user (replaces all existing) - IMPROVED"""
        try:
            await self.ensure_user_exists(user_id)
            
            async with self._get_connection() as conn:
                await conn.execute("BEGIN TRANSACTION")
                try:
                    await conn.execute("DELETE FROM user_keywords WHERE user_id = ?", (user_id,))
                    if keywords:
                        await conn.executemany(
                            "INSERT INTO user_keywords (user_id, keyword) VALUES (?, ?)",
                            [(user_id, keyword) for keyword in keywords]
                        )
                    await conn.commit()
                    logger.info(f"✅ Set {len(keywords)} keywords for user {user_id}")
                except Exception:
                    await conn.rollback()
                    raise
        except Exception as e:
            logger.error(f"Error setting user keywords: {e}")
            raise
    
    async def add_user_keyword(self, user_id: int, keyword: str) -> bool:
        """Add a keyword for a user"""
        try:
            await self.ensure_user_exists(user_id)
            
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT INTO user_keywords (user_id, keyword) VALUES (?, ?)",
                    (user_id, keyword)
                )
                await conn.commit()
                return True
        except aiosqlite.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"Error adding user keyword: {e}")
            return False
    
    async def remove_user_keyword(self, user_id: int, keyword: str) -> bool:
        """Remove a keyword for a user"""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM user_keywords WHERE user_id = ? AND keyword = ?",
                    (user_id, keyword)
                )
                await conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing user keyword: {e}")
            return False
    
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
    
    async def set_user_ignore_keywords(self, user_id: int, keywords: List[str]):
        """Set ignore keywords for a specific user - IMPROVED"""
        try:
            await self.ensure_user_exists(user_id)
            
            async with self._get_connection() as conn:
                await conn.execute("BEGIN TRANSACTION")
                try:
                    await conn.execute("DELETE FROM user_ignore_keywords WHERE user_id = ?", (user_id,))
                    if keywords:
                        await conn.executemany(
                            "INSERT INTO user_ignore_keywords (user_id, keyword) VALUES (?, ?)",
                            [(user_id, keyword) for keyword in keywords]
                        )
                    await conn.commit()
                    logger.info(f"✅ Set {len(keywords)} ignore keywords for user {user_id}")
                except Exception:
                    await conn.rollback()
                    raise
        except Exception as e:
            logger.error(f"Error setting user ignore keywords: {e}")
            raise
    
    async def add_user_ignore_keyword(self, user_id: int, keyword: str) -> bool:
        """Add an ignore keyword for a user"""
        try:
            await self.ensure_user_exists(user_id)
            
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT INTO user_ignore_keywords (user_id, keyword) VALUES (?, ?)",
                    (user_id, keyword)
                )
                await conn.commit()
                return True
        except aiosqlite.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"Error adding user ignore keyword: {e}")
            return False
    
    async def remove_user_ignore_keyword(self, user_id: int, keyword: str) -> bool:
        """Remove an ignore keyword for a user"""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM user_ignore_keywords WHERE user_id = ? AND keyword = ?",
                    (user_id, keyword)
                )
                await conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing user ignore keyword: {e}")
            return False
    
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
        """Get all users who have keywords set - IMPROVED"""
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
    
    async def log_message_forward(self, user_id: int, channel_id: int, message_id: int):
        """Log a forwarded message - IMPROVED"""
        try:
            async with self._get_connection() as conn:
                await conn.execute("BEGIN TRANSACTION")
                try:
                    await conn.execute(
                        "INSERT INTO message_forwards (user_id, channel_id, message_id) VALUES (?, ?, ?)",
                        (user_id, channel_id, message_id)
                    )
                    await conn.execute(
                        "UPDATE users SET total_forwards = total_forwards + 1 WHERE id = ?",
                        (user_id,)
                    )
                    await conn.commit()
                except aiosqlite.IntegrityError:
                    # Duplicate forward - ignore
                    await conn.rollback()
                except Exception:
                    await conn.rollback()
                    raise
        except Exception as e:
            logger.error(f"Error logging message forward: {e}")
    
    async def check_user_limit(self, user_id: int) -> bool:
        """Check if user has reached daily limit - placeholder"""
        return True
    
    async def cleanup_old_data(self, days: int = 30):
        """Clean up old message forward logs - IMPROVED"""
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

    # Export/Import Methods for Configuration Management - IMPROVED
    async def export_all_channels_for_config(self):
        """Export all channels for config file - simple format"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute("""
                    SELECT chat_id, username, type 
                    FROM monitored_channels 
                    WHERE status = 'active'
                    ORDER BY type, username
                """) as cursor:
                    rows = await cursor.fetchall()
                    
                    bot_channels = []
                    user_channels = []
                    
                    for chat_id, username, channel_type in rows:
                        channel_data = {
                            'chat_id': chat_id,
                            'username': username
                        }
                        
                        if channel_type == 'bot':
                            bot_channels.append(channel_data)
                        else:
                            user_channels.append(channel_data)
                    
                    return bot_channels, user_channels
        except Exception as e:
            logger.error(f"Error exporting channels: {e}")
            return [], []
    
    async def export_all_users_for_config(self):
        """Export all users with their data for config file"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute("""
                    SELECT 
                        u.id,
                        u.created_at,
                        u.last_active,
                        u.total_forwards,
                        u.language,
                        GROUP_CONCAT(DISTINCT uk.keyword) as keywords,
                        GROUP_CONCAT(DISTINCT uik.keyword) as ignore_keywords
                    FROM users u
                    LEFT JOIN user_keywords uk ON u.id = uk.user_id
                    LEFT JOIN user_ignore_keywords uik ON u.id = uik.user_id
                    GROUP BY u.id
                    ORDER BY u.id
                """) as cursor:
                    rows = await cursor.fetchall()
                    
                    users_data = []
                    for row in rows:
                        user_data = {
                            'user_id': row[0],
                            'created_at': row[1],
                            'last_active': row[2], 
                            'total_forwards': row[3] or 0,
                            'language': row[4] or 'en',
                            'keywords': row[5].split(',') if row[5] else [],
                            'ignore_keywords': row[6].split(',') if row[6] else []
                        }
                        users_data.append(user_data)
                    
                    return users_data
        except Exception as e:
            logger.error(f"Error exporting users: {e}")
            return []
    
    async def import_channels_from_config(self, bot_channels, user_channels):
        """Import channels from config (replace existing) - IMPROVED"""
        try:
            async with self._get_connection() as conn:
                await conn.execute("BEGIN TRANSACTION")
                try:
                    # Clear existing channels
                    await conn.execute("DELETE FROM monitored_channels")
                    
                    # Import bot channels
                    for channel in bot_channels:
                        if isinstance(channel, dict):
                            chat_id = channel.get('chat_id')
                            username = channel.get('username')
                        else:
                            # Legacy string format
                            chat_id, username = self._parse_identifier_for_legacy(str(channel))
                        
                        if chat_id:
                            await conn.execute(
                                "INSERT INTO monitored_channels (chat_id, username, type) VALUES (?, ?, ?)",
                                (chat_id, username, 'bot')
                            )
                    
                    # Import user channels  
                    for channel in user_channels:
                        if isinstance(channel, dict):
                            chat_id = channel.get('chat_id')
                            username = channel.get('username')
                        else:
                            # Legacy string format
                            chat_id, username = self._parse_identifier_for_legacy(str(channel))
                        
                        if chat_id:
                            await conn.execute(
                                "INSERT INTO monitored_channels (chat_id, username, type) VALUES (?, ?, ?)",
                                (chat_id, username, 'user')
                            )
                    
                    await conn.commit()
                    logger.info(f"✅ Imported {len(bot_channels)} bot channels, {len(user_channels)} user channels")
                    
                except Exception:
                    await conn.rollback()
                    raise
        except Exception as e:
            logger.error(f"Error importing channels: {e}")
            raise
    
    async def import_users_from_config(self, users_data):
        """Import users from config (replace existing) - IMPROVED"""
        try:
            async with self._get_connection() as conn:
                await conn.execute("BEGIN TRANSACTION")
                try:
                    # Clear existing user data
                    await conn.execute("DELETE FROM user_keywords")
                    await conn.execute("DELETE FROM user_ignore_keywords") 
                    await conn.execute("DELETE FROM users")
                    
                    # Import users
                    for user in users_data:
                        user_id = user.get('user_id')
                        if not user_id:
                            continue
                        
                        # Insert user
                        await conn.execute("""
                            INSERT INTO users (id, created_at, last_active, total_forwards, language)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            user_id,
                            user.get('created_at', datetime.now().isoformat()),
                            user.get('last_active', datetime.now().isoformat()),
                            user.get('total_forwards', 0),
                            user.get('language', 'en')
                        ))
                        
                        # Insert keywords
                        for keyword in user.get('keywords', []):
                            if keyword and keyword.strip():
                                await conn.execute(
                                    "INSERT INTO user_keywords (user_id, keyword) VALUES (?, ?)",
                                    (user_id, keyword.strip())
                                )
                        
                        # Insert ignore keywords
                        for keyword in user.get('ignore_keywords', []):
                            if keyword and keyword.strip():
                                await conn.execute(
                                    "INSERT INTO user_ignore_keywords (user_id, keyword) VALUES (?, ?)",
                                    (user_id, keyword.strip())
                                )
                    
                    await conn.commit()
                    logger.info(f"✅ Imported {len(users_data)} users")
                    
                except Exception:
                    await conn.rollback()
                    raise
        except Exception as e:
            logger.error(f"Error importing users: {e}")
            raise


class ConnectionContext:
    """Context manager for database connections - IMPROVED with better error handling"""
    def __init__(self, connection_queue):
        self.connection_queue = connection_queue
        self.connection = None
    
    async def __aenter__(self):
        try:
            self.connection = await asyncio.wait_for(
                self.connection_queue.get(), 
                timeout=30.0  # 30 second timeout
            )
            return self.connection
        except asyncio.TimeoutError:
            raise RuntimeError("Database connection timeout - pool may be exhausted")
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
    