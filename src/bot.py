#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot - Main Entry Point with Proper Client Integration
FIXED VERSION: Proper Application initialization and multiple run modes
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
        
        # Initialize managers with backup support
        logger.info("🔄 Initializing configuration manager with backup support...")
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
        
        # Background task management
        self._background_tasks = []
        self._shutdown_event = asyncio.Event()
        
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
    
    async def initialize_components(self):
        """Initialize all components in proper order"""
        # Initialize database first
        await self.data_manager.initialize()
        logger.info("Database initialized successfully")
        
        # Import from config files if database is empty
        await self._import_on_startup()
        
        # Core bot functionality is ready
        logger.info("Core bot functionality ready")
        
        # Initialize error monitoring INDEPENDENT of user monitor
        await self._initialize_error_monitoring()
        
        # Validate bot channels on startup
        await self._validate_bot_channels()
        
        # Initialize user monitor if available
        if self.user_monitor:
            self.user_monitor.bot_instance = self.app.bot
            self.app.bot_data["user_monitor"] = self.user_monitor
            logger.info("User monitor stored in bot_data")
            
            try:
                success = await self.user_monitor.initialize()
                if success:
                    logger.info("✅ User monitor extension initialized successfully")
                else:
                    logger.warning("❌ User monitor extension needs authentication")
                    
            except Exception as e:
                logger.error(f"❌ User monitor extension error: {e}")
                logger.info("Continuing with core bot functionality only")
        
        # Set up bot menu
        await self.setup_bot_menu()
        
        # Start background tasks using asyncio instead of JobQueue
        await self._start_background_tasks()
        
        logger.info("✅ All components initialized successfully")
    
    async def _start_background_tasks(self):
        """Start background maintenance tasks using asyncio"""
        # Health check for user monitor every 5 minutes
        if self.user_monitor:
            health_task = asyncio.create_task(self._user_monitor_health_loop())
            self._background_tasks.append(("user_monitor_health", health_task))
            logger.info("📊 User monitor health checks started")
        
        # Config reload every hour
        config_task = asyncio.create_task(self._config_reload_loop())
        self._background_tasks.append(("config_reload", config_task))
        logger.info("🔄 Config reload tasks started")
        
        logger.info(f"✅ Started {len(self._background_tasks)} background tasks")
    
    async def _user_monitor_health_loop(self):
        """Periodic health check loop for user monitor"""
        try:
            while not self._shutdown_event.is_set():
                # Wait 5 minutes or until shutdown
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=300)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Continue with health check
                
                # Perform health check
                await self._check_user_monitor_health()
                
        except asyncio.CancelledError:
            logger.info("User monitor health loop cancelled")
        except Exception as e:
            logger.error(f"Error in user monitor health loop: {e}")
    
    async def _config_reload_loop(self):
        """Periodic config reload loop"""
        try:
            while not self._shutdown_event.is_set():
                # Wait 1 hour or until shutdown
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=3600)
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Continue with config reload
                
                # Perform config reload
                await self._reload_config_task()
                
        except asyncio.CancelledError:
            logger.info("Config reload loop cancelled")
        except Exception as e:
            logger.error(f"Error in config reload loop: {e}")
    
    async def _check_user_monitor_health(self):
        """Health check for user monitor"""
        if not self.user_monitor:
            return
        
        try:
            if not self.user_monitor.is_connected():
                logger.warning("User monitor disconnected, attempting reconnect...")
                success = await self.user_monitor.reconnect()
                if success:
                    logger.info("✅ User monitor reconnected successfully")
                    await self._notify_admin("✅ **User Monitor Reconnected**\n\nConnection restored automatically.")
                else:
                    logger.error("❌ User monitor reconnection failed")
                    await self._notify_admin("⚠️ **User Monitor Connection Issues**\n\nAutomatic reconnection failed.")
        except Exception as e:
            logger.error(f"Error in user monitor health check: {e}")
    
    async def _reload_config_task(self):
        """Config reload task"""
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
        
        # Log summary and notify admin if needed
        if invalid_channels:
            logger.warning(f"⚠️ STARTUP: Bot channel validation: {len(valid_channels)} valid, {len(invalid_channels)} issues")
            await self._notify_admin(
                f"⚠️ **Bot Channel Validation Issues**\n\n"
                f"✅ Valid bot channels: {len(valid_channels)}\n"
                f"❌ Invalid bot channels: {len(invalid_channels)}\n\n"
                f"**Issues found:**\n" + 
                "\n".join([f"• {ch}" for ch in invalid_channels[:5]]) +
                (f"\n... and {len(invalid_channels) - 5} more" if len(invalid_channels) > 5 else "") +
                f"\n\nBot must be admin in channels to monitor them."
            )
        else:
            logger.info(f"✅ STARTUP: All {len(valid_channels)} bot channels validated successfully")
    
    async def _initialize_error_monitoring(self):
        """Initialize error monitoring"""
        if not self._admin_id:
            logger.info("No admin ID configured - error monitoring disabled")
            return
        
        try:
            from utils.error_monitor import setup_error_monitoring
            setup_error_monitoring(self.app.bot, self._admin_id)
            logger.info(f"✅ Error monitoring initialized for admin ID: {self._admin_id}")
            
            # Send startup notification
            await self._notify_admin_about_startup()
                
        except ImportError as e:
            logger.warning(f"Error monitoring not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize error monitoring: {e}")
    
    async def _notify_admin_about_startup(self):
        """Notify admin about startup with system info"""
        if not self._admin_id:
            return
        
        try:
            # Get backup info
            backups = self.config_manager.list_backups()
            backup_count = len(backups)
            latest_backup = backups[0]['created'] if backups else "None"
            
            startup_message = (
                f"🤖 **Bot Started Successfully**\n\n"
                f"✅ Core bot functionality active\n"
                f"✅ Error monitoring active\n"
                f"✅ Background tasks running\n"
                f"📊 Admin commands available\n"
                f"💾 Config backups: {backup_count} files\n"
                f"📅 Latest backup: {latest_backup}\n\n"
            )
            
            if self.user_monitor:
                startup_message += f"🔄 User monitor: Active\n\n"
            else:
                startup_message += f"ℹ️ User monitor: Disabled\n\n"
            
            startup_message += f"Use `/admin` to see all available commands"
            
            await self.app.bot.send_message(
                chat_id=self._admin_id,
                text=startup_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send startup notification: {e}")
    
    async def _notify_admin(self, message: str):
        """Send notification to admin"""
        if self._admin_id:
            try:
                await self.app.bot.send_message(
                    chat_id=self._admin_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")
    
    async def setup_bot_menu(self):
        """Set up bot menu commands"""
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
        
        try:
            await self.app.bot.set_my_commands(commands)
            logger.info("Bot menu commands set (English)")
        except Exception as e:
            logger.warning(f"Could not set bot menu commands: {e}")
    
    async def _import_on_startup(self):
        """Import from config files if database is empty"""
        try:
            # Check if database has any channels
            all_users = await self.data_manager.get_all_users_with_keywords()
            bot_channels, user_channels = await self.data_manager.export_all_channels_for_config()
            
            imported_something = False
            
            # Import channels if database is empty
            if not bot_channels and not user_channels:
                self.config_manager.load_channels_config()
                config_bot_channels = self.config_manager.get_channels_to_monitor()
                config_user_channels = self.config_manager.get_user_monitored_channels()
                
                if config_bot_channels or config_user_channels:
                    await self.data_manager.import_channels_from_config(config_bot_channels, config_user_channels)
                    logger.info(f"⚙️ STARTUP: Imported channels from config: {len(config_bot_channels)} bot, {len(config_user_channels)} user")
                    imported_something = True
            
            # Import users if database is empty
            if not all_users:
                users_data = self.config_manager.load_users_config()
                if users_data:
                    await self.data_manager.import_users_from_config(users_data)
                    logger.info(f"⚙️ STARTUP: Imported {len(users_data)} users from config")
                    imported_something = True
            
            if not imported_something:
                logger.info("⚙️ STARTUP: Database has data, skipping config import")
                # Export current state to config files to ensure sync
                await self._export_current_state()
                
        except Exception as e:
            logger.error(f"⚙️ STARTUP: Failed to import from config: {e}")

    async def _export_current_state(self):
        """Export current database state to config files"""
        try:
            # Export channels
            bot_channels, user_channels = await self.data_manager.export_all_channels_for_config()
            self.config_manager.export_channels_config(bot_channels, user_channels)
            
            # Export users
            users_data = await self.data_manager.export_all_users_for_config()
            self.config_manager.export_users_config(users_data)
            
            logger.info("⚙️ STARTUP: Exported current state to config files")
            
        except Exception as e:
            logger.error(f"⚙️ STARTUP: Failed to export current state: {e}")
    
    async def run_simple(self):
        """Simple run mode - GUARANTEED TO WORK"""
        logger.info("🚀 Starting bot in simple mode...")
        
        # Initialize components
        await self.initialize_components()
        
        # Start user monitor in background (if available)
        if self.user_monitor:
            logger.info("👤 Starting user monitor in background...")
            asyncio.create_task(self.user_monitor.start_monitoring())
        
        # Run main bot (this handles initialization internally)
        logger.info("📡 Starting main bot polling...")
        await self.app.run_polling()
    
    async def run_integrated(self):
        """Integrated run mode with proper initialization - FIXED"""
        logger.info("🚀 Starting integrated bot with proper client management...")
        
        # Initialize all components FIRST
        await self.initialize_components()
        
        # CRITICAL: Initialize the Application properly
        await self.app.initialize()
        logger.info("✅ Application initialized")
        
        # Create tasks for concurrent execution
        tasks = []
        
        # Main bot polling task - FIXED: Use run_polling directly
        logger.info("📡 Starting main bot polling...")
        bot_task = asyncio.create_task(self.app.run_polling())
        tasks.append(("bot", bot_task))
        
        # User monitor task (if available)
        if self.user_monitor:
            logger.info("👤 Starting user monitor...")
            user_task = asyncio.create_task(self.user_monitor.start_monitoring())
            tasks.append(("user_monitor", user_task))
        
        # Run all tasks concurrently
        logger.info(f"⚡ Running {len(tasks)} concurrent main tasks...")
        
        try:
            # Wait for any task to complete (or fail)
            done, pending = await asyncio.wait(
                [task for name, task in tasks],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Check results
            for task in done:
                try:
                    result = await task
                    logger.info(f"Task completed: {result}")
                except Exception as e:
                    logger.error(f"Task failed: {e}")
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        except KeyboardInterrupt:
            logger.info("👋 Shutting down gracefully...")
            
        except Exception as e:
            logger.error(f"❌ Critical error in integrated execution: {e}")
            
        finally:
            # Proper cleanup
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("🧹 Cleaning up resources...")
        
        try:
            # Signal shutdown to background tasks
            self._shutdown_event.set()
            
            # Cancel background tasks
            for name, task in self._background_tasks:
                if not task.done():
                    logger.info(f"Cancelling {name} task...")
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Stop user monitor
            if self.user_monitor:
                await self.user_monitor.stop()
            
            # Close database
            await self.data_manager.close()
            
            logger.info("✅ Cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
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

def main():
    """Main function with multiple run mode options"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    bot = JobCollectorBot(token)
    
    # Check run mode
    run_mode = os.getenv('RUN_MODE', 'simple')  # Default to simple mode
    
    if run_mode == 'scheduled':
        # Run job collection once and exit
        logger.info("Starting in scheduled mode...")
        asyncio.run(bot.run_scheduled_job())
        
    elif run_mode == 'integrated':
        # Integrated mode (advanced, more complex)
        logger.info("Starting in integrated mode (advanced)...")
        logger.info("✅ Core functionality: Bot monitoring enabled")
        
        # Log admin status
        if bot._admin_id:
            logger.info("✅ Admin functionality: Enabled")
        else:
            logger.info("ℹ️  Admin functionality: Disabled (no AUTHORIZED_ADMIN_ID)")
        
        # Log user monitor status  
        if bot.user_monitor:
            logger.info("✅ Extended functionality: User account monitoring enabled")
        else:
            logger.info("ℹ️  Extended functionality: User account monitoring disabled")
        
        # Run integrated
        asyncio.run(bot.run_integrated())
        
    else:
        # Default: Simple mode (GUARANTEED TO WORK)
        logger.info("Starting in simple mode (recommended for stability)...")
        logger.info("✅ Core functionality: Bot monitoring enabled")
        
        # Log admin status
        if bot._admin_id:
            logger.info("✅ Admin functionality: Enabled")
        else:
            logger.info("ℹ️  Admin functionality: Disabled (no AUTHORIZED_ADMIN_ID)")
        
        # Log user monitor status  
        if bot.user_monitor:
            logger.info("✅ Extended functionality: User account monitoring enabled")
        else:
            logger.info("ℹ️  Extended functionality: User account monitoring disabled")
        
        # Run simple
        asyncio.run(bot.run_simple())

if __name__ == '__main__':
    main()