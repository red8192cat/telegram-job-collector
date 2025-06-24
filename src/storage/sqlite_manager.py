"""
High-Performance SQLite Manager - Enhanced with Simple Channel Management
Stores chat_id (permanent) + username (display) for better channel handling
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
        self._pool_size = 10
        self._available_connections = asyncio.Queue(maxsize=self._pool_size)
        self._initialized = False
        
    async def initialize(self):
        """Initialize database with optimizations for high performance"""
        if self._initialized:
            return
        
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
        # Create connection pool
        for _ in range(self._pool_size):
            conn = await aiosqlite.connect(self.db_path)
            await self._configure_connection(conn)
            await self._available_connections.put(conn)
    
        # Set initialized flag BEFORE using any connections
        self._initialized = True
    
        # Initialize schema
        async with self._get_connection() as conn:
            await self._create_schema(conn)
        
        logger.info(f"SQLite initialized: {self.db_path}")
    
    async def _configure_connection(self, conn):
        """Configure connection for maximum performance"""
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA cache_size=20000")
        await conn.execute("PRAGMA temp_store=memory")
        await conn.execute("PRAGMA mmap_size=268435456")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA wal_autocheckpoint=1000")
        
    async def _create_schema(self, conn):
        """Create optimized database schema with enhanced channel support"""
        
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
            await conn.execute(index)
        
        await conn.commit()
    
    async def _migrate_channels_table_simple(self, conn):
        """Migrate to simple enhanced format: chat_id + username"""
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
                return
            
            # Check if already migrated (has chat_id column)
            try:
                await conn.execute("SELECT chat_id FROM monitored_channels LIMIT 1")
                return  # Already migrated
            except:
                pass  # Needs migration
            
            # Migrate from old format
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
            
            # Migrate data
            async with conn.execute("SELECT identifier, type, status, added_at FROM monitored_channels") as cursor:
                old_channels = await cursor.fetchall()
            
            for identifier, channel_type, status, added_at in old_channels:
                chat_id, username = self._parse_old_identifier(identifier)
                
                await conn.execute("""
                    INSERT OR IGNORE INTO monitored_channels_new 
                    (chat_id, username, type, status, added_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (chat_id, username, channel_type, status, added_at))
            
            # Replace tables
            await conn.execute("DROP TABLE monitored_channels")
            await conn.execute("ALTER TABLE monitored_channels_new RENAME TO monitored_channels")
            await self._create_channel_indexes(conn)
            
            await conn.commit()
            logger.info(f"Migrated {len(old_channels)} channels to enhanced format")
            
        except Exception as e:
            logger.error(f"Channel migration error: {e}")

    def _parse_old_identifier(self, identifier: str) -> tuple:
        """Parse old identifier format to (chat_id, username)"""
        if identifier.startswith('@'):
            # Old @username format - generate consistent fake chat_id for now
            chat_id = hash(identifier) % 1000000000
            return chat_id, identifier
        elif identifier.lstrip('-').isdigit():
            # Old chat_id format
            return int(identifier), None
        else:
            # Unknown old format
            chat_id = hash(identifier) % 1000000000
            return chat_id, None

    async def _create_channel_indexes(self, conn):
        """Create indexes for channels table"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_monitored_channels_chat_id ON monitored_channels(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_monitored_channels_username ON monitored_channels(username)",
            "CREATE INDEX IF NOT EXISTS idx_monitored_channels_type_status ON monitored_channels(type, status)"
        ]
        for index in indexes:
            await conn.execute(index)
    
    def _get_connection(self):
        if not self._initialized:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return ConnectionContext(self._available_connections)
    
    async def close(self):
        """Close all connections"""
        while not self._available_connections.empty():
            conn = await self._available_connections.get()
            await conn.close()
        logger.info("SQLite connections closed")
    
    # Enhanced Channel Management Methods
    
    async def add_channel_simple(self, chat_id: int, username: str = None, channel_type: str = 'bot') -> bool:
        """Add channel with chat_id and optional username"""
        async with self._get_connection() as conn:
            try:
                await conn.execute("""
                    INSERT INTO monitored_channels (chat_id, username, type, last_updated)
                    VALUES (?, ?, ?, datetime('now'))
                """, (chat_id, username, channel_type))
                await conn.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def update_channel_username(self, chat_id: int, username: str) -> bool:
        """Update channel username when it changes"""
        async with self._get_connection() as conn:
            cursor = await conn.execute("""
                UPDATE monitored_channels 
                SET username = ?, last_updated = datetime('now')
                WHERE chat_id = ?
            """, (username, chat_id))
            await conn.commit()
            return cursor.rowcount > 0

    async def get_channel_display_name(self, chat_id: int) -> str:
        """Get display name for channel (username or chat_id)"""
        async with self._get_connection() as conn:
            async with conn.execute(
                "SELECT username FROM monitored_channels WHERE chat_id = ?", (chat_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return row[0]  # Return @username
                return f"Channel {chat_id}"  # Fallback to chat_id

    async def remove_channel_simple(self, chat_id: int, channel_type: str) -> bool:
        """Remove channel by chat_id"""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM monitored_channels WHERE chat_id = ? AND type = ?",
                (chat_id, channel_type)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def get_simple_bot_channels(self) -> List[int]:
        """Get bot channel chat_ids"""
        async with self._get_connection() as conn:
            async with conn.execute(
                "SELECT chat_id FROM monitored_channels WHERE type = 'bot' AND status = 'active'"
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    async def get_simple_user_channels(self) -> List[int]:
        """Get user channel chat_ids"""
        async with self._get_connection() as conn:
            async with conn.execute(
                "SELECT chat_id FROM monitored_channels WHERE type = 'user' AND status = 'active'"
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    async def get_all_channels_with_usernames(self) -> dict:
        """Get all channels with their usernames for display"""
        async with self._get_connection() as conn:
            async with conn.execute("""
                SELECT chat_id, username, type 
                FROM monitored_channels 
                WHERE status = 'active'
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

    async def find_channel_by_chat_id(self, chat_id: int) -> Optional[dict]:
        """Find channel by chat_id"""
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

    # Legacy compatibility methods for existing code
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
        """Parse identifier for legacy compatibility"""
        if identifier.startswith('@'):
            chat_id = hash(identifier) % 1000000000  # Temp ID
            return chat_id, identifier
        elif identifier.lstrip('-').isdigit():
            return int(identifier), None
        else:
            chat_id = hash(identifier) % 1000000000
            return chat_id, None
    
    # Language Support Methods
    async def get_user_language(self, user_id: int) -> str:
        """Get user's preferred language"""
        async with self._get_connection() as conn:
            async with conn.execute(
                "SELECT language FROM users WHERE id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0] or 'en'
                else:
                    await self.ensure_user_exists(user_id)
                    return 'en'

    async def set_user_language(self, user_id: int, language: str):
        """Set user's preferred language"""
        await self.ensure_user_exists(user_id)
        async with self._get_connection() as conn:
            await conn.execute(
                "UPDATE users SET language = ?, last_active = datetime('now') WHERE id = ?",
                (language, user_id)
            )
            await conn.commit()

    async def get_users_by_language(self, language: str) -> List[int]:
        """Get list of user IDs who use specific language"""
        async with self._get_connection() as conn:
            async with conn.execute(
                "SELECT id FROM users WHERE language = ?", (language,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    async def get_language_statistics(self) -> Dict[str, int]:
        """Get statistics about language usage"""
        async with self._get_connection() as conn:
            async with conn.execute(
                "SELECT language, COUNT(*) as count FROM users GROUP BY language"
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}
    
    # User management methods
    async def ensure_user_exists(self, user_id: int, language: str = 'en'):
        """Ensure user exists in database with language preference"""
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
    
    async def get_user_keywords(self, user_id: int) -> List[str]:
        """Get keywords for a specific user"""
        async with self._get_connection() as conn:
            async with conn.execute(
                "SELECT keyword FROM user_keywords WHERE user_id = ? ORDER BY created_at",
                (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
    
    async def set_user_keywords(self, user_id: int, keywords: List[str]):
        """Set keywords for a specific user (replaces all existing)"""
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
            except Exception:
                await conn.rollback()
                raise
    
    async def add_user_keyword(self, user_id: int, keyword: str) -> bool:
        """Add a keyword for a user"""
        await self.ensure_user_exists(user_id)
        
        async with self._get_connection() as conn:
            try:
                await conn.execute(
                    "INSERT INTO user_keywords (user_id, keyword) VALUES (?, ?)",
                    (user_id, keyword)
                )
                await conn.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
    
    async def remove_user_keyword(self, user_id: int, keyword: str) -> bool:
        """Remove a keyword for a user"""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM user_keywords WHERE user_id = ? AND keyword = ?",
                (user_id, keyword)
            )
            await conn.commit()
            return cursor.rowcount > 0
    
    async def get_user_ignore_keywords(self, user_id: int) -> List[str]:
        """Get ignore keywords for a specific user"""
        async with self._get_connection() as conn:
            async with conn.execute(
                "SELECT keyword FROM user_ignore_keywords WHERE user_id = ? ORDER BY created_at",
                (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
    
    async def set_user_ignore_keywords(self, user_id: int, keywords: List[str]):
        """Set ignore keywords for a specific user"""
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
            except Exception:
                await conn.rollback()
                raise
    
    async def add_user_ignore_keyword(self, user_id: int, keyword: str) -> bool:
        """Add an ignore keyword for a user"""
        await self.ensure_user_exists(user_id)
        
        async with self._get_connection() as conn:
            try:
                await conn.execute(
                    "INSERT INTO user_ignore_keywords (user_id, keyword) VALUES (?, ?)",
                    (user_id, keyword)
                )
                await conn.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
    
    async def remove_user_ignore_keyword(self, user_id: int, keyword: str) -> bool:
        """Remove an ignore keyword for a user"""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM user_ignore_keywords WHERE user_id = ? AND keyword = ?",
                (user_id, keyword)
            )
            await conn.commit()
            return cursor.rowcount > 0
    
    async def purge_user_ignore_keywords(self, user_id: int) -> bool:
        """Remove all ignore keywords for a user"""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM user_ignore_keywords WHERE user_id = ?",
                (user_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0
    
    async def get_all_users_with_keywords(self) -> Dict[int, List[str]]:
        """Get all users who have keywords set"""
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
    
    async def log_message_forward(self, user_id: int, channel_id: int, message_id: int):
        """Log a forwarded message"""
        async with self._get_connection() as conn:
            try:
                await conn.execute("BEGIN TRANSACTION")
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
                await conn.rollback()
            except Exception:
                await conn.rollback()
                raise
    
    async def check_user_limit(self, user_id: int) -> bool:
        """Check if user has reached daily limit"""
        return True
    
    async def cleanup_old_data(self, days: int = 30):
        """Clean up old message forward logs"""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM message_forwards WHERE forwarded_at < datetime('now', '-{} days')".format(days)
            )
            await conn.commit()
            logger.info(f"Cleaned up {cursor.rowcount} old message forward records")

    # Export/Import Methods for Configuration Management
    async def export_all_channels_for_config(self):
        """Export all channels for config file - simple format"""
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
    
    async def export_all_users_for_config(self):
        """Export all users with their data for config file"""
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
    
    async def import_channels_from_config(self, bot_channels, user_channels):
        """Import channels from config (replace existing)"""
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
                        chat_id, username = self._parse_identifier_for_legacy(channel)
                    
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
                        chat_id, username = self._parse_identifier_for_legacy(channel)
                    
                    await conn.execute(
                        "INSERT INTO monitored_channels (chat_id, username, type) VALUES (?, ?, ?)",
                        (chat_id, username, 'user')
                    )
                
                await conn.commit()
                logger.info(f"Imported {len(bot_channels)} bot channels, {len(user_channels)} user channels")
                
            except Exception:
                await conn.rollback()
                raise
    
    async def import_users_from_config(self, users_data):
        """Import users from config (replace existing)"""
        async with self._get_connection() as conn:
            await conn.execute("BEGIN TRANSACTION")
            try:
                # Clear existing user data
                await conn.execute("DELETE FROM user_keywords")
                await conn.execute("DELETE FROM user_ignore_keywords") 
                await conn.execute("DELETE FROM users")
                
                # Import users
                for user in users_data:
                    user_id = user['user_id']
                    
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
                        if keyword.strip():
                            await conn.execute(
                                "INSERT INTO user_keywords (user_id, keyword) VALUES (?, ?)",
                                (user_id, keyword.strip())
                            )
                    
                    # Insert ignore keywords
                    for keyword in user.get('ignore_keywords', []):
                        if keyword.strip():
                            await conn.execute(
                                "INSERT INTO user_ignore_keywords (user_id, keyword) VALUES (?, ?)",
                                (user_id, keyword.strip())
                            )
                
                await conn.commit()
                logger.info(f"Imported {len(users_data)} users")
                
            except Exception:
                await conn.rollback()
                raise


class ConnectionContext:
    """Context manager for database connections"""
    def __init__(self, connection_queue):
        self.connection_queue = connection_queue
        self.connection = None
    
    async def __aenter__(self):
        self.connection = await self.connection_queue.get()
        return self.connection
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.connection_queue.put(self.connection)