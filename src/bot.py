#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot - Main Entry Point with OPTIONAL User Account Monitoring
The bot works perfectly without user account - it's just an optional extension!
FIXED: Error monitoring and admin functionality independent of user monitor
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
        
        # Get admin ID for notifications
        self._admin_id = None
        admin_id_str = os.getenv('AUTHORIZED_ADMIN_ID')
        if admin_id_str and admin_id_str.isdigit():
            self._admin_id = int(admin_id_str)
        
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
        
        # FIXED: Initialize error monitoring INDEPENDENT of user monitor
        await self._initialize_error_monitoring()
        
        # Validate bot channels on startup
        await self._validate_bot_channels()
        
        # Initialize user monitor if available (completely separate from admin/error monitoring)
        if self.user_monitor:
            # Store user_monitor in bot_data for admin commands that need it
            self.user_monitor.bot_instance = self.app.bot
            self.app.bot_data["user_monitor"] = self.user_monitor
            logger.info("User monitor stored in bot_data")
            
            try:
                success = await self.user_monitor.initialize()
                if success:
                    # Start user monitor in background
                    asyncio.create_task(self.user_monitor.run_forever())
                    logger.info("✅ User monitor extension started successfully")
                else:
                    logger.warning("❌ User monitor extension needs authentication")
                    
            except Exception as e:
                logger.error(f"❌ User monitor extension error: {e}")
                logger.info("Continuing with core bot functionality only")
        
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
    
    async def _validate_bot_channels(self):
        """Validate bot channels on startup"""
        channels = self.config_manager.get_channels_to_monitor()
        if not channels:
            logger.info("⚙️ STARTUP: No bot channels configured")
            return
        
        valid_channels = []
        invalid_channels = []
        
        for channel_identifier in channels:
            try:
                # Try to get chat info
                chat = await self.app.bot.get_chat(channel_identifier)
                
                # Check if bot is admin
                is_admin = False
                try:
                    bot_member = await self.app.bot.get_chat_member(chat.id, self.app.bot.id)
                    is_admin = bot_member.status in ['administrator', 'creator']
                except Exception:
                    is_admin = False
                
                if is_admin:
                    valid_channels.append(channel_identifier)
                    logger.info(f"✅ STARTUP: Bot validated (admin): {channel_identifier}")
                else:
                    invalid_channels.append(f"{channel_identifier} (not admin)")
                    logger.warning(f"⚠️ STARTUP: Bot not admin in: {channel_identifier}")
                
            except Exception as e:
                invalid_channels.append(f"{channel_identifier} (access error)")
                logger.error(f"❌ STARTUP: Bot cannot access channel {channel_identifier}: {e}")
        
        # Log summary
        if invalid_channels:
            logger.warning(f"⚠️ STARTUP: Bot channel validation: {len(valid_channels)} valid, {len(invalid_channels)} issues")
            
            # Notify admin if error monitoring is available
            if hasattr(self, '_admin_id') and self._admin_id:
                try:
                    await self.app.bot.send_message(
                        chat_id=self._admin_id,
                        text=(
                            f"⚠️ **Bot Channel Validation Issues**\n\n"
                            f"✅ Valid bot channels: {len(valid_channels)}\n"
                            f"❌ Invalid bot channels: {len(invalid_channels)}\n\n"
                            f"**Issues found:**\n" + 
                            "\n".join([f"• {ch}" for ch in invalid_channels]) +
                            f"\n\nBot must be admin in channels to monitor them."
                        ),
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Could not notify admin about channel issues: {e}")
        else:
            logger.info(f"✅ STARTUP: All {len(valid_channels)} bot channels validated successfully")
    
    async def _initialize_error_monitoring(self):
        """Initialize error monitoring - INDEPENDENT of user monitor"""
        admin_id_str = os.getenv('AUTHORIZED_ADMIN_ID')
        
        if not admin_id_str or not admin_id_str.isdigit():
            logger.info("No admin ID configured - error monitoring disabled")
            return
        
        admin_id = int(admin_id_str)
        
        try:
            from utils.error_monitor import setup_error_monitoring
            setup_error_monitoring(self.app.bot, admin_id)
            logger.info(f"✅ Error monitoring initialized for admin ID: {admin_id}")
            
            # Send initial notification to admin
            try:
                await self.app.bot.send_message(
                    chat_id=admin_id,
                    text="🤖 **Bot Started Successfully**\n\n✅ Error monitoring active\n📊 Admin commands available",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Could not send startup notification to admin: {e}")
                
        except ImportError as e:
            logger.warning(f"Error monitoring not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize error monitoring: {e}")
    
    async def setup_bot_menu(self):
        """Set up the bot menu commands - AUTH COMMANDS HIDDEN FROM PUBLIC"""
        from telegram import BotCommand
        
        # PUBLIC commands only - auth commands are hidden
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
        ]
        
        # NOTE: auth_status, auth_restart, and admin commands are NOT in public menu
        # They work for authorized admin but are hidden from other users
        
        try:
            await self.app.bot.set_my_commands(commands)
            logger.info("Bot menu commands set successfully (auth commands hidden)")
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
        
        # Log admin status
        admin_id_str = os.getenv('AUTHORIZED_ADMIN_ID')
        if admin_id_str and admin_id_str.isdigit():
            logger.info("✅ Admin functionality: Enabled")
        else:
            logger.info("ℹ️  Admin functionality: Disabled (no AUTHORIZED_ADMIN_ID)")
        
        # Log user monitor status  
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