# 🚀 Production Deployment Guide

Complete guide for deploying the Telegram Job Collector Bot in production environments.

## 🏗️ Prerequisites

- **Server**: Linux VPS with 1GB+ RAM
- **Docker**: Docker and Docker Compose installed
- **Bot Token**: From [@BotFather](https://t.me/BotFather)
- **Domain** (optional): For webhook mode
- **Telegram Account** (optional): For advanced monitoring

## 🚀 Quick Production Setup

### 1. Server Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Restart to apply docker group
sudo reboot
```

### 2. Deploy the Bot

```bash
# Clone repository
git clone https://github.com/red8192cat/telegram-job-collector.git
cd telegram-job-collector

# Configure secrets
cp data/config/bot-secrets.env.example data/config/bot-secrets.env
nano data/config/bot-secrets.env
```

**Edit `data/config/bot-secrets.env`:**
```bash
# Required: Bot token from @BotFather
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Optional: Your Telegram user ID for admin features
AUTHORIZED_ADMIN_ID=123456789

# Optional: For advanced channel monitoring
# API_ID=12345678
# API_HASH=your_api_hash_here
# PHONE_NUMBER=+1234567890
```

### 3. Start the Bot

```bash
# Build and start
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs -f telegram-bot
```

### 4. Add Channels

```bash
# Method 1: Via admin commands (if AUTHORIZED_ADMIN_ID set)
# Send to your bot: /admin add_bot_channel @yourjobchannel

# Method 2: Direct database (temporary)
docker exec -it job-collector-bot python -c "
import asyncio
from src.storage.sqlite_manager import SQLiteManager

async def setup():
    db = SQLiteManager()
    await db.initialize()
    # Add your channels here
    await db.add_channel_simple(-1001234567890, '@techjobs', 'bot')
    await db.add_channel_simple(-1009876543210, '@remotework', 'bot')
    print('Channels added successfully!')

asyncio.run(setup())
"
```

## 🔧 Production Configuration

### Docker Compose for Production

Create `docker-compose.prod.yml`:

```yaml
services:
  telegram-bot:
    build: .
    container_name: job-collector-bot-prod
    env_file:
      - data/config/bot-secrets.env
    environment:
      - DATABASE_PATH=/app/data/bot.db
      - LOG_LEVEL=INFO
      - BACKUP_RETENTION_COUNT=10
    volumes:
      - ./data:/app/data
      - /etc/localtime:/etc/localtime:ro
    restart: unless-stopped
    networks:
      - bot-network
    healthcheck:
      test: ["CMD", "python", "/app/src/health_check.py"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  bot-network:
    driver: bridge
```

### Nginx Reverse Proxy (Optional)

For webhook mode with SSL:

```nginx
# /etc/nginx/sites-available/jobbot
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location /webhook/ {
        proxy_pass http://localhost:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 📊 Monitoring & Maintenance

### System Monitoring

```bash
# Check system resources
docker stats job-collector-bot-prod

# Monitor logs in real-time
docker logs -f job-collector-bot-prod

# Check database size
docker exec job-collector-bot-prod ls -lah /app/data/

# Health check
docker exec job-collector-bot-prod python /app/src/health_check.py
```

### Performance Monitoring

```bash
# Monitor message processing
docker logs job-collector-bot-prod | grep "FORWARD" | tail -20

# Check database performance  
docker logs job-collector-bot-prod | grep "SQLite" | tail -10

# Monitor errors
docker logs job-collector-bot-prod | grep "ERROR" | tail -10
```

### Automated Backups

Create backup script `/opt/jobbot/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/opt/jobbot/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
docker exec job-collector-bot-prod cp /app/data/bot.db /tmp/bot_backup_$DATE.db
docker cp job-collector-bot-prod:/tmp/bot_backup_$DATE.db $BACKUP_DIR/

# Backup config
docker cp job-collector-bot-prod:/app/data/config $BACKUP_DIR/config_$DATE/

# Cleanup old backups (keep last 7 days)
find $BACKUP_DIR -name "bot_backup_*.db" -mtime +7 -delete
find $BACKUP_DIR -name "config_*" -mtime +7 -exec rm -rf {} \;

echo "Backup completed: $DATE"
```

Add to crontab:
```bash
# Daily backup at 2 AM
0 2 * * * /opt/jobbot/backup.sh >> /opt/jobbot/backup.log 2>&1
```

## 🔄 Updates & Maintenance

### Updating the Bot

```bash
# Navigate to bot directory
cd telegram-job-collector

# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d

# Verify update
docker logs job-collector-bot-prod | head -20
```

### Database Maintenance

```bash
# Check database integrity
docker exec job-collector-bot-prod sqlite3 /app/data/bot.db "PRAGMA integrity_check;"

# Optimize database
docker exec job-collector-bot-prod sqlite3 /app/data/bot.db "VACUUM;"

# Check database size and stats
docker exec job-collector-bot-prod sqlite3 /app/data/bot.db "
.headers on
.mode column
SELECT 
  name, 
  COUNT(*) as rows,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname = 'main';
"
```

## 🔒 Security Best Practices

### File Permissions

```bash
# Secure configuration files
chmod 600 data/config/bot-secrets.env
chown root:root data/config/bot-secrets.env

# Secure data directory
chmod 750 data/
chown -R 1000:1000 data/
```

### Firewall Configuration

```bash
# UFW firewall setup
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Environment Security

```bash
# Never commit secrets to git
echo "data/config/bot-secrets.env" >> .gitignore

# Use environment variables in production
export TELEGRAM_BOT_TOKEN="your_token_here"

# Rotate bot token periodically via @BotFather
```

## 📈 Scaling for High Volume

### Database Optimization

For 10,000+ users, optimize SQLite:

```python
# Add to sqlite_manager.py
async def _configure_connection(self, conn):
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA cache_size=50000")  # Increased
    await conn.execute("PRAGMA temp_store=memory")
    await conn.execute("PRAGMA mmap_size=536870912")  # 512MB
    await conn.execute("PRAGMA wal_autocheckpoint=1000")
```

### Multiple Bot Instances

For extreme scale, run multiple bot instances:

```yaml
# docker-compose.scale.yml
services:
  telegram-bot-1:
    build: .
    container_name: job-collector-bot-1
    # ... configuration

  telegram-bot-2:
    build: .
    container_name: job-collector-bot-2
    # ... configuration

  load-balancer:
    image: nginx:alpine
    # ... load balancer configuration
```

### Resource Limits

```yaml
services:
  telegram-bot:
    # ... other configuration
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 256M
        reservations:
          cpus: '0.25'
          memory: 128M
```

## 🚨 Troubleshooting Production Issues

### Common Issues

**Bot not receiving messages:**
```bash
# Check if bot is admin in channels
docker exec job-collector-bot-prod python -c "
import asyncio, os
from telegram import Bot

async def check():
    bot = Bot(os.getenv('TELEGRAM_BOT_TOKEN'))
    chat = await bot.get_chat('@yourchannel')
    member = await bot.get_chat_member(chat.id, bot.id)
    print(f'Bot status: {member.status}')

asyncio.run(check())
"
```

**Database locked errors:**
```bash
# Check for long-running transactions
docker exec job-collector-bot-prod sqlite3 /app/data/bot.db ".timeout 30000"

# Restart bot if necessary
docker-compose restart telegram-bot
```

**Memory issues:**
```bash
# Monitor memory usage
docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Increase container memory limit if needed
```

### Log Analysis

```bash
# Extract performance metrics
docker logs job-collector-bot-prod 2>&1 | grep -E "(FORWARD|ERROR|SQLite)" | tail -50

# Monitor forwarding rate
docker logs job-collector-bot-prod 2>&1 | grep "FORWARD" | awk '{print $1, $2}' | uniq -c

# Check for rate limiting
docker logs job-collector-bot-prod 2>&1 | grep -i "rate\|limit\|flood"
```

## 📋 Production Checklist

Before going live:

- [ ] Bot token configured and tested
- [ ] Admin ID set for management access
- [ ] Channels added and bot has admin permissions
- [ ] Docker containers running and healthy
- [ ] Backup script configured and tested
- [ ] Monitoring and logging set up
- [ ] Firewall configured
- [ ] SSL certificate installed (if using webhooks)
- [ ] Resource limits configured
- [ ] Update procedure documented

## 🎯 Performance Targets

**Recommended server specs by user count:**

| Users | CPU | RAM | Storage | Network |
|-------|-----|-----|---------|---------|
| 1-1,000 | 1 vCPU | 1GB | 10GB SSD | 100Mbps |
| 1,000-5,000 | 2 vCPU | 2GB | 20GB SSD | 200Mbps |
| 5,000-10,000 | 4 vCPU | 4GB | 40GB SSD | 500Mbps |
| 10,000+ | 8 vCPU | 8GB | 80GB SSD | 1Gbps |

**Expected performance metrics:**

- **Response time**: <10ms for keyword matching
- **Message forwarding**: 100-500 messages/minute
- **Database operations**: <5ms average
- **Memory usage**: 50-100MB base + 5MB per 1000 users
- **Uptime**: 99.9%+ with proper configuration

This deployment guide ensures your job collector bot runs reliably in production!