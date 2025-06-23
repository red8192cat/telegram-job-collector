#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot - Main Entry Point with OPTIONAL User Account Monitoring
The bot works perfectly without user account - it's just an optional extension!
"""

import asyncio
import logging
import os

from telegram.ext import Application

from handlers.commands import CommandHandlers
from handlers.callbacks import CallbackHandlers
from handlers.messages import MessageHandlers
from storage.sqlite_manager import SQLiteManager
from utils.config import ConfigManager

# Try to import user monitor - if dependencies missing, gracefully disable
try:
    from monitoring.user_monitor import UserAccountMonitor
    USER_MONITOR_AVAILABLE = True
except ImportError as e:
    logging.warning(f"User monitor dependencies not available: {e}")
    UserAccountMonitor = None
    USER_MONITOR_AVAILABLE = False

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
        db_path = os.getenv("DATABASE_PATH", "data/bot.db")
        self.data_manager = SQLiteManager(db_path)
        
        # Initialize handlers (core functionality - always works)
        self.command_handlers = CommandHandlers(self.data_manager)
        self.callback_handlers = CallbackHandlers(self.data_manager)
        self.message_handlers = MessageHandlers(self.data_manager, self.config_manager)
        
        # Initialize OPTIONAL user monitor
        self.user_monitor = None
        if USER_MONITOR_AVAILABLE and self._has_user_credentials():
            self.user_monitor = UserAccountMonitor(
                self.data_manager, 
                self.config_manager,
                bot_instance=None  # Will be set after app initialization
            )
            logger.info("User monitor extension enabled")
        else:
            if not USER_MONITOR_AVAILABLE:
                logger.info("User monitor extension not available (missing dependencies)")
            else:
                logger.info("User monitor extension disabled (no credentials)")
        
        # Register all handlers
        self.register_handlers()
    
    def _has_user_credentials(self):
        """Check if user account credentials are provided"""
        return all([
            os.getenv('API_ID'),
            os.getenv('API_HASH'),
            os.getenv('PHONE_NUMBER')
        ])
    
    def register_handlers(self):
        """Register all command and message handlers"""
        # Command handlers (core functionality)
        self.command_handlers.register(self.app)
        
        # Callback handlers (core functionality)
        self.callback_handlers.register(self.app)
        
        # Message handlers (core bot monitoring - always active)
        self.message_handlers.register(self.app)
        
        logger.info("All core handlers registered successfully")
    
    async def start_background_tasks(self):
        """Start background tasks"""
        # Initialize database first
        await self.data_manager.initialize()
        logger.info("Database initialized successfully")
        
        # Core bot functionality is ready
        logger.info("Core bot functionality ready")
        
        # Optionally start user monitor extension
        if self.user_monitor:
            self.user_monitor.bot_instance = self.app.bot
            # Store user_monitor in bot_data for handlers to access
            self.app.bot_data["user_monitor"] = self.user_monitor
            
            try:
                success = await self.user_monitor.initialize()
                if success:
                    # Start user monitor in background
                    asyncio.create_task(self.user_monitor.run_forever())
                    logger.info("✅ User monitor extension started successfully")
                else:
                    logger.warning("❌ User monitor extension failed to start")
                    self.user_monitor = None
                    
            except Exception as e:
                logger.error(f"❌ User monitor extension error: {e}")
                logger.info("Continuing with core bot functionality only")
                self.user_monitor = None
        
        # Start config reload task
        async def reload_task():
            while True:
                await asyncio.sleep(3600)  # 1 hour
                logger.info("Reloading configuration...")
                
                old_bot_channels = self.config_manager.get_channels_to_monitor()
                old_user_channels = self.config_manager.get_user_monitored_channels() if self.user_monitor else []
                
                self.config_manager.load_config()
                
                new_bot_channels = self.config_manager.get_channels_to_monitor()
                new_user_channels = self.config_manager.get_user_monitored_channels() if self.user_monitor else []
                
                # Update user monitor if channels changed
                if self.user_monitor and old_user_channels != new_user_channels:
                    try:
                        await self.user_monitor.update_monitored_entities()
                        logger.info("✅ User monitor channels updated")
                    except Exception as e:
                        logger.error(f"❌ Failed to update user monitor channels: {e}")
        
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
            BotCommand("help", "❓ Show help and examples"),
            BotCommand("auth_status", "🔐 Check authentication status"),
            BotCommand("auth_restart", "🔄 Restart authentication"),
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
        logger.info("Starting Job Collector Bot...")
        logger.info("✅ Core functionality: Bot monitoring enabled")
        if bot.user_monitor:
            logger.info("✅ Extended functionality: User account monitoring enabled")
        else:
            logger.info("ℹ️  Extended functionality: User account monitoring disabled")
        
        # Set up post_init callback to start background tasks
        async def post_init(application):
            await bot.start_background_tasks()
        
        bot.app.post_init = post_init
        bot.app.run_polling()

if __name__ == '__main__':
    main()