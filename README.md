# 🤖 Telegram Job Collector Bot

A simple Docker-based Telegram bot that collects job postings from multiple channels and forwards them to users based on keywords.

## ✨ Features

- 🕐 **Realtime Collection**: Forwards the job posts immediately as they appear
- 🎯 **Keyword Matching**: Users set their own job search keywords
- 📨 **Smart Forwarding**: Automatically forwards matching jobs to users
- 🐳 **Docker Ready**: Complete containerized deployment
- 🔧 **Easy Configuration**: Simple JSON config files

## 🚀 Quick Start

1. **Create your bot** with [@BotFather](https://t.me/botfather)
2. **Clone this repo**: `git clone https://github.com/red8192cat/telegram-job-collector.git`
3. **Configure**: Copy example files and add your settings
4. **Deploy**: `docker-compose up -d`

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

## 📋 User Commands

- `/keywords python, javascript, remote` - Set job search keywords
- `/add_keyword_to_list django` - Add one keyword
- `/delete_keyword_from_list php` - Remove one keyword
- `/purge_list` - Clear all keywords
- `/my_keywords` - Show current keywords
- `/help` - Show help message

## 🔧 Configuration

The bot uses two simple config files:

**`.env`** - Your bot token:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

**`config.json`** - Channels to monitor:
```json
{
  "channels": [
    "@jobschannel",
    "@hiringchannel",
    "-1001234567890"
  ]
}
```

## 🐳 Docker Deployment

```bash
# Copy example configs
cp .env.example .env
cp config.json.example config.json

# Edit your settings
nano .env
nano config.json

# Deploy
docker-compose up -d
```

## 📁 Project Structure

```
telegram-job-collector/
├── README.md
├── DEPLOYMENT.md
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── config.json.example
├── src/
│   └── bot.py
└── docs/
    └── TROUBLESHOOTING.md
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 💡 Support

- 📖 Read the [deployment guide](DEPLOYMENT.md)
- 🔍 Check [troubleshooting](docs/TROUBLESHOOTING.md)
- 🐛 Report issues on GitHub

---
⭐ If this project helped you, please give it a star!
