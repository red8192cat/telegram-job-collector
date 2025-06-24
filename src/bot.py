#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot - WITH ROBUST USER MONITOR
INCLUDES: Proper User Monitor integration with event loop separation
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
        logger.info("🔄 Initializing configuration manager...")
        self.config_manager = ConfigManager()
        
        db_path = os.getenv("DATABASE_PATH", "data/bot.db")
        self.data_manager = SQLiteManager(db_path)
        
        # Initialize handlers
        self.command_handlers = CommandHandlers(self.data_manager)
        self.callback_handlers = CallbackHandlers(self.data_manager)
        self.message_handlers = MessageHandlers(self.data_manager, self.config_manager)
        
        # User Monitor setup - DELAYED INITIALIZATION
        self.user_monitor = None
        self._user_monitor_task = None
        self._user_monitor_enabled = self._should_enable_user_monitor()
        
        if self._user_monitor_enabled:
            logger.info("✅ User monitor will be enabled after event loop starts")
        else:
            logger.info("ℹ️ User monitor disabled (missing credentials or explicitly disabled)")
        
        # Register all handlers
        self.register_handlers()
    
    def _should_enable_user_monitor(self):
        """Determine if user monitor should be enabled"""
        # Check if explicitly disabled
        if os.getenv('DISABLE_USER_MONITOR', '').lower() in ('true', '1', 'yes'):
            return False
        
        # Check if credentials are available
        required_vars = ['API_ID', 'API_HASH', 'PHONE_NUMBER']
        if not all(os.getenv(var) for var in required_vars):
            return False
        
        # Check if import is available
        try:
            from monitoring.user_monitor import UserAccountMonitor
            return True
        except ImportError as e:
            logger.warning(f"User monitor dependencies not available: {e}")
            return False
    
    def register_handlers(self):
        """Register all command and message handlers"""
        self.command_handlers.register(self.app)
        self.callback_handlers.register(self.app)
        self.message_handlers.register(self.app)
        logger.info("✅ All core handlers registered successfully")
    
    async def start_background_tasks(self):
        """Start background tasks - WITH USER MONITOR"""
        try:
            # Initialize database first
            await self.data_manager.initialize()
            logger.info("✅ Database initialized successfully")
            
            # Import from config files if database is empty
            await self._import_on_startup()
            
            # Initialize error monitoring
            await self._initialize_error_monitoring()
            
            # Validate bot channels on startup
            await self._validate_bot_channels()
            
            # Set up bot menu
            await self.setup_bot_menu()
            
            # Start background tasks using job queue
            self._setup_background_tasks()
            
            # Initialize User Monitor AFTER event loop is stable
            if self._user_monitor_enabled:
                await self._initialize_user_monitor()
            
            logger.info("✅ Core bot initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Critical error in background tasks: {e}")
            await self._notify_admin_safe(f"❌ **Bot Startup Error**\n\n{str(e)}")
    
    async def _initialize_user_monitor(self):
        """Initialize user monitor with proper event loop handling"""
        try:
            logger.info("🔄 Initializing User Monitor...")
            
            # Import and create user monitor AFTER event loop is running
            from monitoring.user_monitor import UserAccountMonitor
            
            self.user_monitor = UserAccountMonitor(
                self.data_manager,
                self.config_manager,
                bot_instance=self.app.bot
            )
            
            # Store in bot_data for admin commands
            self.app.bot_data["user_monitor"] = self.user_monitor
            
            logger.info("✅ User monitor created successfully")
            
            # Start initialization in background (non-blocking)
            self._user_monitor_task = asyncio.create_task(
                self._user_monitor_initialization_flow()
            )
            
            logger.info("🔄 User monitor initialization started in background")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize user monitor: {e}")
            self.user_monitor = None
            await self._notify_admin_safe(
                f"❌ **User Monitor Initialization Failed**\n\n"
                f"Error: {str(e)}\n\n"
                f"Core bot functionality continues normally.\n"
                f"Check logs for details."
            )
    
    async def _user_monitor_initialization_flow(self):
        """Complete user monitor initialization flow"""
        try:
            # Give the main event loop a moment to stabilize
            await asyncio.sleep(2)
            
            logger.info("🔄 Starting user monitor authentication...")
            success = await self.user_monitor.initialize()
            
            if success:
                logger.info("✅ User monitor authenticated successfully")
                
                # Start monitoring
                await self.user_monitor.start_monitoring()
                
                # Notify admin of success
                channel_count = len(self.user_monitor.monitored_entities)
                await self._notify_admin_safe(
                    f"🎉 **User Monitor Active!**\n\n"
                    f"✅ Authentication successful\n"
                    f"📊 Monitoring {channel_count} user channels\n"
                    f"🔄 Real-time forwarding enabled\n\n"
                    f"The bot can now monitor channels where it's not admin!"
                )
                
            else:
                logger.warning("⚠️ User monitor needs authentication")
                await self._notify_admin_safe(
                    f"🔐 **User Monitor Authentication Required**\n\n"
                    f"📱 The user account needs to be authenticated\n"
                    f"📨 Check your phone for SMS verification code\n\n"
                    f"**Commands:**\n"
                    f"• `/auth_status` - Check authentication status\n"
                    f"• `/auth_restart` - Restart authentication process\n\n"
                    f"Send the verification code directly to this chat when received."
                )
                
        except Exception as e:
            logger.error(f"❌ User monitor initialization flow error: {e}")
            await self._notify_admin_safe(
                f"❌ **User Monitor Error**\n\n{str(e)}\n\n"
                f"Core bot functionality continues normally.\n"
                f"Use `/auth_restart` to retry."
            )
    
    def _setup_background_tasks(self):
        """Set up background tasks with user monitor health checks"""
        try:
            if not self.app.job_queue:
                logger.warning("⚠️ JobQueue not available - install python-telegram-bot[job-queue]")
                return
            
            # User monitor health check every 5 minutes
            self.app.job_queue.run_repeating(
                self._check_user_monitor_health,
                interval=300,  # 5 minutes
                first=60       # Start after 1 minute
            )
            
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
        """Health check for user monitor"""
        if not self.user_monitor:
            return
        
        try:
            if not self.user_monitor.is_connected():
                logger.warning("⚠️ User monitor disconnected, attempting reconnect...")
                success = await self.user_monitor.reconnect()
                if success:
                    logger.info("✅ User monitor reconnected successfully")
                    await self._notify_admin_safe(
                        "✅ **User Monitor Reconnected**\n\n"
                        "Connection restored automatically.\n"
                        "Real-time monitoring resumed."
                    )
                else:
                    logger.error("❌ User monitor reconnection failed")
                    await self._notify_admin_safe(
                        "⚠️ **User Monitor Connection Issues**\n\n"
                        "Automatic reconnection failed.\n"
                        "Use `/auth_restart` if needed."
                    )
        except Exception as e:
            logger.error(f"Error in user monitor health check: {e}")
    
    async def _reload_config_task(self, context):
        """Config reload task with user monitor channel updates"""
        try:
            logger.info("🔄 Reloading configuration...")
            
            old_bot_channels = self.config_manager.get_channels_to_monitor()
            old_user_channels = self.config_manager.get_user_monitored_channels() if self.user_monitor else []
            
            self.config_manager.load_channels_config()
            
            new_bot_channels = self.config_manager.get_channels_to_monitor()
            new_user_channels = self.config_manager.get_user_monitored_channels() if self.user_monitor else []
            
            # Update user monitor channels if they changed
            if self.user_monitor and old_user_channels != new_user_channels:
                try:
                    await self.user_monitor.update_monitored_entities()
                    logger.info("✅ User monitor channels updated")
                    
                    if new_user_channels != old_user_channels:
                        await self._notify_admin_safe(
                            f"🔄 **User Monitor Channels Updated**\n\n"
                            f"📊 Now monitoring {len(new_user_channels)} user channels\n"
                            f"Configuration reloaded automatically."
                        )
                except Exception as e:
                    logger.error(f"❌ Failed to update user monitor channels: {e}")
                    
        except Exception as e:
            logger.error(f"Config reload error: {e}")
    
    async def _cleanup_database_task(self, context):
        """Database cleanup task"""
        try:
            logger.info("🧹 Running database cleanup...")
            await self.data_manager.cleanup_old_data(days=30)
            logger.info("✅ Database cleanup completed")
        except Exception as e:
            logger.error(f"Database cleanup error: {e}")
    
    async def _validate_bot_channels(self):
        """Validate bot channels on startup"""
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
                    invalid_channels.append(f"{channel_identifier} (error)")
                    logger.error(f"❌ Error accessing channel {channel_identifier}: {e}")
            
            # Log summary and notify admin
            if invalid_channels:
                logger.warning(f"⚠️ Channel validation: {len(valid_channels)} valid, {len(invalid_channels)} issues")
                await self._notify_admin_safe(
                    f"⚠️ **Bot Channel Validation**\n\n"
                    f"✅ Valid bot channels: {len(valid_channels)}\n"
                    f"❌ Issues found: {len(invalid_channels)}\n\n"
                    f"**Issues:**\n" + 
                    "\n".join([f"• {ch}" for ch in invalid_channels[:5]]) +
                    (f"\n... and {len(invalid_channels) - 5} more" if len(invalid_channels) > 5 else "") +
                    f"\n\nBot must be admin in channels to monitor them.\n"
                    f"Use User Monitor for channels where bot isn't admin."
                )
            else:
                logger.info(f"✅ All {len(valid_channels)} bot channels validated")
                
        except Exception as e:
            logger.error(f"Error in channel validation: {e}")
    
    async def _initialize_error_monitoring(self):
        """Initialize error monitoring"""
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
        """Notify admin about startup with system info"""
        if not self._admin_id:
            return
        
        try:
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
            
            startup_message += f"✅ Error monitoring active\n"
            
            if self._user_monitor_enabled:
                startup_message += f"🔄 User monitor: Initializing...\n"
            else:
                startup_message += f"ℹ️ User monitor: Disabled\n"
            
            startup_message += f"\n**Monitoring Capabilities:**\n"
            startup_message += f"• Bot channels: Where bot is admin\n"
            
            if self._user_monitor_enabled:
                startup_message += f"• User channels: Any public channel (via user account)\n"
            else:
                startup_message += f"• User channels: Not available (no credentials)\n"
            
            startup_message += f"\nUse `/admin` to see available commands"
            
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
        """Send notification to admin with timeout"""
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
        """Set up bot menu commands"""
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
        """Import from config files if database is empty"""
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
    
    async def run_polling_manually(self):
        """Run polling manually with proper event loop"""
        try:
            # Initialize the application
            await self.app.initialize()
            
            # Start background tasks (includes user monitor initialization)
            await self.start_background_tasks()
            
            # Start the updater
            await self.app.updater.start_polling(drop_pending_updates=True)
            
            # Start the application
            await self.app.start()
            
            logger.info("✅ Bot is now running and listening for updates...")
            
            # Keep running until stopped
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                
        except Exception as e:
            logger.error(f"Error in manual polling: {e}")
            raise
        finally:
            # Clean shutdown
            try:
                await self.app.stop()
                await self.app.updater.stop()
                await self.app.shutdown()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
    
    async def shutdown(self):
        """Graceful shutdown with user monitor cleanup"""
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

async def clear_webhook(token):
    """Clear webhook and pending updates"""
    try:
        from telegram import Bot
        bot = Bot(token)
        
        # First check current state
        info = await bot.get_webhook_info()
        if info.pending_update_count > 0 or info.url:
            logger.info(f"🧹 Clearing webhook (URL: {info.url or 'None'}, Pending: {info.pending_update_count})")
            await bot.delete_webhook(drop_pending_updates=True)
            
            # Verify it's cleared
            new_info = await bot.get_webhook_info()
            if new_info.pending_update_count > 0:
                logger.warning(f"⚠️ Still have {new_info.pending_update_count} pending updates after clearing")
            else:
                logger.info("✅ Webhook cleared successfully")
        else:
            logger.info("✅ No webhook or pending updates to clear")
            
    except Exception as e:
        logger.error(f"❌ Failed to clear webhook: {e}")

def main():
    """Main function with robust user monitor support"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN environment variable not set!")
        sys.exit(1)
    
    logger.info("🚀 Starting Job Collector Bot with User Monitor...")
    
    # Check run mode
    run_mode = os.getenv('RUN_MODE', 'polling')
    
    if run_mode == 'scheduled':
        # Run job collection once and exit
        logger.info("Starting in scheduled mode...")
        bot = JobCollectorBot(token)
        asyncio.run(bot.run_scheduled_job())
    else:
        # Default: Manual polling mode with user monitor
        logger.info("✅ Core functionality: Bot + User monitoring enabled")
        
        # Create new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Clear webhook first
            loop.run_until_complete(clear_webhook(token))
            
            # Create bot
            bot = JobCollectorBot(token)
            
            # Log configuration status
            if bot._admin_id:
                logger.info("✅ Admin functionality: Enabled")
            else:
                logger.info("ℹ️ Admin functionality: Disabled (no AUTHORIZED_ADMIN_ID)")
            
            if bot._user_monitor_enabled:
                logger.info("✅ User monitor: Will be enabled")
            else:
                logger.info("ℹ️ User monitor: Disabled (missing credentials)")
            
            # Run the bot manually
            loop.run_until_complete(bot.run_polling_manually())
            
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}")
        finally:
            # Cleanup
            try:
                if 'bot' in locals():
                    loop.run_until_complete(bot.shutdown())
            except Exception as e:
                logger.error(f"Shutdown error: {e}")
            finally:
                loop.close()

if __name__ == '__main__':
    main()