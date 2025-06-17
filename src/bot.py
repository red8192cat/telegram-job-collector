#!/usr/bin/env python3
"""
Telegram Job Collector Bot
Collects job postings from configured channels and reposts to user groups
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Set

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class JobCollectorBot:
    def __init__(self, token: str):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.user_keywords = {}  # {chat_id: [keywords]}
        self.channels_to_monitor = []
        self.job_keywords = ['job', 'hiring', 'vacancy', 'position', 'remote', 'work', 'developer', 'engineer', 'programmer']
        
        # Load configuration
        self.load_config()
        self.load_user_keywords()
        
        # Register handlers
        self.register_handlers()
    
    def load_config(self):
        """Load channels to monitor from config file"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                self.channels_to_monitor = config.get('channels', [])
                logger.info(f"Loaded {len(self.channels_to_monitor)} channels to monitor")
        except FileNotFoundError:
            logger.warning("config.json not found, using empty channel list")
            self.channels_to_monitor = []
    
    def load_user_keywords(self):
        """Load user keywords from file"""
        try:
            with open('data/user_keywords.json', 'r') as f:
                self.user_keywords = json.load(f)
                # Convert string keys back to int
                self.user_keywords = {int(k): v for k, v in self.user_keywords.items()}
                logger.info(f"Loaded keywords for {len(self.user_keywords)} users")
        except FileNotFoundError:
            logger.info("user_keywords.json not found, starting with empty user list")
            self.user_keywords = {}
    
    def save_user_keywords(self):
        """Save user keywords to file"""
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/user_keywords.json', 'w') as f:
                json.dump(self.user_keywords, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save user keywords: {e}")
    
    def register_handlers(self):
        """Register command handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("keywords", self.set_keywords_command))
        self.app.add_handler(CommandHandler("add_keyword_to_list", self.add_keyword_command))
        self.app.add_handler(CommandHandler("delete_keyword_from_list", self.delete_keyword_command))
        self.app.add_handler(CommandHandler("purge_list", self.purge_keywords_command))
        self.app.add_handler(CommandHandler("my_keywords", self.show_keywords_command))
        
        # Add message handler to process channel messages in real-time
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_channel_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_msg = (
            "🤖 Welcome to Job Collector Bot!\n\n"
            "I help you collect job postings from configured channels.\n"
            "Use /help to see available commands."
        )
        await update.message.reply_text(welcome_msg)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_msg = (
            "📋 Available Commands:\n\n"
            "/keywords <word1, word2, ...> - Set your job keywords\n"
            "/add_keyword_to_list <keyword> - Add a keyword to your list\n"
            "/delete_keyword_from_list <keyword> - Remove a keyword\n"
            "/purge_list - Clear all your keywords\n"
            "/my_keywords - Show your current keywords\n"
            "/help - Show this help message\n\n"
            "💡 The bot monitors configured channels and forwards matching jobs automatically."
        )
        await update.message.reply_text(help_msg)
    
    async def set_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /keywords command"""
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide keywords: /keywords python, javascript, remote")
            return
        
        # Parse keywords from arguments
        keywords_text = ' '.join(context.args)
        keywords = [k.strip().lower() for k in keywords_text.split(',') if k.strip()]
        
        if not keywords:
            await update.message.reply_text("No valid keywords provided!")
            return
        
        self.user_keywords[chat_id] = keywords
        self.save_user_keywords()
        
        keywords_str = ', '.join(keywords)
        await update.message.reply_text(f"✅ Keywords set: {keywords_str}")
    
    async def add_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_keyword_to_list command"""
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide a keyword: /add_keyword_to_list python")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if chat_id not in self.user_keywords:
            self.user_keywords[chat_id] = []
        
        if keyword not in self.user_keywords[chat_id]:
            self.user_keywords[chat_id].append(keyword)
            self.save_user_keywords()
            await update.message.reply_text(f"✅ Added keyword: {keyword}")
        else:
            await update.message.reply_text(f"Keyword '{keyword}' already in your list!")
    
    async def delete_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_keyword_from_list command"""
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide a keyword: /delete_keyword_from_list python")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if chat_id in self.user_keywords and keyword in self.user_keywords[chat_id]:
            self.user_keywords[chat_id].remove(keyword)
            self.save_user_keywords()
            await update.message.reply_text(f"✅ Removed keyword: {keyword}")
        else:
            await update.message.reply_text(f"Keyword '{keyword}' not found in your list!")
    
    async def purge_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /purge_list command"""
        chat_id = update.effective_chat.id
        
        if chat_id in self.user_keywords:
            del self.user_keywords[chat_id]
            self.save_user_keywords()
            await update.message.reply_text("✅ All keywords cleared!")
        else:
            await update.message.reply_text("You don't have any keywords set!")
    
    async def show_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_keywords command"""
        chat_id = update.effective_chat.id
        
        if chat_id in self.user_keywords and self.user_keywords[chat_id]:
            keywords_str = ', '.join(self.user_keywords[chat_id])
            await update.message.reply_text(f"📝 Your keywords: {keywords_str}")
        else:
            await update.message.reply_text("You haven't set any keywords yet!")
    
    def is_job_message(self, message_text: str) -> bool:
        """Check if message contains job-related keywords"""
        text_lower = message_text.lower()
        return any(keyword in text_lower for keyword in self.job_keywords)
    
    def matches_user_keywords(self, message_text: str, user_keywords: List[str]) -> bool:
        """Check if message matches user's keywords"""
        text_lower = message_text.lower()
        return any(keyword in text_lower for keyword in user_keywords)
    
    async def handle_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages from monitored channels"""
        message = update.message
        if not message or not message.text:
            return
        
        # Check if message is from a monitored channel
        chat_id = message.chat.id
        channel_username = f"@{message.chat.username}" if message.chat.username else str(chat_id)
        
        if channel_username not in self.channels_to_monitor and str(chat_id) not in self.channels_to_monitor:
            return
        
        logger.info(f"Processing message from channel: {channel_username}")
        
        # Check if it's a job-related message
        if not self.is_job_message(message.text):
            logger.info("Message doesn't contain job keywords")
            return
        
        # Check against each user's keywords and forward if matches
        for user_chat_id, keywords in self.user_keywords.items():
            if self.matches_user_keywords(message.text, keywords):
                try:
                    # Forward the message directly to the user's private chat
                    await context.bot.forward_message(
                        chat_id=user_chat_id,
                        from_chat_id=chat_id,
                        message_id=message.message_id
                    )
                    logger.info(f"Forwarded job to user {user_chat_id}")
                    
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)
                    
                except TelegramError as e:
                    logger.error(f"Failed to forward to user {user_chat_id}: {e}")
    
    async def collect_and_repost_jobs(self):
        """Manual job collection function for scheduled runs"""
        logger.info("Starting manual job collection...")
        
        if not self.channels_to_monitor:
            logger.warning("No channels configured to monitor")
            return
        
        if not self.user_keywords:
            logger.info("No users have set keywords yet")
            return
        
        # Get messages from the last 12 hours
        since_time = datetime.now() - timedelta(hours=12)
        
        for channel in self.channels_to_monitor:
            try:
                logger.info(f"Checking channel: {channel}")
                
                # Get recent messages from channel using get_chat_history
                try:
                    messages = []
                    async for message in context.bot.get_chat_history(
                        chat_id=channel,
                        limit=50
                    ):
                        if message.date > since_time and message.text:
                            messages.append(message)
                    
                    for message in messages:
                        # Check if it's a job-related message
                        if not self.is_job_message(message.text):
                            continue
                        
                        # Check against each user's keywords
                        for user_chat_id, keywords in self.user_keywords.items():
                            if self.matches_user_keywords(message.text, keywords):
                                try:
                                    # Forward the message directly to the user's private chat
                                    await self.app.bot.forward_message(
                                        chat_id=user_chat_id,
                                        from_chat_id=channel,
                                        message_id=message.message_id
                                    )
                                    logger.info(f"Forwarded job to user {user_chat_id}")
                                    
                                    # Small delay to avoid rate limiting
                                    await asyncio.sleep(0.5)
                                    
                                except TelegramError as e:
                                    logger.error(f"Failed to forward to user {user_chat_id}: {e}")
                
                except Exception as e:
                    logger.error(f"Failed to get messages from {channel}: {e}")
                
            except Exception as e:
                logger.error(f"Error processing channel {channel}: {e}")
        
        logger.info("Manual job collection completed")
    
    async def run_scheduled_job(self):
        """Run the scheduled job collection"""
        try:
            await self.app.initialize()
            await self.collect_and_repost_jobs()
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")
        finally:
            await self.app.shutdown()

def main():
    """Main function"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    bot = JobCollectorBot(token)
    
    # Check if we should run the scheduled job
    run_mode = os.getenv('RUN_MODE', 'webhook')
    
    if run_mode == 'scheduled':
        # Run job collection once and exit
        asyncio.run(bot.run_scheduled_job())
    else:
        # Run as webhook bot
        logger.info("Starting bot in webhook mode...")
        bot.app.run_polling()

if __name__ == '__main__':
    main()