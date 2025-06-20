# Production Deployment Instructions

## After pulling the SQLite migration:

### 1. Clean up old data (if needed)
```bash
# Remove old JSON files and Docker artifacts
rm -rf data/*
docker-compose down
docker system prune -f
```

### 2. Rebuild with new dependencies
```bash
# Build fresh image with SQLite dependencies
docker-compose build --no-cache
```

### 3. Deploy
```bash
# Set your bot token
echo "TELEGRAM_BOT_TOKEN=your_actual_token" > .env

# Start with SQLite database
docker-compose up -d

# Verify everything is working
docker-compose logs -f telegram-bot
```

### 4. Database file location
- Single database file: `data/bot.db`
- To migrate: just copy this one file
- Automatic backups: database creates WAL files

### 5. Troubleshooting
```bash
# Check health
docker-compose exec telegram-bot python health_check.py

# Check database
ls -la data/
# Should see: bot.db, bot.db-shm, bot.db-wal

# Reset if needed
rm data/bot.db*
docker-compose restart telegram-bot
```
