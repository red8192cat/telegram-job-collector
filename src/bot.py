#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot
Collects job postings from configured channels and reposts to user groups
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Set

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
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
        self.user_ignore_keywords = {}  # {chat_id: [ignore_keywords]}
        self.channels_to_monitor = []
        self.job_keywords = ['job', 'hiring', 'vacancy', 'position', 'remote', 'work', 'developer', 'engineer', 'programmer']
        
        # Load configuration
        self.load_config()
        self.load_user_data()
        
        # Register handlers
        self.register_handlers()
    
    def load_config(self):
        """Load channels to monitor from config file"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                old_channels = self.channels_to_monitor.copy()
                self.channels_to_monitor = config.get('channels', [])
                
                if old_channels != self.channels_to_monitor:
                    logger.info(f"Updated channels: {len(self.channels_to_monitor)} channels to monitor")
                    
        except FileNotFoundError:
            logger.warning("config.json not found, using empty channel list")
            self.channels_to_monitor = []
    
    def load_user_data(self):
        """Load all user data from files"""
        # Load keywords
        try:
            with open('data/user_keywords.json', 'r') as f:
                self.user_keywords = json.load(f)
                self.user_keywords = {int(k): v for k, v in self.user_keywords.items()}
        except FileNotFoundError:
            logger.info("user_keywords.json not found, starting with empty user list")
            self.user_keywords = {}
        
        # Load ignore keywords
        try:
            with open('data/user_ignore_keywords.json', 'r') as f:
                self.user_ignore_keywords = json.load(f)
                self.user_ignore_keywords = {int(k): v for k, v in self.user_ignore_keywords.items()}
        except FileNotFoundError:
            logger.info("user_ignore_keywords.json not found, starting with empty ignore list")
            self.user_ignore_keywords = {}
    
    def save_user_data(self):
        """Save all user data to files"""
        try:
            os.makedirs('data', exist_ok=True)
            
            # Save keywords
            with open('data/user_keywords.json', 'w') as f:
                json.dump(self.user_keywords, f, indent=2)
            
            # Save ignore keywords
            with open('data/user_ignore_keywords.json', 'w') as f:
                json.dump(self.user_ignore_keywords, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save user data: {e}")
    
    async def start_config_reload_task(self):
        """Start the config reload background task"""
        async def reload_task():
            while True:
                await asyncio.sleep(3600)  # 1 hour
                logger.info("Reloading configuration...")
                self.load_config()
        
        # Start the task
        asyncio.create_task(reload_task())
        logger.info("Config reload task started")
    
    def is_private_chat(self, update: Update) -> bool:
        """Check if message is from private chat"""
        return update.effective_chat.type == 'private'
    
    def check_user_limit(self, chat_id: int) -> bool:
        """Check if user has reached daily limit"""
        # All users are premium now
        return True
    
    def increment_user_usage(self, chat_id: int):
        """Increment user's daily usage count"""
        # No usage tracking needed since all users are premium
        pass
    
    def create_main_menu(self):
        """Create main menu keyboard"""
        keyboard = [
            [InlineKeyboardButton("🎯 Set Keywords", callback_data="menu_keywords")],
            [InlineKeyboardButton("🚫 Set Ignore Keywords", callback_data="menu_ignore")],
            [InlineKeyboardButton("📝 My Keywords", callback_data="menu_show_keywords"),
             InlineKeyboardButton("📋 My Ignore List", callback_data="menu_show_ignore")],
            [InlineKeyboardButton("💬 Contact Admin", callback_data="menu_contact")],
            [InlineKeyboardButton("❓ Help", callback_data="menu_help")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def register_handlers(self):
        """Register command handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("menu", self.menu_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("keywords", self.set_keywords_command))
        self.app.add_handler(CommandHandler("ignore_keywords", self.set_ignore_keywords_command))
        self.app.add_handler(CommandHandler("add_keyword_to_list", self.add_keyword_command))
        self.app.add_handler(CommandHandler("delete_keyword_from_list", self.delete_keyword_command))
        self.app.add_handler(CommandHandler("add_ignore_keyword", self.add_ignore_keyword_command))
        self.app.add_handler(CommandHandler("delete_ignore_keyword", self.delete_ignore_keyword_command))
        self.app.add_handler(CommandHandler("purge_list", self.purge_keywords_command))
        self.app.add_handler(CommandHandler("purge_ignore", self.purge_ignore_keywords_command))
        self.app.add_handler(CommandHandler("my_keywords", self.show_keywords_command))
        self.app.add_handler(CommandHandler("my_ignore", self.show_ignore_keywords_command))
        
        # Callback query handler for menu buttons
        self.app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Add message handler to process channel messages in real-time
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_channel_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self.is_private_chat(update):
            return
        
        welcome_msg = (
            "🤖 Welcome to Job Collector Bot!\n\n"
            "I help you collect job postings from configured channels based on your keywords.\n\n"
            "✅ All users get unlimited job forwards\n"
            "✅ Advanced keyword filtering with ignore list\n\n"
            "Use the menu below to get started:"
        )
        await update.message.reply_text(welcome_msg, reply_markup=self.create_main_menu())
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command"""
        if not self.is_private_chat(update):
            return
        
        await update.message.reply_text("📋 Main Menu:", reply_markup=self.create_main_menu())
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self.is_private_chat(update):
            return
        
        help_msg = (
            "📋 Available Commands:\n\n"
            "🎯 Keywords Management:\n"
            "/keywords <word1, word2, ...> - Set your job keywords\n"
            "/add_keyword_to_list <keyword> - Add a keyword\n"
            "/delete_keyword_from_list <keyword> - Remove a keyword\n"
            "/my_keywords - Show your current keywords\n"
            "/purge_list - Clear all keywords\n\n"
            "🚫 Ignore Keywords:\n"
            "/ignore_keywords <word1, word2, ...> - Set ignore keywords\n"
            "/add_ignore_keyword <keyword> - Add ignore keyword\n"
            "/delete_ignore_keyword <keyword> - Remove ignore keyword\n"
            "/my_ignore - Show ignore keywords\n"
            "/purge_ignore - Clear ignore list\n\n"
            "📊 Other Commands:\n"
            "/menu - Show interactive menu\n"
            "/help - Show this help message\n\n"
            "💡 The bot monitors configured channels and forwards matching jobs automatically.\n"
            "🎯 Ignore keywords help filter out unwanted jobs (e.g., 'java' to avoid when searching 'javascript')."
        )
        await update.message.reply_text(help_msg)
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "menu_keywords":
            msg = "🎯 To set keywords, use:\n/keywords python, javascript, remote"
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
        
        elif query.data == "menu_ignore":
            msg = "🚫 To set ignore keywords, use:\n/ignore_keywords java, php, senior"
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
        
        elif query.data == "menu_show_keywords":
            chat_id = query.from_user.id
            if chat_id in self.user_keywords and self.user_keywords[chat_id]:
                keywords_str = ', '.join(self.user_keywords[chat_id])
                msg = f"📝 Your keywords: {keywords_str}"
            else:
                msg = "You haven't set any keywords yet!"
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
        
        elif query.data == "menu_show_ignore":
            chat_id = query.from_user.id
            if chat_id in self.user_ignore_keywords and self.user_ignore_keywords[chat_id]:
                ignore_str = ', '.join(self.user_ignore_keywords[chat_id])
                msg = f"🚫 Your ignore keywords: {ignore_str}"
            else:
                msg = "You haven't set any ignore keywords yet!"
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
        
        elif query.data == "menu_contact":
            await self.show_contact_info(query)
        
        elif query.data == "menu_help":
            await query.edit_message_text("📋 Use /help to see all available commands!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
        
        elif query.data == "menu_back":
            await query.edit_message_text("📋 Main Menu:", reply_markup=self.create_main_menu())
    
    async def show_contact_info(self, query):
        """Show contact information"""
        msg = (
            "💬 Need Help?\n\n"
            "For support, questions, or feedback:\n\n"
            "👤 Contact the admin mentioned in the bot description\n\n"
            "We're here to help! 😊"
        )
        
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
    
    async def set_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /keywords command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide keywords: /keywords python, javascript, remote")
            return
        
        keywords_text = ' '.join(context.args)
        keywords = [k.strip().lower() for k in keywords_text.split(',') if k.strip()]
        
        if not keywords:
            await update.message.reply_text("No valid keywords provided!")
            return
        
        self.user_keywords[chat_id] = keywords
        self.save_user_data()
        
        keywords_str = ', '.join(keywords)
        await update.message.reply_text(f"✅ Keywords set: {keywords_str}")
    
    async def set_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ignore_keywords command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide ignore keywords: /ignore_keywords java, senior, manager")
            return
        
        keywords_text = ' '.join(context.args)
        keywords = [k.strip().lower() for k in keywords_text.split(',') if k.strip()]
        
        if not keywords:
            await update.message.reply_text("No valid ignore keywords provided!")
            return
        
        self.user_ignore_keywords[chat_id] = keywords
        self.save_user_data()
        
        keywords_str = ', '.join(keywords)
        await update.message.reply_text(f"✅ Ignore keywords set: {keywords_str}")
    
    async def add_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_keyword_to_list command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide a keyword: /add_keyword_to_list python")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if chat_id not in self.user_keywords:
            self.user_keywords[chat_id] = []
        
        if keyword not in self.user_keywords[chat_id]:
            self.user_keywords[chat_id].append(keyword)
            self.save_user_data()
            await update.message.reply_text(f"✅ Added keyword: {keyword}")
        else:
            await update.message.reply_text(f"Keyword '{keyword}' already in your list!")
    
    async def add_ignore_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_ignore_keyword command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide an ignore keyword: /add_ignore_keyword java")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if chat_id not in self.user_ignore_keywords:
            self.user_ignore_keywords[chat_id] = []
        
        if keyword not in self.user_ignore_keywords[chat_id]:
            self.user_ignore_keywords[chat_id].append(keyword)
            self.save_user_data()
            await update.message.reply_text(f"✅ Added ignore keyword: {keyword}")
        else:
            await update.message.reply_text(f"Ignore keyword '{keyword}' already in your list!")
    
    async def delete_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_keyword_from_list command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide a keyword: /delete_keyword_from_list python")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if chat_id in self.user_keywords and keyword in self.user_keywords[chat_id]:
            self.user_keywords[chat_id].remove(keyword)
            self.save_user_data()
            await update.message.reply_text(f"✅ Removed keyword: {keyword}")
        else:
            await update.message.reply_text(f"Keyword '{keyword}' not found in your list!")
    
    async def delete_ignore_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_ignore_keyword command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide an ignore keyword: /delete_ignore_keyword java")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if chat_id in self.user_ignore_keywords and keyword in self.user_ignore_keywords[chat_id]:
            self.user_ignore_keywords[chat_id].remove(keyword)
            self.save_user_data()
            await update.message.reply_text(f"✅ Removed ignore keyword: {keyword}")
        else:
            await update.message.reply_text(f"Ignore keyword '{keyword}' not found in your list!")
    
    async def purge_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /purge_list command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if chat_id in self.user_keywords:
            del self.user_keywords[chat_id]
            self.save_user_data()
            await update.message.reply_text("✅ All keywords cleared!")
        else:
            await update.message.reply_text("You don't have any keywords set!")
    
    async def purge_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /purge_ignore command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if chat_id in self.user_ignore_keywords:
            del self.user_ignore_keywords[chat_id]
            self.save_user_data()
            await update.message.reply_text("✅ All ignore keywords cleared!")
        else:
            await update.message.reply_text("You don't have any ignore keywords set!")
    
    async def show_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_keywords command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if chat_id in self.user_keywords and self.user_keywords[chat_id]:
            keywords_str = ', '.join(self.user_keywords[chat_id])
            await update.message.reply_text(f"📝 Your keywords: {keywords_str}")
        else:
            await update.message.reply_text("You haven't set any keywords yet!")
    
    async def show_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_ignore command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if chat_id in self.user_ignore_keywords and self.user_ignore_keywords[chat_id]:
            ignore_str = ', '.join(self.user_ignore_keywords[chat_id])
            await update.message.reply_text(f"🚫 Your ignore keywords: {ignore_str}")
        else:
            await update.message.reply_text("You haven't set any ignore keywords yet!")
    
    def is_job_message(self, message_text: str) -> bool:
        """Check if message contains job-related keywords"""
        text_lower = message_text.lower()
        return any(keyword in text_lower for keyword in self.job_keywords)
    
    def matches_user_keywords(self, message_text: str, user_keywords: List[str]) -> bool:
        """Check if message matches user's keywords"""
        text_lower = message_text.lower()
        return any(keyword in text_lower for keyword in user_keywords)
    
    def matches_ignore_keywords(self, message_text: str, ignore_keywords: List[str]) -> bool:
        """Check if message matches ignore keywords"""
        if not ignore_keywords:
            return False
        text_lower = message_text.lower()
        return any(keyword in text_lower for keyword in ignore_keywords)
    
    async def handle_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages from monitored channels"""
        message = update.message
        if not message or not message.text:
            return
        
        # Ignore messages from private chats (user commands)
        if message.chat.type == 'private':
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
            # Check user's daily limit
            if not self.check_user_limit(user_chat_id):
                logger.info(f"User {user_chat_id} has reached daily limit")
                continue
            
            # Check if message matches user keywords
            if not self.matches_user_keywords(message.text, keywords):
                continue
            
            # Check if message matches ignore keywords
            ignore_keywords = self.user_ignore_keywords.get(user_chat_id, [])
            if self.matches_ignore_keywords(message.text, ignore_keywords):
                logger.info(f"Message filtered out by ignore keywords for user {user_chat_id}")
                continue
            
            try:
                # Forward the message directly to the user's private chat
                await context.bot.forward_message(
                    chat_id=user_chat_id,
                    from_chat_id=chat_id,
                    message_id=message.message_id
                )
                
                # No need to increment usage or check limits anymore
                
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
                    async for message in self.app.bot.get_chat_history(
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
                            # Check user's daily limit
                            if not self.check_user_limit(user_chat_id):
                                continue
                            
                            # Check if message matches user keywords
                            if not self.matches_user_keywords(message.text, keywords):
                                continue
                            
                            # Check if message matches ignore keywords
                            ignore_keywords = self.user_ignore_keywords.get(user_chat_id, [])
                            if self.matches_ignore_keywords(message.text, ignore_keywords):
                                continue
                            
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
        
        # Set up post_init callback to start background tasks
        async def post_init(application):
            await bot.start_config_reload_task()
        
        bot.app.post_init = post_init
        bot.app.run_polling()

if __name__ == '__main__':
    main()