#!/usr/bin/env python3
import asyncio
import sys
import os
sys.path.append('/app/src')

async def health_check():
    try:
        from storage.sqlite_manager import SQLiteManager
        
        db_path = os.getenv('DATABASE_PATH', '/app/data/bot.db')
        db = SQLiteManager(db_path)
        await db.initialize()
        
        async with db._get_connection() as conn:
            async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
                result = await cursor.fetchone()
                print(f"Health check passed - {result[0]} users in database")
        
        await db.close()
        return 0
    except Exception as e:
        print(f"Health check failed: {e}")
        return 1

if __name__ == '__main__':
    exit_code = asyncio.run(health_check())
    sys.exit(exit_code)
