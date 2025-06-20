#!/usr/bin/env python3
import sys
import os

try:
    # Simple check - if the database file exists, we're healthy
    db_path = os.getenv('DATABASE_PATH', '/app/data/bot.db')
    if os.path.exists(db_path):
        print("Health check passed - database file exists")
        sys.exit(0)
    else:
        print("Health check failed - database file missing")
        sys.exit(1)
except Exception as e:
    print(f"Health check failed: {e}")
    sys.exit(1)
