#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot - COMPLETE VERSION
Organized lifecycle management with BotConfig and event system integration
"""

import asyncio
import logging
import signal
import sys
from telegram.ext import Application

from config import BotConfig
from events import get_event_bus, EventType, emit_system_status
from handlers.commands import CommandHandlers
from handlers.callbacks import CallbackHandlers
from handlers.messages import MessageHandlers
from handlers.admin_commands import AdminCommandHandlers
from storage.sqlite_manager import SQLiteManager
from monitoring.health_monitor import HealthMonitor

logger = logging.getLogger(__name__)

class JobCollectorBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        self.event_bus = get_event_bus()
        
        # Core components
        self.data_manager = SQLiteManager(config)
        self.command_handlers = CommandHandlers(config, self.data_manager)
        self.callback_handlers = CallbackHandlers(config, self.data_manager)
        self.message_handlers = MessageHandlers(config, self.data_manager)
        self.admin_handlers = AdminCommandHandlers(config, self.data_manager)
        self.health_monitor = HealthMonitor(config, self.data_manager)
        
        # User Monitor setup - will be initialized later
        self.user_monitor = None
        self._user_monitor_task = None
        self.mode = "initializing"  # "full", "bot-only", "degraded"
        
        # Background tasks
        self._background_tasks = []
        self._shutdown_event = asyncio.Event()
        
        # Register handlers
        self._register_handlers()
        
        # Subscribe to events
        self._subscribe_to_events()
        
    def _register_handlers(self):
        """Register all command and message handlers"""
        self.command_handlers.register(self.app)
        self.callback_handlers.register(self.app)
        self.message_handlers.register(self.app)
        self.admin_handlers.register(self.app)
        
        # Set bot instance for message forwarding
        self.message_handlers.set_bot_instance(self.app.bot)
        
        logger.info("✅ All core handlers registered successfully")
    
    def _subscribe_to_events(self):
        """Subscribe to relevant events"""
        # System events
        self.event_bus.subscribe(EventType.SYSTEM_ERROR, self._handle_system_error)
        self.event_bus.subscribe(EventType.USER_MONITOR_ERROR, self._handle_user_monitor_error)
        self.event_bus.subscribe(EventType.USER_MONITOR_DISCONNECTED, self._handle_user_monitor_disconnected)
        
        logger.info("✅ Event system subscriptions configured")
    
    async def _handle_system_error(self, event):
        """Handle system error events"""
        try:
            error_info = event.data
            component = error_info.get('component', 'unknown')
            error_msg = error_info.get('error', 'Unknown error')
            
            logger.error(f"System error in {component}: {error_msg}")
            
            # Notify admin if configured
            if self.config.AUTHORIZED_ADMIN_ID:
                await self._notify_admin_safe(
                    f"🚨 **System Error**\n\n"
                    f"**Component:** {component}\n"
                    f"**Error:** {error_msg[:200]}\n\n"
                    f"Check logs for details."
                )
        except Exception as e:
            logger.error(f"Error handling system error event: {e}")
    
    async def _handle_user_monitor_error(self, event):
        """Handle user monitor error events"""
        try:
            if self.mode == "full":
                self.mode = "degraded"
                logger.warning("⚠️ Switching to degraded mode due to user monitor error")
                
                if self.config.AUTHORIZED_ADMIN_ID:
                    await self._notify_admin_safe(
                        "⚠️ **System Degraded**\n\n"
                        "User monitor encountered errors.\n"
                        "Bot channels continue working normally.\n"
                        "Use `/admin health` to check status."
                    )
        except Exception as e:
            logger.error(f"Error handling user monitor error: {e}")
    
    async def _handle_user_monitor_disconnected(self, event):
        """Handle user monitor disconnection events"""
        try:
            if self.mode == "full":
                self.mode = "bot-only"
                logger.info("ℹ️ Switching to bot-only mode due to user monitor disconnection")
        except Exception as e:
            logger.error(f"Error handling user monitor disconnection: {e}")
    
    # =============================================================================
    # LIFECYCLE MANAGEMENT METHODS
    # =============================================================================
    
    async def initialize(self):
        """Complete bot initialization sequence"""
        try:
            logger.info("🔄 Starting bot initialization...")
            
            # Validate configuration
            await self._validate_configuration()
            
            # Initialize database
            await self._initialize_database()
            
            # Initialize error monitoring
            await self._initialize_error_monitoring()
            
            # Initialize user monitor if enabled
            await self._initialize_user_monitor()
            
            # Validate channels
            await self._validate_channels()
            
            # Set bot menu
            await self._setup_bot_menu()
            
            # Determine final mode
            self._determine_operating_mode()
            
            # Emit startup event
            await emit_system_status("startup", f"Bot initialized in {self.mode} mode")
            
            logger.info(f"✅ Bot initialization completed in {self.mode} mode")
            
        except Exception as e:
            logger.error(f"❌ Bot initialization failed: {e}")
            await emit_system_status("error", f"Initialization failed: {str(e)}")
            raise
    
    async def _validate_configuration(self):
        """Validate bot configuration"""
        logger.info("🔄 Validating configuration...")
        
        errors = self.config.validate()
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"• {error}" for error in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("✅ Configuration validation passed")
    
    async def _initialize_database(self):
        """Initialize database with migration support"""
        logger.info("🔄 Initializing database...")
        
        try:
            await self.data_manager.initialize()
            logger.info("✅ Database initialized successfully")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    async def _initialize_error_monitoring(self):
        """Initialize error monitoring system"""
        if not self.config.ENABLE_ERROR_MONITORING or not self.config.AUTHORIZED_ADMIN_ID:
            logger.info("ℹ️ Error monitoring disabled")
            return
        
        try:
            from utils.error_monitor import setup_error_monitoring
            setup_error_monitoring(self.app.bot, self.config.AUTHORIZED_ADMIN_ID)
            logger.info("✅ Error monitoring initialized")
            
            # Send startup notification
            await self._send_startup_notification()
            
        except ImportError:
            logger.warning("⚠️ Error monitoring module not available")
        except Exception as e:
            logger.error(f"❌ Error monitoring initialization failed: {e}")
    
    async def _initialize_user_monitor(self):
        """Initialize user monitor if enabled"""
        if not self.config.ENABLE_USER_MONITOR:
            logger.info("ℹ️ User monitor disabled in configuration")
            return
        
        credentials = self.config.get_user_monitor_credentials()
        if not credentials:
            logger.info("ℹ️ User monitor disabled (no credentials)")
            return
        
        try:
            logger.info("🔄 Initializing user monitor...")
            
            # Import and create user monitor
            from monitoring.user_monitor import UserAccountMonitor
            self.user_monitor = UserAccountMonitor(
                self.config,
                self.data_manager,
                bot_instance=self.app.bot
            )
            
            # Store in bot_data for admin commands
            self.app.bot_data["user_monitor"] = self.user_monitor
            self.app.bot_data["bot_instance"] = self
            
            # Start initialization in background
            self._user_monitor_task = asyncio.create_task(
                self._user_monitor_initialization_flow()
            )
            
            logger.info("✅ User monitor initialization started")
            
        except ImportError as e:
            logger.warning(f"⚠️ User monitor dependencies not available: {e}")
        except Exception as e:
            logger.error(f"❌ User monitor initialization failed: {e}")
            await self._notify_admin_safe(
                f"❌ **User Monitor Error**\n\n{str(e)}\n\n"
                f"Bot will continue in bot-only mode."
            )
    
    async def _user_monitor_initialization_flow(self):
        """Complete user monitor initialization flow"""
        try:
            # Give the main event loop time to stabilize
            await asyncio.sleep(3)
            
            logger.info("🔄 Starting user monitor authentication...")
            success = await self.user_monitor.initialize()
            
            if success:
                logger.info("✅ User monitor authenticated successfully")
                await self.user_monitor.start_monitoring()
                
                # Update mode
                self.mode = "full"
                
                # Notify admin
                channel_count = len(self.user_monitor.monitored_entities)
                await self._notify_admin_safe(
                    f"🎉 **User Monitor Active!**\n\n"
                    f"✅ Authentication successful\n"
                    f"📊 Monitoring {channel_count} user channels\n"
                    f"🎯 Bot now running in **full mode**"
                )
                
            else:
                logger.warning("⚠️ User monitor needs authentication")
                await self._notify_admin_safe(
                    f"🔐 **User Monitor Authentication Required**\n\n"
                    f"📱 Check your phone for SMS verification code\n"
                    f"📨 Send the code directly to this chat\n\n"
                    f"Use `/auth_status` to check status"
                )
                
        except Exception as e:
            logger.error(f"❌ User monitor initialization flow error: {e}")
            await self._notify_admin_safe(
                f"❌ **User Monitor Error**\n\n{str(e)}\n\n"
                f"Bot continues in bot-only mode.\n"
                f"Use `/auth_restart` to retry."
            )
    
    async def _validate_channels(self):
        """Validate bot channels on startup"""
        logger.info("🔄 Validating bot channels...")
        
        try:
            bot_channels = await self.data_manager.get_simple_bot_channels()
            if not bot_channels:
                logger.info("ℹ️ No bot channels configured")
                return
            
            valid_channels = []
            invalid_channels = []
            
            for chat_id in bot_channels:
                try:
                    # Get chat info with timeout
                    chat = await asyncio.wait_for(
                        self.app.bot.get_chat(chat_id),
                        timeout=self.config.CHANNEL_VALIDATION_TIMEOUT
                    )
                    
                    # Check if bot is admin
                    try:
                        bot_member = await asyncio.wait_for(
                            self.app.bot.get_chat_member(chat.id, self.app.bot.id),
                            timeout=self.config.CHANNEL_VALIDATION_TIMEOUT
                        )
                        is_admin = bot_member.status in ['administrator', 'creator']
                    except Exception:
                        is_admin = False
                    
                    display_name = await self.data_manager.get_channel_display_name(chat_id)
                    
                    if is_admin:
                        valid_channels.append(display_name)
                        logger.info(f"✅ Bot channel validated: {display_name}")
                    else:
                        invalid_channels.append(f"{display_name} (not admin)")
                        logger.warning(f"⚠️ Bot not admin in: {display_name}")
                
                except asyncio.TimeoutError:
                    display_name = await self.data_manager.get_channel_display_name(chat_id)
                    invalid_channels.append(f"{display_name} (timeout)")
                    logger.error(f"❌ Timeout validating channel: {display_name}")
                except Exception as e:
                    display_name = await self.data_manager.get_channel_display_name(chat_id)
                    invalid_channels.append(f"{display_name} (error)")
                    logger.error(f"❌ Error validating channel {display_name}: {e}")
            
            # Notify admin if there are issues
            if invalid_channels and self.config.AUTHORIZED_ADMIN_ID:
                await self._notify_admin_safe(
                    f"⚠️ **Channel Validation Results**\n\n"
                    f"✅ Valid: {len(valid_channels)}\n"
                    f"❌ Issues: {len(invalid_channels)}\n\n"
                    f"**Issues:**\n" +
                    "\n".join([f"• {ch}" for ch in invalid_channels[:5]]) +
                    (f"\n... and {len(invalid_channels) - 5} more" if len(invalid_channels) > 5 else "") +
                    f"\n\nBot must be admin to monitor channels."
                )
            else:
                logger.info(f"✅ All {len(valid_channels)} bot channels validated")
                
        except Exception as e:
            logger.error(f"❌ Channel validation error: {e}")
    
    async def _setup_bot_menu(self):
        """Set up bot menu commands"""
        try:
            from telegram import BotCommand
            from utils.translations import get_text
            
            commands = [
                BotCommand("start", get_text("menu_command_start", "en")),
                BotCommand("manage_keywords", get_text("menu_command_manage", "en")),
                BotCommand("my_settings", get_text("menu_command_settings", "en")),
                BotCommand("help", get_text("menu_command_help", "en")),
            ]
            
            await asyncio.wait_for(
                self.app.bot.set_my_commands(commands),
                timeout=self.config.TELEGRAM_API_TIMEOUT
            )
            logger.info("✅ Bot menu commands configured")
        except Exception as e:
            logger.warning(f"⚠️ Could not set bot menu: {e}")
    
    def _determine_operating_mode(self):
        """Determine final operating mode"""
        if self.user_monitor and self.user_monitor.is_connected():
            self.mode = "full"
        else:
            self.mode = "bot-only"
        
        logger.info(f"🎯 Bot operating mode: {self.mode}")
    
    async def start_background_tasks(self):
        """Start background tasks using job queue"""
        if not self.app.job_queue:
            logger.warning("⚠️ JobQueue not available - background tasks disabled")
            return
        
        try:
            # Health monitoring
            self.app.job_queue.run_repeating(
                self.health_monitor.run_health_check,
                interval=self.config.HEALTH_CHECK_INTERVAL,
                first=60
            )
            
            # Database cleanup
            self.app.job_queue.run_repeating(
                self._cleanup_database_task,
                interval=self.config.AUTO_BACKUP_INTERVAL,
                first=3600
            )
            
            # User monitor health check
            if self.user_monitor:
                self.app.job_queue.run_repeating(
                    self._check_user_monitor_health,
                    interval=300,  # 5 minutes
                    first=120
                )
            
            logger.info("✅ Background tasks scheduled")
            
        except Exception as e:
            logger.error(f"❌ Failed to start background tasks: {e}")
    
    async def _cleanup_database_task(self, context):
        """Database cleanup background task"""
        try:
            deleted_count = await self.data_manager.cleanup_old_data(
                days=self.config.BACKUP_RETENTION_DAYS
            )
            if deleted_count > 0:
                logger.info(f"🧹 Database cleanup: removed {deleted_count} old records")
        except Exception as e:
            logger.error(f"❌ Database cleanup error: {e}")
    
    async def _check_user_monitor_health(self, context):
        """User monitor health check background task"""
        if not self.user_monitor:
            return
        
        try:
            if not self.user_monitor.is_connected():
                logger.warning("⚠️ User monitor disconnected, attempting reconnect...")
                success = await self.user_monitor.reconnect()
                
                if success:
                    logger.info("✅ User monitor reconnected")
                    self.mode = "full"
                    await self._notify_admin_safe(
                        "✅ **User Monitor Reconnected**\n\n"
                        "Connection restored automatically."
                    )
                else:
                    logger.error("❌ User monitor reconnection failed")
                    self.mode = "degraded"
                    
        except Exception as e:
            logger.error(f"❌ User monitor health check error: {e}")
    
    async def _send_startup_notification(self):
        """Send startup notification to admin"""
        if not self.config.AUTHORIZED_ADMIN_ID:
            return
        
        try:
            credentials = self.config.get_user_monitor_credentials()
            
            message = (
                f"🤖 **Bot Started Successfully**\n\n"
                f"✅ Core functionality active\n"
                f"✅ Database initialized\n"
                f"✅ Error monitoring active\n"
            )
            
            if credentials:
                message += f"🔄 User monitor: Initializing...\n"
            else:
                message += f"ℹ️ User monitor: Disabled (no credentials)\n"
            
            message += f"\n**Mode:** {self.mode}\n"
            message += f"**Admin commands:** `/admin`"
            
            await self._notify_admin_safe(message)
            
        except Exception as e:
            logger.warning(f"⚠️ Could not send startup notification: {e}")
    
    async def _notify_admin_safe(self, message: str):
        """Send notification to admin with timeout and error handling"""
        if not self.config.AUTHORIZED_ADMIN_ID:
            return
        
        try:
            await asyncio.wait_for(
                self.app.bot.send_message(
                    chat_id=self.config.AUTHORIZED_ADMIN_ID,
                    text=message,
                    parse_mode='Markdown'
                ),
                timeout=self.config.TELEGRAM_API_TIMEOUT
            )
        except Exception as e:
            logger.error(f"❌ Failed to notify admin: {e}")
    
    # =============================================================================
    # MAIN EXECUTION METHODS
    # =============================================================================
    
    async def run_polling(self):
        """Run bot in polling mode with complete lifecycle"""
        try:
            # Initialize application
            await self.app.initialize()
            logger.info("✅ Telegram application initialized")
            
            # Complete bot initialization
            await self.initialize()
            
            # Start background tasks
            await self.start_background_tasks()
            
            # Start polling
            await self.app.updater.start_polling(
                drop_pending_updates=True,
                read_timeout=self.config.TELEGRAM_API_TIMEOUT,
                write_timeout=self.config.TELEGRAM_API_TIMEOUT,
                connect_timeout=self.config.TELEGRAM_API_TIMEOUT
            )
            
            # Start application
            await self.app.start()
            
            logger.info("✅ Bot is running and listening for updates...")
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"❌ Error in polling mode: {e}")
            raise
        finally:
            await self.shutdown()
    
    async def run_scheduled_job(self):
        """Run job collection once and exit"""
        try:
            await self.app.initialize()
            await self.initialize()
            
            # Run job collection
            await self.message_handlers.collect_and_repost_jobs(self.app.bot)
            
        except Exception as e:
            logger.error(f"❌ Error in scheduled job: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown with complete cleanup"""
        logger.info("🛑 Starting graceful shutdown...")
        
        try:
            # Signal shutdown
            self._shutdown_event.set()
            
            # Stop user monitor task
            if self._user_monitor_task and not self._user_monitor_task.done():
                self._user_monitor_task.cancel()
                try:
                    await asyncio.wait_for(self._user_monitor_task, timeout=5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Stop user monitor
            if self.user_monitor:
                await self.user_monitor.stop()
            
            # Stop application
            if self.app.running:
                await self.app.stop()
            
            if self.app.updater.running:
                await self.app.updater.stop()
            
            # Close database
            await self.data_manager.close()
            
            # Shutdown application
            await self.app.shutdown()
            
            # Emit shutdown event
            await emit_system_status("shutdown", "Graceful shutdown completed")
            
            logger.info("✅ Graceful shutdown completed")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")

# =============================================================================
# MAIN EXECUTION
# =============================================================================

async def clear_webhook(token):
    """Clear webhook and pending updates"""
    try:
        from telegram import Bot
        bot = Bot(token)
        
        info = await bot.get_webhook_info()
        if info.pending_update_count > 0 or info.url:
            logger.info(f"🧹 Clearing webhook (pending updates: {info.pending_update_count})")
            await bot.delete_webhook(drop_pending_updates=True)
            
            new_info = await bot.get_webhook_info()
            if new_info.pending_update_count == 0:
                logger.info("✅ Webhook cleared successfully")
            else:
                logger.warning(f"⚠️ Still have {new_info.pending_update_count} pending updates")
        else:
            logger.info("✅ No webhook cleanup needed")
            
    except Exception as e:
        logger.error(f"❌ Failed to clear webhook: {e}")

def setup_signal_handlers(bot):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(bot.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def main():
    """Main function with complete error handling"""
    # Load configuration
    try:
        config = BotConfig.from_env_file()
        config.setup_logging()
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
    
    logger.info("🚀 Starting Job Collector Bot...")
    
    # Validate token
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not configured!")
        sys.exit(1)
    
    # Determine run mode
    run_mode = config.__dict__.get('RUN_MODE', 'polling')
    
    # Create event loop
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Clear webhook first
        loop.run_until_complete(clear_webhook(config.TELEGRAM_BOT_TOKEN))
        
        # Create bot
        bot = JobCollectorBot(config)
        
        # Setup signal handlers
        setup_signal_handlers(bot)
        
        # Log configuration status
        logger.info(f"🎯 Operating mode: {bot.mode}")
        logger.info(f"✅ Admin: {'Enabled' if config.AUTHORIZED_ADMIN_ID else 'Disabled'}")
        logger.info(f"✅ User Monitor: {'Enabled' if config.ENABLE_USER_MONITOR else 'Disabled'}")
        logger.info(f"✅ Error Monitoring: {'Enabled' if config.ENABLE_ERROR_MONITORING else 'Disabled'}")
        
        # Run bot
        if run_mode == 'scheduled':
            logger.info("📅 Running in scheduled mode")
            loop.run_until_complete(bot.run_scheduled_job())
        else:
            logger.info("🔄 Running in polling mode")
            loop.run_until_complete(bot.run_polling())
            
    except KeyboardInterrupt:
        logger.info("👋 Received keyboard interrupt")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}")
        sys.exit(1)
    finally:
        try:
            loop.close()
        except Exception as e:
            logger.error(f"❌ Error closing event loop: {e}")

if __name__ == '__main__':
    main()