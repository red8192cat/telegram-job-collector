# 🚀 Telegram Job Bot - Deployment Manual

## Prerequisites
- A computer with Docker installed
- A Telegram account
- Basic file editing skills

## Step 1: Create Your Telegram Bot

1. Open Telegram and find **@BotFather**
2. Send `/newbot` to BotFather
3. Choose a name for your bot (e.g., "Job Collector Bot")
4. Choose a username (must end with 'bot', e.g., "myjobcollector_bot")
5. **SAVE THE TOKEN** - it looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

## Step 2: Configure Your Bot

### Create Environment File
1. Copy the example file: `cp .env.example .env`
2. Open `.env` with any text editor
3. Replace the example token with your actual bot token
4. Save the file

### Configure Channels to Monitor
1. Copy the example file: `cp config.json.example config.json`
2. Edit with your actual channels
3. Add bot as admin to all channels

## Step 3: Deploy

```bash
docker-compose up -d
```

See full documentation for complete setup instructions.
