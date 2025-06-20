#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot - Main Entry Point
Collects job postings from configured channels and reposts to user groups
"""

import asyncio
import logging
import os

from telegram.ext import Application

from handlers.commands import CommandHandlers
from handlers.callbacks import CallbackHandlers
from handlers.messages import MessageHandlers
from storage.data_manager import DataManager
from utils.config import ConfigManager

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
        
        # Initialize managers
        self.config_manager = ConfigManager()
        self.data_manager = DataManager()
        
        # Initialize handlers
        self.command_handlers = CommandHandlers(self.data_manager)
        self.callback_handlers = CallbackHandlers(self.data_manager)
        self.message_handlers = MessageHandlers(self.data_manager, self.config_manager)
        
        # Register all handlers
        self.register_handlers()
    
    def register_handlers(self):
        """Register all command and message handlers"""
        # Command handlers
        self.command_handlers.register(self.app)
        
        # Callback handlers
        self.callback_handlers.register(self.app)
        
        # Message handlers
        self.message_handlers.register(self.app)
        
        logger.info("All handlers registered successfully")
    
    async def start_background_tasks(self):
        """Start background tasks like config reloading"""
        # Start config reload task
        async def reload_task():
            while True:
                await asyncio.sleep(3600)  # 1 hour
                logger.info("Reloading configuration...")
                self.config_manager.load_config()
        
        asyncio.create_task(reload_task())
        logger.info("Background tasks started")
        
        # Set up bot menu
        await self.setup_bot_menu()
    
    async def setup_bot_menu(self):
        """Set up the bot menu commands"""
        from telegram import BotCommand
        
        commands = [
            BotCommand("start", "🚀 Start the bot and see welcome message"),
            BotCommand("menu", "📋 Show interactive menu"),
            BotCommand("keywords", "🎯 Set your search keywords"),
            BotCommand("ignore_keywords", "🚫 Set ignore keywords"),
            BotCommand("my_keywords", "📝 Show your current keywords"),
            BotCommand("my_ignore", "📋 Show your ignore keywords"),
            BotCommand("add_keyword_to_list", "➕ Add a keyword"),
            BotCommand("add_ignore_keyword", "➕ Add ignore keyword"),
            BotCommand("delete_keyword_from_list", "➖ Remove a keyword"),
            BotCommand("delete_ignore_keyword", "➖ Remove ignore keyword"),
            BotCommand("purge_ignore", "🗑️ Clear all ignore keywords"),
            BotCommand("help", "❓ Show help and examples")
        ]
        
        try:
            await self.app.bot.set_my_commands(commands)
            logger.info("Bot menu commands set successfully")
        except Exception as e:
            logger.warning(f"Could not set bot menu commands: {e}")
    
    async def collect_and_repost_jobs(self):
        """Manual job collection function for scheduled runs"""
        await self.message_handlers.collect_and_repost_jobs(self.app.bot)
    
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
            await bot.start_background_tasks()
        
        bot.app.post_init = post_init
        bot.app.run_polling()

if __name__ == '__main__':
    main()
