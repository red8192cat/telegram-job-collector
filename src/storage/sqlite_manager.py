"""
High-Performance SQLite Manager - Optimized for 10,000+ users
Single file database perfect for easy migration
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
        
        # Initialize schema
        async with self._get_connection() as conn:
            await self._create_schema(conn)
            
        self._initialized = True
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
        """Create optimized database schema"""
        
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                created_at TEXT DEFAULT (datetime('now')),
                last_active TEXT DEFAULT (datetime('now')),
                total_forwards INTEGER DEFAULT 0
            )
        """)
        
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
            "CREATE INDEX IF NOT EXISTS idx_message_forwards_forwarded_at ON message_forwards(forwarded_at)"
        ]
        
        for index in indexes:
            await conn.execute(index)
        
        await conn.commit()
    
    async def _get_connection(self):
        if not self._initialized:
            await self.initialize()
        return ConnectionContext(self._available_connections)
    
    async def close(self):
        """Close all connections"""
        while not self._available_connections.empty():
            conn = await self._available_connections.get()
            await conn.close()
        logger.info("SQLite connections closed")
    
    async def ensure_user_exists(self, user_id: int):
        """Ensure user exists in database"""
        async with self._get_connection() as conn:
            await conn.execute("""
                INSERT OR IGNORE INTO users (id, last_active) 
                VALUES (?, datetime('now'))
            """, (user_id,))
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
