# 🎯 Advanced Features Guide

Complete guide to advanced keyword matching, channel management, and bot features.

## 🎯 Advanced Keyword System

### Keyword Types

| Type | Syntax | Example | Matches |
|------|--------|---------|---------|
| **Required** | `[word]` | `[remote]` | Must contain "remote" |
| **Required OR** | `[word1\|word2]` | `[remote\|online]` | Must contain "remote" OR "online" |
| **Single** | `word` | `python` | "Python developer needed" |
| **AND Logic** | `word1+word2` | `python+remote` | "Remote Python developer" |
| **Exact Phrase** | `"phrase"` | `"project manager"` | "Project manager role" (exact order) |
| **Wildcard** | `word*` | `develop*` | developer, development, developing |
| **Multi-Wildcard** | `"word1* word2*"` | `"support* engineer*"` | "Support Engineer", "Supporting Engineering" |

### Complex Examples

```bash
# Must be remote AND match tech skills
/keywords [remote], linux, python, "data scientist"

# Must be remote OR online AND senior OR lead
/keywords [remote|online], [senior|lead], python, devops

# Complex patterns with wildcards
/keywords [remote|online], "support* engineer*", python+django, develop*

# Filter out unwanted technologies
/ignore_keywords java, php, "team lead"
```

### Logic Rules

- **Required keywords** (in brackets): ALL must be present
- **Optional keywords**: At least ONE must match
- **Final rule**: `(ALL required) AND (at least one optional)`

**Example**: `/keywords [remote|online], linux, python`
- ✅ "Remote Linux administrator" → has required + optional
- ✅ "Online Python developer" → has required + optional  
- ❌ "Linux administrator in NYC" → missing required
- ❌ "Remote project manager" → missing optional

## 📺 Enhanced Channel Management

### Supported Input Formats

The bot accepts channels in multiple formats:

```bash
# Username formats
@channelname
@techjobs

# Telegram links
t.me/channelname
t.me/techjobs
https://t.me/techjobs

# Private channel invites
t.me/joinchat/AbCdEf123456
https://t.me/joinchat/AbCdEf123456

# Direct chat IDs
-1001234567890
```

### Admin Channel Management

```bash
# Add channels (all formats supported)
/admin add_bot_channel @techjobs
/admin add_bot_channel t.me/remotework
/admin add_bot_channel https://t.me/startupjobs
/admin add_user_channel -1001234567890

# List channels with friendly names
/admin channels

# Remove channels
/admin remove_channel -1001234567890

# Update usernames when channels rename
/admin update_username -1001234567890 @newtechjobs
```

### Channel Types

- **Bot Channels**: Bot monitors as admin, forwards messages
- **User Channels**: User account monitors, forwards via bot (requires user credentials)

### What Happens When Channels Rename

1. **Bot keeps working** - uses permanent `chat_id` for processing
2. **Display might be outdated** - shows old username in logs
3. **Admin updates it**: `/admin update_username -1001234567890 @newname`
4. **Everything updated** - logs and admin panel show new username

## 🌐 Multi-Language Support

### Supported Languages

- **English** (en) - Default
- **Russian** (ru) - Русский

### Language Management

```bash
# Users can change language via /start menu or
# Bot automatically detects user preference

# All admin commands remain in English for consistency
```

### Adding New Languages

1. Edit `data/config/languages.json`
2. Add language to `supported_languages`
3. Add translations for all keys in `translations`
4. Restart bot

## 🏗️ Database Architecture

### Enhanced Schema

```sql
-- Channels with enhanced metadata
monitored_channels:
  chat_id (INTEGER)     -- Permanent Telegram ID
  username (TEXT)       -- Current @username (can change)
  type (TEXT)          -- 'bot' or 'user'
  status (TEXT)        -- 'active' or 'inactive'
  added_at (TEXT)      -- When added
  last_updated (TEXT)  -- Last username update

-- Users with language preferences  
users:
  id (INTEGER)         -- Telegram user ID
  language (TEXT)      -- Preferred language
  created_at (TEXT)    -- Registration date
  last_active (TEXT)   -- Last interaction
  total_forwards (INT) -- Message count

-- Keywords and ignore lists
user_keywords, user_ignore_keywords:
  user_id, keyword, created_at
```

### Performance Optimizations

- **Connection Pooling**: 10 concurrent database connections
- **WAL Journaling**: Better concurrency and crash recovery
- **Optimized Indexes**: Fast keyword and user lookups
- **Memory Mapping**: 256MB mmap for better performance

### Export/Import Formats

**Enhanced JSON Format:**
```json
{
  "channels": [
    {
      "chat_id": -1001234567890,
      "username": "@techjobs"
    }
  ],
  "format_version": "2.0"
}
```

## 🔧 Advanced Configuration

### Environment Variables

```bash
# Required
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Optional - Admin features
AUTHORIZED_ADMIN_ID=your_telegram_user_id

# Optional - User account monitoring
API_ID=12345678
API_HASH=your_api_hash_here  
PHONE_NUMBER=+1234567890

# Optional - Performance tuning
DATABASE_PATH=/app/data/bot.db
LOG_LEVEL=INFO
BACKUP_RETENTION_COUNT=5
```

### User Account Monitoring

For advanced channel monitoring (private channels, better access):

1. Get API credentials from [my.telegram.org](https://my.telegram.org/auth)
2. Add to `bot-secrets.env`:
   ```bash
   API_ID=your_api_id
   API_HASH=your_api_hash
   PHONE_NUMBER=+1234567890
   ```
3. Bot will prompt for SMS verification code
4. Enables monitoring of private channels and auto-join features

## 🚀 Performance Features

### Scaling Capabilities

| Users | Memory | Response Time | Status |
|-------|--------|---------------|---------|
| 0-1,000 | <50MB | <5ms | ✅ Excellent |
| 1,000-5,000 | <60MB | <10ms | ✅ Great |
| 5,000-10,000 | <80MB | <15ms | ✅ Good |
| 10,000+ | <100MB | <20ms | ⚠️ Monitor |

### Rate Limiting

- **Message Forwarding**: 0.5s delay between forwards
- **Telegram API**: Built-in respect for API limits
- **Error Recovery**: Graceful handling of network issues

### Database Maintenance

```bash
# Check database size and performance
docker exec job-collector-bot ls -la /app/data/

# View performance stats in logs
docker logs job-collector-bot | grep "SQLite initialized"

# Monitor forwarding activity
docker logs job-collector-bot | grep "FORWARD"
```

## 🔍 Advanced Admin Features

### Database Queries

```bash
# View all users and their keywords
docker exec job-collector-bot sqlite3 -header -column /app/data/bot.db "
SELECT 
    u.id as 'User_ID',
    u.language as 'Lang',
    COALESCE(GROUP_CONCAT(DISTINCT uk.keyword, ', '), 'None') as 'Keywords',
    COALESCE(GROUP_CONCAT(DISTINCT uik.keyword, ', '), 'None') as 'Ignore_Words'
FROM users u 
LEFT JOIN user_keywords uk ON u.id = uk.user_id 
LEFT JOIN user_ignore_keywords uik ON u.id = uik.user_id 
GROUP BY u.id 
ORDER BY u.id;
"
```

### Error Monitoring

```bash
# View recent errors (if admin ID configured)
/admin errors

# Check system health
/admin health

# View detailed statistics
/admin stats
```

### Backup Management

```bash
# Create manual backup (never auto-deleted)
/admin backup_manual

# List all backups
/admin list_backups

# Export current configuration
/admin export

# Import from configuration files
/admin import
```

## 🎛️ Customization

### Custom Keyword Logic

Modify `src/matching/keywords.py` to add custom matching patterns:

```python
def custom_match_pattern(self, text: str, pattern: str) -> bool:
    # Add your custom matching logic here
    pass
```

### Custom Commands

Add new commands in `src/handlers/commands.py`:

```python
async def custom_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Your custom command logic
    pass
```

### Custom Languages

Add new language in `data/config/languages.json`:

```json
{
  "supported_languages": {
    "es": {"name": "Español", "flag": "🇪🇸"}
  },
  "translations": {
    "welcome_message": {
      "es": "¡Bienvenido al Bot de Trabajos!"
    }
  }
}
```

## 🔗 Integration Features

### Webhook Support

For high-volume deployments, switch to webhook mode:

```python
# In bot.py
if os.getenv('WEBHOOK_URL'):
    app.run_webhook(webhook_url=os.getenv('WEBHOOK_URL'))
else:
    app.run_polling()
```

### External APIs

Connect to job boards or external services:

```python
# Example: Integration with external job API
async def fetch_external_jobs():
    # Your API integration code
    pass
```

### Monitoring Integration

Connect to monitoring systems:

```bash
# Prometheus metrics endpoint
curl localhost:8080/metrics

# Health check endpoint  
curl localhost:8080/health
```

This covers all the advanced features available in the enhanced job collector bot!