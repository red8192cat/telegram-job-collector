# 🤖 Telegram Job Collector Bot

A smart Telegram bot that automatically forwards job postings from monitored channels to users based on their custom keywords with advanced filtering capabilities and modular architecture.

## ✨ Features

- 🎯 **Advanced Keyword Matching** - Required keywords, OR logic, AND logic, exact phrases, and wildcards
- 🚫 **Smart Ignore Filters** - Block unwanted job postings with ignore keywords
- 🔄 **Auto Channel Monitoring** - Real-time job forwarding from configured channels
- 🔒 **Private Only** - Bot only responds in private chats, never in groups
- ⚙️ **Auto Configuration Reload** - Updates channel list every hour without restart
- 💬 **Interactive Interface** - User-friendly buttons and comprehensive help
- 🏗️ **Modular Architecture** - Clean, maintainable codebase for easy development

## 🚀 Quick Start

1. **Get Bot Token**
   ```bash
   # Create bot with @BotFather and get token
   ```

2. **Deploy with Docker**
   ```bash
   git clone https://github.com/red8192cat/telegram-job-collector.git
   cd telegram-job-collector
   cp .env.example .env
   cp config.json.example config.json
   # Edit .env and config.json with your settings
   docker-compose up -d
   ```

3. **Add Bot to Channels**
   ```bash
   # For each channel in config.json:
   # 1. Add @Find_Me_A_Perfect_Job_bot as admin to the channel/group
   # 2. Grant "Read Messages" permission (minimum required)
   # 3. Bot will automatically start monitoring
   ```

4. **Configure Channels**
   ```json
   {
     "channels": [
       "@jobschannel",
       "@hiringchannel", 
       "-1001234567890"
     ]
   }
   ```

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

### Advanced Examples

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

## 🏗️ Project Structure

```
telegram-job-collector/
├── README.md                    # This file
├── docker-compose.yml           # Docker deployment config
├── Dockerfile                   # Container definition
├── requirements.txt             # Python dependencies
├── .env.example                # Environment variables template
├── config.json.example         # Channel configuration template
├── src/                        # Source code
│   ├── bot.py                  # Main application entry point
│   ├── handlers/               # Request handlers
│   │   ├── __init__.py
│   │   ├── commands.py         # All bot commands (/start, /keywords, etc.)
│   │   ├── callbacks.py        # Menu button interactions
│   │   └── messages.py         # Channel message processing & forwarding
│   ├── matching/               # Keyword matching engine
│   │   ├── __init__.py
│   │   └── keywords.py         # Advanced pattern matching logic
│   ├── storage/                # Data persistence
│   │   ├── __init__.py
│   │   └── data_manager.py     # File I/O and user data management
│   └── utils/                  # Utilities and configuration
│       ├── __init__.py
│       ├── config.py           # Configuration file management
│       └── helpers.py          # Menu creation and helper functions
└── data/                       # Persistent data storage (Docker volume)
    ├── user_keywords.json      # User search keywords
    ├── user_ignore_keywords.json # User ignore patterns
    └── last_menu_set.txt       # Bot menu rate limit tracking
```

## 💾 Data Storage

All user data is stored in `/data` directory:

### `user_keywords.json`
```json
{
  "123456789": ["[remote|online]", "python+django", "\"data scientist\""],
  "987654321": ["[remote]", "react", "javascript+senior"]
}
```

### `user_ignore_keywords.json`
```json
{
  "123456789": ["java", "php+senior", "\"team lead*\""],
  "987654321": ["management", "onsite"]
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

**⚠️ Important:** The bot must be added as an **admin** to each channel/group with at least **"Read Messages"** permission to monitor job postings.

### Bot Permissions Setup

1. **For Public Channels:**
   - Add `@Find_Me_A_Perfect_Job_bot` as admin
   - Grant minimum permission: "Read Messages"

2. **For Private Groups:**
   - Add bot to the group
   - Promote to admin with "Read Messages" permission
   - Get group ID from bot logs or use [@userinfobot](https://t.me/userinfobot)

3. **Permission Verification:**
   ```bash
   # Check bot logs to verify channel access
   docker logs job-collector-bot | grep "Processing message from channel"
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

## 🔧 Development

### Modular Architecture Benefits

1. **Easy Maintenance** - Each component has a single responsibility
2. **Simple Debugging** - Find issues quickly in the right module
3. **Clean Testing** - Test keyword matching independently of commands
4. **Fast Development** - Add features without touching core logic
5. **Team Collaboration** - Multiple developers can work on different modules

### Adding New Features

```bash
# Add new commands
edit src/handlers/commands.py

# Modify keyword logic
edit src/matching/keywords.py

# Update data storage
edit src/storage/data_manager.py

# Add configuration options
edit src/utils/config.py
```

### Running Tests

```bash
# Test keyword matching
python -m pytest tests/test_keywords.py

# Test full bot functionality
docker-compose up -d --build
./test_bot.sh
```

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Add docstrings to all public methods
- Keep modules focused and cohesive
- Write tests for new functionality

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

⭐ **Star this repo if it helped you land your dream job!**