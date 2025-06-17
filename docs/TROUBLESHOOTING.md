# 🔧 Troubleshooting Guide

## Common Issues and Solutions

### Bot Not Responding
- Check if bot token is correct in `.env` file
- Verify containers are running: `docker-compose ps`
- Check bot logs: `docker-compose logs telegram-bot`

### No Jobs Being Collected
- Verify bot is admin in monitoring channels
- Check channel names/IDs are correct in config.json
- Users must set keywords with `/keywords` command

### Jobs Not Being Forwarded
- Add bot as admin in user groups
- Check users have set keywords correctly
- Monitor logs for rate limiting issues

## Getting Help

Check logs: `docker-compose logs`
Restart: `docker-compose restart`
Reset: `docker-compose down && docker-compose up -d`
