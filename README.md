# 🤖 Telegram Job Collector Bot

A smart Telegram bot that automatically forwards job postings from monitored channels to users based on their custom keywords with advanced filtering capabilities.

## ✨ Features

- 🎯 **Advanced Keyword Matching** - Single words, AND logic, exact phrases, and wildcards
- 🚫 **Smart Ignore Filters** - Block unwanted job postings with ignore keywords
- 🔄 **Auto Channel Monitoring** - Real-time job forwarding from configured channels
- 🔒 **Private Only** - Bot only responds in private chats, never in groups
- ⚙️ **Auto Configuration Reload** - Updates channel list every hour without restart
- 💬 **Interactive Interface** - User-friendly buttons and comprehensive help

## 🚀 Quick Start

1. **Get Bot Token**
   ```bash
   # Create bot with @BotFather and get token
   ```

2. **Deploy with Docker**
   ```bash
   git clone https://github.com/yourusername/telegram-job-collector.git
   cd telegram-job-collector
   cp .env.example .env
   cp config.json.example config.json
   # Edit .env and config.json with your settings
   docker-compose up -d
   ```

3. **Configure Channels**
   ```json
   {
     "channels": [
       "@jobschannel",
       "@hiringchannel", 
       "-1001234567890"
     ]
   }
   ```

## 🎯 Keyword System

### Keyword Types

| Type | Syntax | Example | Matches |
|------|--------|---------|---------|
| **Single** | `word` | `python` | "Python developer needed" |
| **AND Logic** | `word1+word2` | `python+remote` | "Remote Python developer" |
| **Exact Phrase** | `"phrase"` | `"project manager"` | "Project manager role" (exact order) |
| **Wildcard** | `word*` | `develop*` | developer, development, developing |
| **Multi-Wildcard** | `"word1* word2*"` | `"support* engineer*"` | "Support Engineer", "Supporting Engineering" |

### Setting Keywords

```bash
# Set keywords (overwrites existing)
/keywords python, remote, "data scientist"

# Complex patterns
/keywords python+remote, "project manag*", develop*+senior

# Add individual keywords
/add_keyword_to_list react+typescript

# Remove keywords
/delete_keyword_from_list python
```

### Ignore Keywords

```bash
# Block unwanted jobs
/ignore_keywords java, senior, "team lead"

# Complex ignore patterns
/ignore_keywords java+senior, "project manag*"

# Clear all ignore keywords
/purge_ignore
```

## 📋 User Commands

### Keywords Management
- `/keywords <list>` - Set search keywords (overwrites current list)
- `/add_keyword_to_list <keyword>` - Add a single keyword
- `/delete_keyword_from_list <keyword>` - Remove a keyword
- `/my_keywords` - Show current keywords

### Ignore Keywords
- `/ignore_keywords <list>` - Set ignore keywords (overwrites current list) 
- `/add_ignore_keyword <keyword>` - Add ignore keyword
- `/delete_ignore_keyword <keyword>` - Remove ignore keyword
- `/my_ignore` - Show ignore keywords
- `/purge_ignore` - Clear all ignore keywords

### General
- `/start` - Welcome message and main menu
- `/menu` - Show interactive button menu
- `/help` - Complete help with examples

## 📁 Project Structure

```
telegram-job-collector/
├── README.md                 # This file
├── docker-compose.yml        # Docker deployment config
├── Dockerfile               # Container definition
├── requirements.txt         # Python dependencies
├── .env.example            # Environment variables template
├── config.json.example     # Channel configuration template
├── src/
│   └── bot.py              # Main bot application
└── data/                   # Persistent data storage
    ├── user_keywords.json         # User search keywords
    ├── user_ignore_keywords.json  # User ignore patterns
    └── last_menu_set.txt          # Bot menu rate limit tracking
```

## 💾 Data Storage

All user data is stored in `/data` directory:

### `user_keywords.json`
```json
{
  "123456789": ["python+remote", "\"data scientist\"", "develop*"],
  "987654321": ["react", "javascript+senior"]
}
```

### `user_ignore_keywords.json`
```json
{
  "123456789": ["java", "php+senior", "\"team lead*\""],
  "987654321": ["management"]
}
```

### Volume Mapping
```yaml
volumes:
  - ./data:/app/data  # Persists user data across container restarts
  - ./config.json:/app/config.json  # Live channel configuration
```

## ⚙️ Configuration

### Environment Variables (`.env`)
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

### Channel Configuration (`config.json`)
```json
{
  "channels": [
    "@publicchannel",        # Public channel username
    "@anotherchannel",       # Another public channel
    "-1001234567890"         # Private channel/group ID
  ]
}
```

**Note:** Channel list reloads automatically every hour - no restart needed!

## 🔧 Advanced Features

### Real-time Processing
- Messages are forwarded **immediately** when posted to monitored channels
- No polling delays or batch processing

### Smart Filtering
- **Private chat only** - Never forwards to groups or channels
- **Duplicate prevention** - Won't forward to same user multiple times
- **Rate limiting protection** - Built-in delays to avoid Telegram limits

### Auto-Updates
- **Channel monitoring** - Automatically picks up new channels from config
- **Persistent storage** - All user preferences saved across restarts
- **Error recovery** - Gracefully handles API limits and network issues

## 🚀 Deployment

### Docker (Recommended)
```bash
docker-compose up -d          # Start in background
docker-compose logs -f        # View logs
docker-compose restart        # Restart bot
```

### Manual Updates
```bash
# Update channel list without restart
nano config.json             # Edit channels
# Bot automatically reloads within 1 hour

# Update bot code
docker-compose up -d --build  # Rebuild and restart
```

## 📊 Monitoring

```bash
# View logs
docker logs job-collector-bot

# Check if bot is forwarding
docker logs job-collector-bot | grep "Forwarded job"

# Monitor channel processing  
docker logs job-collector-bot | grep "Processing message"
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

⭐ **Star this repo if it helped you land your dream job!**