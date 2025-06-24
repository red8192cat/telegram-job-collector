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
        
        # Initialize managers with backup support
        logger.info("🔄 Initializing configuration manager with backup support...")
        self.config_manager = ConfigManager()  # This will auto-backup on startup
        
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
        
        # Import from config files if database is empty
        await self._import_on_startup()
        
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
            
            # Send enhanced startup notification with backup info
            await self.notify_admin_about_startup()
                
        except ImportError as e:
            logger.warning(f"Error monitoring not available: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize error monitoring: {e}")
    
    async def notify_admin_about_startup(self):
        """Notify admin about startup with backup info"""
        if not self._admin_id:
            return
        
        try:
            # Get backup info
            backups = self.config_manager.list_backups()
            backup_count = len(backups)
            latest_backup = backups[0]['created'] if backups else "None"
            
            startup_message = (
                f"🤖 **Bot Started Successfully**\n\n"
                f"✅ Error monitoring active\n"
                f"📊 Admin commands available\n"
                f"💾 Config backups: {backup_count} files\n"
                f"📅 Latest backup: {latest_backup}\n\n"
                f"Use `/admin backups` to manage config backups"
            )
            
            await self.app.bot.send_message(
                chat_id=self._admin_id,
                text=startup_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send startup notification with backup info: {e}")
    
    async def setup_bot_menu(self):
        """Set up bot menu commands - ALWAYS English but configurable via translations"""
        from telegram import BotCommand
        from utils.translations import get_text
        
        # FORCE English for bot menu (global standard) but use translations for flexibility
        menu_language = "en"  # Always English for bot menu commands
        
        commands = [
            BotCommand("start", get_text("menu_command_start", menu_language)),
            BotCommand("manage_keywords", get_text("menu_command_manage", menu_language)),
            BotCommand("my_settings", get_text("menu_command_settings", menu_language)),
            BotCommand("help", get_text("menu_command_help", menu_language)),
        ]
        
        try:
            await self.app.bot.set_my_commands(commands)
            logger.info("Bot menu commands set (English - configurable via translations)")
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
