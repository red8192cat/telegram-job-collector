#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot - Fixed Version
FIXES: Event loop conflicts, initialization issues, proper error handling
"""

import asyncio
import logging
import os
import signal
import sys

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
        
        # Initialize managers with backup support
        logger.info("🔄 Initializing configuration manager...")
        self.config_manager = ConfigManager()
        
        db_path = os.getenv("DATABASE_PATH", "data/bot.db")
        self.data_manager = SQLiteManager(db_path)
        
        # Initialize handlers (core functionality - always works)
        self.command_handlers = CommandHandlers(self.data_manager)
        self.callback_handlers = CallbackHandlers(self.data_manager)
        self.message_handlers = MessageHandlers(self.data_manager, self.config_manager)
        
        # Initialize OPTIONAL user monitor - but don't block if it fails
        self.user_monitor = None
        self._user_monitor_task = None
        
        if USER_MONITOR_AVAILABLE and self._has_user_credentials() and not os.getenv('DISABLE_USER_MONITOR'):
            try:
                self.user_monitor = UserAccountMonitor(
                    self.data_manager, 
                    self.config_manager,
                    bot_instance=None  # Will be set after app initialization
                )
                logger.info("✅ User monitor extension available")
            except Exception as e:
                logger.error(f"❌ User monitor initialization failed: {e}")
                self.user_monitor = None
        else:
            if not USER_MONITOR_AVAILABLE:
                logger.info("ℹ️ User monitor extension not available (missing dependencies)")
            elif os.getenv('DISABLE_USER_MONITOR'):
                logger.info("ℹ️ User monitor extension disabled by environment variable")
            else:
                logger.info("ℹ️ User monitor extension disabled (no credentials)")
        
        # Register all handlers
        self.register_handlers()
        
        # Set up shutdown handling
        self._shutdown_event = asyncio.Event()
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_event.set()
    
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
        
        logger.info("✅ All core handlers registered successfully")
    
    async def start_background_tasks(self):
        """Start background tasks - FIXED VERSION with proper error handling"""
        try:
            # Initialize database first
            await self.data_manager.initialize()
            logger.info("✅ Database initialized successfully")
            
            # Import from config files if database is empty
            await self._import_on_startup()
            
            # Initialize error monitoring INDEPENDENT of user monitor
            await self._initialize_error_monitoring()
            
            # Validate bot channels on startup
            await self._validate_bot_channels()
            
            # Set up bot menu
            await self.setup_bot_menu()
            
            # Start background tasks using job queue - FIXED
            self._setup_background_tasks()
            
            # Initialize user monitor AFTER core bot is ready - NON-BLOCKING
            if self.user_monitor:
                self.user_monitor.bot_instance = self.app.bot
                self.app.bot_data["user_monitor"] = self.user_monitor
                
                # Start user monitor in background task - don't await
                self._user_monitor_task = asyncio.create_task(
                    self._initialize_user_monitor_safe()
                )
                logger.info("🔄 User monitor initialization started in background")
            
            logger.info("✅ Core bot initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Critical error in background tasks: {e}")
            await self._notify_admin_safe(f"❌ **Bot Startup Error**\n\n{str(e)}")
            # Don't raise - let core bot continue
    
    async def _initialize_user_monitor_safe(self):
        """Initialize user monitor safely in background"""
        try:
            logger.info("🔄 Initializing user monitor...")
            success = await self.user_monitor.initialize()
            
            if success:
                logger.info("✅ User monitor authenticated successfully")
                # Start monitoring in background
                await self.user_monitor.start_monitoring()
            else:
                logger.warning("⚠️ User monitor needs authentication")
                await self._notify_admin_safe(
                    "⚠️ **User Monitor Authentication Required**\n\n"
                    "Use `/auth_status` to check status and `/auth_restart` if needed."
                )
        except Exception as e:
            logger.error(f"❌ User monitor error: {e}")
            await self._notify_admin_safe(
                f"❌ **User Monitor Error**\n\n{str(e)}\n\n"
                f"Core bot functionality continues normally."
            )
    
    def _setup_background_tasks(self):
        """Set up background tasks with proper job queue - FIXED"""
        try:
            if not self.app.job_queue:
                logger.warning("⚠️ JobQueue not available - install python-telegram-bot[job-queue]")
                return
            
            # User monitor health check every 5 minutes
            if self.user_monitor:
                self.app.job_queue.run_repeating(
                    self._check_user_monitor_health,
                    interval=300,  # 5 minutes
                    first=60       # Start after 1 minute
                )
                logger.info("📊 User monitor health checks scheduled")
            
            # Config reload every hour
            self.app.job_queue.run_repeating(
                self._reload_config_task,
                interval=3600,  # 1 hour
                first=300       # Start after 5 minutes
            )
            
            # Database cleanup daily
            self.app.job_queue.run_repeating(
                self._cleanup_database_task,
                interval=86400,  # 24 hours
                first=3600       # Start after 1 hour
            )
            
            logger.info("✅ Background tasks scheduled")
                
        except Exception as e:
            logger.warning(f"Could not set up background tasks: {e}")
            logger.info("Core bot will continue without background tasks")
    
    async def _check_user_monitor_health(self, context):
        """Health check for user monitor - FIXED JobQueue compatible"""
        if not self.user_monitor:
            return
        
        try:
            if not self.user_monitor.is_connected():
                logger.warning("User monitor disconnected, attempting reconnect...")
                success = await self.user_monitor.reconnect()
                if success:
                    logger.info("✅ User monitor reconnected successfully")
                    await self._notify_admin_safe("✅ **User Monitor Reconnected**\n\nConnection restored automatically.")
                else:
                    logger.error("❌ User monitor reconnection failed")
                    await self._notify_admin_safe("⚠️ **User Monitor Connection Issues**\n\nAutomatic reconnection failed.")
        except Exception as e:
            logger.error(f"Error in user monitor health check: {e}")
    
    async def _reload_config_task(self, context):
        """Config reload task - FIXED JobQueue compatible"""
        try:
            logger.info("🔄 Reloading configuration...")
            
            old_bot_channels = self.config_manager.get_channels_to_monitor()
            old_user_channels = self.config_manager.get_user_monitored_channels() if self.user_monitor else []
            
            self.config_manager.load_channels_config()
            
            new_bot_channels = self.config_manager.get_channels_to_monitor()
            new_user_channels = self.config_manager.get_user_monitored_channels() if self.user_monitor else []
            
            # Update user monitor if channels changed
            if self.user_monitor and old_user_channels != new_user_channels:
                try:
                    await self.user_monitor.update_monitored_entities()
                    logger.info("✅ User monitor channels updated")
                except Exception as e:
                    logger.error(f"❌ Failed to update user monitor channels: {e}")
        except Exception as e:
            logger.error(f"Config reload error: {e}")
    
    async def _cleanup_database_task(self, context):
        """Database cleanup task - NEW"""
        try:
            logger.info("🧹 Running database cleanup...")
            await self.data_manager.cleanup_old_data(days=30)
            logger.info("✅ Database cleanup completed")
        except Exception as e:
            logger.error(f"Database cleanup error: {e}")
    
    async def _validate_bot_channels(self):
        """Validate bot channels on startup - IMPROVED with better error handling"""
        try:
            channels = self.config_manager.get_channels_to_monitor()
            if not channels:
                logger.info("ℹ️ No bot channels configured")
                return
            
            valid_channels = []
            invalid_channels = []
            
            for channel_identifier in channels:
                try:
                    # Try to get chat info with timeout
                    chat = await asyncio.wait_for(
                        self.app.bot.get_chat(channel_identifier), 
                        timeout=10
                    )
                    
                    # Check if bot is admin
                    try:
                        bot_member = await asyncio.wait_for(
                            self.app.bot.get_chat_member(chat.id, self.app.bot.id),
                            timeout=5
                        )
                        is_admin = bot_member.status in ['administrator', 'creator']
                    except:
                        is_admin = False
                    
                    if is_admin:
                        valid_channels.append(channel_identifier)
                        logger.info(f"✅ Bot validated (admin): {channel_identifier}")
                    else:
                        invalid_channels.append(f"{channel_identifier} (not admin)")
                        logger.warning(f"⚠️ Bot not admin in: {channel_identifier}")
                
                except asyncio.TimeoutError:
                    invalid_channels.append(f"{channel_identifier} (timeout)")
                    logger.error(f"❌ Timeout accessing channel: {channel_identifier}")
                except Exception as e:
                    invalid_channels.append(f"{channel_identifier} (error: {str(e)[:30]})")
                    logger.error(f"❌ Error accessing channel {channel_identifier}: {e}")
            
            # Log summary
            if invalid_channels:
                logger.warning(f"⚠️ Channel validation: {len(valid_channels)} valid, {len(invalid_channels)} issues")
                await self._notify_admin_safe(
                    f"⚠️ **Bot Channel Validation**\n\n"
                    f"✅ Valid: {len(valid_channels)}\n"
                    f"❌ Issues: {len(invalid_channels)}\n\n"
                    f"**Issues:**\n" + 
                    "\n".join([f"• {ch}" for ch in invalid_channels[:5]]) +
                    (f"\n... and {len(invalid_channels) - 5} more" if len(invalid_channels) > 5 else "")
                )
            else:
                logger.info(f"✅ All {len(valid_channels)} bot channels validated")
                
        except Exception as e:
            logger.error(f"Error in channel validation: {e}")
    
    async def _initialize_error_monitoring(self):
        """Initialize error monitoring - IMPROVED"""
        if not self._admin_id:
            logger.info("ℹ️ No admin ID configured - error monitoring disabled")
            return
        
        try:
            from utils.error_monitor import setup_error_monitoring
            setup_error_monitoring(self.app.bot, self._admin_id)
            logger.info(f"✅ Error monitoring initialized for admin ID: {self._admin_id}")
            
            # Send startup notification
            await self._notify_admin_about_startup()
                
        except ImportError:
            logger.warning("Error monitoring module not available")
        except Exception as e:
            logger.error(f"Failed to initialize error monitoring: {e}")
    
    async def _notify_admin_about_startup(self):
        """Notify admin about startup with system info - IMPROVED"""
        if not self._admin_id:
            return
        
        try:
            # Get system info
            backups = self.config_manager.list_backups() if hasattr(self.config_manager, 'list_backups') else []
            backup_count = len(backups)
            
            startup_message = (
                f"🤖 **Bot Started Successfully**\n\n"
                f"✅ Core bot functionality active\n"
                f"✅ Database initialized\n"
                f"✅ Message handlers registered\n"
            )
            
            if self.app.job_queue:
                startup_message += f"✅ Background tasks scheduled\n"
            else:
                startup_message += f"⚠️ Background tasks disabled (missing job-queue)\n"
            
            if self._admin_id:
                startup_message += f"✅ Error monitoring active\n"
            
            startup_message += f"💾 Config backups: {backup_count} files\n\n"
            
            if self.user_monitor:
                startup_message += f"🔄 User monitor: Initializing...\n\n"
            else:
                startup_message += f"ℹ️ User monitor: Disabled\n\n"
            
            startup_message += f"Use `/admin` to see available commands"
            
            await asyncio.wait_for(
                self.app.bot.send_message(
                    chat_id=self._admin_id,
                    text=startup_message,
                    parse_mode='Markdown'
                ),
                timeout=10
            )
        except Exception as e:
            logger.warning(f"Could not send startup notification: {e}")
    
    async def _notify_admin_safe(self, message: str):
        """Send notification to admin with timeout - IMPROVED"""
        if not self._admin_id:
            return
        
        try:
            await asyncio.wait_for(
                self.app.bot.send_message(
                    chat_id=self._admin_id,
                    text=message,
                    parse_mode='Markdown'
                ),
                timeout=10
            )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")
    
    async def setup_bot_menu(self):
        """Set up bot menu commands - IMPROVED with error handling"""
        try:
            from telegram import BotCommand
            from utils.translations import get_text
            
            # Always English for bot menu commands
            menu_language = "en"
            
            commands = [
                BotCommand("start", get_text("menu_command_start", menu_language)),
                BotCommand("manage_keywords", get_text("menu_command_manage", menu_language)),
                BotCommand("my_settings", get_text("menu_command_settings", menu_language)),
                BotCommand("help", get_text("menu_command_help", menu_language)),
            ]
            
            await asyncio.wait_for(
                self.app.bot.set_my_commands(commands),
                timeout=10
            )
            logger.info("✅ Bot menu commands set")
        except Exception as e:
            logger.warning(f"Could not set bot menu commands: {e}")
    
    async def _import_on_startup(self):
        """Import from config files if database is empty - IMPROVED"""
        try:
            # Check if database has data
            all_users = await self.data_manager.get_all_users_with_keywords()
            bot_channels, user_channels = await self.data_manager.export_all_channels_for_config()
            
            imported_something = False
            
            # Import channels if database is empty
            if not bot_channels and not user_channels:
                self.config_manager.load_channels_config()
                config_bot_channels = self.config_manager.get_channels_to_monitor()
                config_user_channels = self.config_manager.get_user_monitored_channels()
                
                if config_bot_channels or config_user_channels:
                    # Convert to proper format for import
                    bot_channel_dicts = [{'chat_id': ch, 'username': None} for ch in config_bot_channels]
                    user_channel_dicts = [{'chat_id': ch, 'username': None} for ch in config_user_channels]
                    
                    await self.data_manager.import_channels_from_config(bot_channel_dicts, user_channel_dicts)
                    logger.info(f"✅ Imported channels: {len(config_bot_channels)} bot, {len(config_user_channels)} user")
                    imported_something = True
            
            # Import users if database is empty
            if not all_users:
                users_data = self.config_manager.load_users_config()
                if users_data:
                    await self.data_manager.import_users_from_config(users_data)
                    logger.info(f"✅ Imported {len(users_data)} users")
                    imported_something = True
            
            if not imported_something:
                logger.info("ℹ️ Database has data, skipping config import")
                
        except Exception as e:
            logger.error(f"⚠️ Config import error: {e}")
    
    # Legacy methods for backward compatibility
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
    
    async def shutdown(self):
        """Graceful shutdown - NEW"""
        logger.info("🛑 Starting graceful shutdown...")
        
        try:
            # Cancel user monitor task
            if self._user_monitor_task and not self._user_monitor_task.done():
                self._user_monitor_task.cancel()
                try:
                    await asyncio.wait_for(self._user_monitor_task, timeout=5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Stop user monitor
            if self.user_monitor:
                await self.user_monitor.stop()
            
            # Close database connections
            await self.data_manager.close()
            
            logger.info("✅ Graceful shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

def main():
    """Main function - FIXED with proper error handling and webhook clearing"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN environment variable not set!")
        sys.exit(1)
    
    # Clear webhook on startup to prevent pending updates issue
    async def clear_webhook():
        try:
            from telegram import Bot
            bot = Bot(token)
            await bot.delete_webhook()
            info = await bot.get_webhook_info()
            if info.pending_update_count > 0:
                logger.warning(f"⚠️ Cleared webhook, had {info.pending_update_count} pending updates")
            else:
                logger.info("✅ Webhook cleared, no pending updates")
        except Exception as e:
            logger.error(f"❌ Failed to clear webhook: {e}")
    
    try:
        # Clear webhook first
        asyncio.run(clear_webhook())
    except Exception as e:
        logger.warning(f"Webhook clearing failed: {e}")
    
    bot = JobCollectorBot(token)
    
    # Check run mode
    run_mode = os.getenv('RUN_MODE', 'polling')
    
    if run_mode == 'scheduled':
        # Run job collection once and exit
        logger.info("Starting in scheduled mode...")
        asyncio.run(bot.run_scheduled_job())
    else:
        # Default: Polling mode
        logger.info("🚀 Starting Job Collector Bot...")
        logger.info("✅ Core functionality: Bot monitoring enabled")
        
        # Log configuration status
        if bot._admin_id:
            logger.info("✅ Admin functionality: Enabled")
        else:
            logger.info("ℹ️ Admin functionality: Disabled (no AUTHORIZED_ADMIN_ID)")
        
        if bot.user_monitor:
            logger.info("✅ Extended functionality: User account monitoring available")
        else:
            logger.info("ℹ️ Extended functionality: User account monitoring disabled")
        
        # Set up post_init callback to start background tasks
        async def post_init(application):
            await bot.start_background_tasks()
        
        bot.app.post_init = post_init
        
        try:
            # Run using the built-in method (handles event loop properly)
            bot.app.run_polling(
                drop_pending_updates=True,  # CRITICAL: Drop old pending updates
                stop_signals=[signal.SIGTERM, signal.SIGINT]
            )
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}")
            sys.exit(1)
        finally:
            # Cleanup
            try:
                asyncio.run(bot.shutdown())
            except Exception as e:
                logger.error(f"Shutdown error: {e}")

if __name__ == '__main__':
    main()