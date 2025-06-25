"""
Command Handlers - PRODUCTION VERSION
Integrated with BotConfig and event system, enhanced admin channel management
Consistent with project architecture and graceful degradation
"""

import logging
import re
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

from config import BotConfig
from storage.sqlite_manager import SQLiteManager
from events import get_event_bus, EventType
from utils.helpers import (
    is_private_chat, create_main_menu, get_help_text, 
    create_keywords_help_keyboard, create_ignore_keywords_help_keyboard,
    create_language_selection_keyboard, format_settings_message,
    format_manage_keywords_message, create_manage_keywords_keyboard,
    create_settings_keyboard
)
from utils.translations import get_text, is_supported_language

logger = logging.getLogger(__name__)

class CommandHandlers:
    def __init__(self, config: BotConfig, data_manager: SQLiteManager):
        self.config = config
        self.data_manager = data_manager
        self.event_bus = get_event_bus()
        logger.info("Command handlers initialized with configuration")
    
    def _is_authorized_admin(self, update: Update) -> bool:
        """Check if user is authorized admin"""
        if not self.config.AUTHORIZED_ADMIN_ID:
            return False
        
        user_id = update.effective_user.id
        return user_id == self.config.AUTHORIZED_ADMIN_ID
    
    def register(self, app):
        """Register command handlers"""
        # Essential user commands
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("manage_keywords", self.manage_keywords_command))
        app.add_handler(CommandHandler("my_settings", self.show_settings_command))
        
        # Legacy commands (hidden from menu but still work)
        app.add_handler(CommandHandler("keywords", self.set_keywords_command))
        app.add_handler(CommandHandler("ignore_keywords", self.set_ignore_keywords_command))
        app.add_handler(CommandHandler("purge_ignore", self.purge_ignore_keywords_command))
        
        # Admin commands (only if admin is configured)
        if self.config.AUTHORIZED_ADMIN_ID:
            app.add_handler(CommandHandler("auth_status", self.auth_status_command))
            app.add_handler(CommandHandler("auth_restart", self.auth_restart_command))
            app.add_handler(CommandHandler("admin", self.admin_command))
        
        # Authentication handler for non-command messages (admin only)
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            self.handle_auth_message
        ), group=10)
        
        # Handler for messages that start with @bot_name (from inline queries)
        app.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE,
            self.handle_bot_mention_message
        ), group=20)
        
        logger.info("Enhanced command handlers registered")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with language selection for new users"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        logger.info(f"Start command from user {user_id}")
        
        try:
            # Get user's current language
            user_language = await self.data_manager.get_user_language(user_id)
            
            # Check if user is completely new
            user_exists = await self._user_has_interacted_before(user_id)
            
            if not user_exists:
                # New user - show language selection first
                welcome_msg = get_text("language_selection_message", self.config.DEFAULT_LANGUAGE)
                keyboard = create_language_selection_keyboard()
                
                await update.message.reply_text(welcome_msg, reply_markup=keyboard)
                
                # Emit user registered event
                await self.event_bus.emit(EventType.USER_REGISTERED, {
                    'user_id': user_id,
                    'language': self.config.DEFAULT_LANGUAGE
                }, source='commands')
                
            else:
                # Existing user - show main menu in their language
                welcome_msg = get_text("welcome_message", user_language)
                menu_markup = create_main_menu(user_language)
                await update.message.reply_text(welcome_msg, reply_markup=menu_markup)
                
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'start_command',
                'user_id': user_id
            }, source='commands')
            
            # Fallback response
            await update.message.reply_text("Welcome! Please try again.")
    
    async def _user_has_interacted_before(self, user_id: int) -> bool:
        """Check if user has interacted with bot before"""
        try:
            # Check if user has keywords set
            keywords = await self.data_manager.get_user_keywords(user_id)
            if keywords:
                return True
            
            # Check if user has custom language
            language = await self.data_manager.get_user_language(user_id)
            return language != self.config.DEFAULT_LANGUAGE
            
        except Exception:
            return False
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_help_text(language))
            
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'help_command',
                'user_id': user_id
            }, source='commands')
    
    async def manage_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /manage_keywords command - unified keyword management"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
            language = await self.data_manager.get_user_language(user_id)
            
            # Get current keywords and ignore keywords
            keywords = await self.data_manager.get_user_keywords(user_id)
            ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_id)
            
            # Format message with current status
            title = get_text("manage_keywords_title", language)
            status_msg = format_manage_keywords_message(keywords, ignore_keywords, language)
            full_msg = f"{title}\n\n{status_msg}"
            
            # Create keyboard based on current state
            keyboard = create_manage_keywords_keyboard(
                has_keywords=bool(keywords),
                has_ignore=bool(ignore_keywords),
                language=language
            )
            
            await update.message.reply_text(full_msg, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error in manage keywords command: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'manage_keywords_command',
                'user_id': user_id
            }, source='commands')
    
    async def show_settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_settings command - shows read-only dashboard"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
            language = await self.data_manager.get_user_language(user_id)
            
            keywords = await self.data_manager.get_user_keywords(user_id)
            ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_id)
            
            # Use helper to format message
            msg = format_settings_message(keywords, ignore_keywords, language)
            keyboard = create_settings_keyboard(bool(keywords), language)
            
            await update.message.reply_text(msg, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error in show settings command: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'show_settings_command',
                'user_id': user_id
            }, source='commands')
    
    # Legacy commands (keep for backward compatibility)
    async def set_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /keywords command - legacy support"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
            language = await self.data_manager.get_user_language(user_id)
            
            if not context.args:
                # Show help with pre-fill button
                help_text = get_text("keywords_help_text", language)
                keyboard = create_keywords_help_keyboard(language)
                await update.message.reply_text(help_text, reply_markup=keyboard)
                return
            
            keywords_text = ' '.join(context.args)
            
            # Use existing parsing logic
            from matching.keywords import KeywordMatcher
            matcher = KeywordMatcher()
            keywords = matcher.parse_keywords(keywords_text)
            
            if not keywords:
                await update.message.reply_text(get_text("keywords_no_valid", language))
                return
            
            # Convert to lowercase for storage
            keywords = [k.lower() for k in keywords]
            
            # Set keywords (this will validate limits)
            await self.data_manager.set_user_keywords(user_id, keywords)
            
            # Enhanced success message
            keywords_str = ', '.join(keywords)
            success_message = get_text("keywords_success", language, keywords=keywords_str)
            
            await update.message.reply_text(success_message)
            
            # Emit keywords updated event
            await self.event_bus.emit(EventType.USER_KEYWORDS_UPDATED, {
                'user_id': user_id,
                'keywords': keywords,
                'keyword_count': len(keywords),
                'action': 'set_keywords'
            }, source='commands')
            
            logger.info(f"User {user_id} set {len(keywords)} keywords")
            
        except ValueError as e:
            # Handle validation errors (too many keywords, etc.)
            await update.message.reply_text(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"Error setting keywords: {e}")
            await update.message.reply_text(get_text("error_occurred", language))
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'set_keywords_command',
                'user_id': user_id
            }, source='commands')
    
    async def set_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ignore_keywords command - legacy support"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
            language = await self.data_manager.get_user_language(user_id)
            
            if not context.args:
                # Show help with pre-fill button
                help_text = get_text("ignore_help_text", language)
                keyboard = create_ignore_keywords_help_keyboard(language)
                await update.message.reply_text(help_text, reply_markup=keyboard)
                return
            
            keywords_text = ' '.join(context.args)
            
            # Use existing parsing logic
            from matching.keywords import KeywordMatcher
            matcher = KeywordMatcher()
            keywords = matcher.parse_keywords(keywords_text)
            
            if not keywords:
                await update.message.reply_text(get_text("ignore_keywords_no_valid", language))
                return
            
            # Convert to lowercase for storage
            keywords = [k.lower() for k in keywords]
            
            # Set ignore keywords (this will validate limits)
            await self.data_manager.set_user_ignore_keywords(user_id, keywords)
            
            # Enhanced success message
            keywords_str = ', '.join(keywords)
            success_message = get_text("ignore_keywords_success", language, keywords=keywords_str)
            
            await update.message.reply_text(success_message)
            
            # Emit keywords updated event
            await self.event_bus.emit(EventType.USER_KEYWORDS_UPDATED, {
                'user_id': user_id,
                'ignore_keywords': keywords,
                'ignore_keyword_count': len(keywords),
                'action': 'set_ignore_keywords'
            }, source='commands')
            
            logger.info(f"User {user_id} set {len(keywords)} ignore keywords")
            
        except ValueError as e:
            # Handle validation errors
            await update.message.reply_text(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"Error setting ignore keywords: {e}")
            await update.message.reply_text(get_text("error_occurred", language))
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'set_ignore_keywords_command',
                'user_id': user_id
            }, source='commands')
    
    async def purge_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /purge_ignore command - legacy support"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
            language = await self.data_manager.get_user_language(user_id)
            
            if await self.data_manager.purge_user_ignore_keywords(user_id):
                success_message = get_text("ignore_cleared_success", language)
                await update.message.reply_text(success_message)
                
                # Emit keywords updated event
                await self.event_bus.emit(EventType.USER_KEYWORDS_UPDATED, {
                    'user_id': user_id,
                    'ignore_keywords': [],
                    'action': 'purge_ignore_keywords'
                }, source='commands')
                
                logger.info(f"User {user_id} purged ignore keywords")
            else:
                await update.message.reply_text(get_text("ignore_cleared_none", language))
                
        except Exception as e:
            logger.error(f"Error purging ignore keywords: {e}")
            await update.message.reply_text(get_text("error_occurred", language))
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'purge_ignore_keywords_command',
                'user_id': user_id
            }, source='commands')
    
    # Admin commands and authentication handlers (keep in English)
    async def handle_auth_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle authentication messages - ADMIN ONLY - Graceful degradation"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update):
            return  # Ignore non-admin messages
        
        # Graceful degradation - check if user monitor is available
        user_monitor = context.bot_data.get('user_monitor', None)
        if not user_monitor:
            return  # No user monitor available, silently skip
        
        try:
            if user_monitor.is_waiting_for_auth():
                user_id = update.effective_user.id
                message_text = update.message.text
                handled = await user_monitor.handle_auth_message(user_id, message_text)
                
                if handled:
                    # Delete the auth message for security
                    try:
                        await update.message.delete()
                    except Exception:
                        pass  # Ignore deletion errors
                        
        except Exception as e:
            logger.error(f"Error handling auth message: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'handle_auth_message'
            }, source='commands')
    
    async def handle_bot_mention_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages that start with @bot_name from inline queries"""
        if not is_private_chat(update) or not update.message:
            return
        
        message_text = update.message.text
        if not message_text:
            return
        
        try:
            # Check if message starts with @bot_name and extract the command
            bot_username = context.bot.username
            if message_text.startswith(f"@{bot_username}"):
                # Remove @bot_name and any extra spaces
                clean_text = message_text.replace(f"@{bot_username}", "").strip()
                
                # Check if it's a command we handle
                if clean_text.startswith("/keywords"):
                    # Extract arguments
                    args_text = clean_text.replace("/keywords", "").strip()
                    if args_text:
                        context.args = args_text.split()
                        await self.set_keywords_command(update, context)
                    else:
                        context.args = []
                        await self.set_keywords_command(update, context)
                        
                elif clean_text.startswith("/ignore_keywords"):
                    # Extract arguments  
                    args_text = clean_text.replace("/ignore_keywords", "").strip()
                    if args_text:
                        context.args = args_text.split()
                        await self.set_ignore_keywords_command(update, context)
                    else:
                        context.args = []
                        await self.set_ignore_keywords_command(update, context)
                        
        except Exception as e:
            logger.error(f"Error handling bot mention message: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'handle_bot_mention_message'
            }, source='commands')
    
    # Admin commands - ALL IN ENGLISH
    async def auth_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_status command - ADMIN ONLY - Graceful degradation"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update):
            user_id = update.effective_user.id
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("unknown_command", language))
            return
        
        try:
            # Graceful degradation - check if user monitor is available
            user_monitor = context.bot_data.get('user_monitor', None)
            if not user_monitor:
                await update.message.reply_text("❌ User account monitoring is not enabled or unavailable.")
                return
            
            status = user_monitor.get_auth_status()
            
            if status == "disabled":
                await update.message.reply_text("ℹ️ User account monitoring is disabled (no credentials configured).")
            elif status == "not_initialized":
                await update.message.reply_text("❌ User account monitoring failed to initialize.")
            elif status == "waiting_for_code":
                await update.message.reply_text("📱 Waiting for SMS verification code\n\nPlease send the code you received.")
            elif status == "waiting_for_2fa":
                await update.message.reply_text("🔐 Waiting for 2FA password\n\nPlease send your two-factor authentication password.")
            elif status == "authenticated":
                await update.message.reply_text("✅ User account authenticated!\n\nMonitoring is active and working.")
            else:
                await update.message.reply_text("❓ Unknown status. Use /auth_restart to restart authentication.")
                
        except Exception as e:
            logger.error(f"Error in auth status command: {e}")
            await update.message.reply_text("❌ Error checking authentication status.")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'auth_status_command'
            }, source='commands')

    async def auth_restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_restart command - ADMIN ONLY - Graceful degradation"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update):
            user_id = update.effective_user.id
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("unknown_command", language))
            return
        
        try:
            chat_id = update.effective_chat.id
            
            # Graceful degradation - check if user monitor is available
            user_monitor = context.bot_data.get('user_monitor', None)
            if not user_monitor:
                await update.message.reply_text("❌ User account monitoring is not enabled or unavailable.")
                return
            
            success = await user_monitor.restart_auth(chat_id)
            if success:
                await update.message.reply_text("🔄 Authentication restarted\n\nCheck your phone for the verification code.")
            else:
                await update.message.reply_text("❌ Failed to restart authentication.")
                
        except Exception as e:
            logger.error(f"Error restarting authentication: {e}")
            await update.message.reply_text(f"❌ Error restarting authentication: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'auth_restart_command'
            }, source='commands')
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command - Enhanced with improved channel management"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update):
            user_id = update.effective_user.id
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("unknown_command", language))
            return
        
        try:
            if not context.args:
                await update.message.reply_text(
                    "📋 **Enhanced Admin Commands**\n\n"
                    "**System:**\n"
                    "• `/admin health` - System health check\n"
                    "• `/admin stats` - Database statistics\n"
                    "• `/admin mode` - Current bot mode\n\n"
                    "**Enhanced Channel Management:**\n"
                    "• `/admin channels` - List all channels (enhanced display)\n"
                    "• `/admin add_bot_channel <channel>` - Add bot channel\n"
                    "• `/admin add_user_channel <channel>` - Add user channel\n"
                    "• `/admin remove_channel <channel>` - Remove channel (flexible)\n"
                    "• `/admin update_username <chat_id> <username>` - Update username\n\n"
                    "**Supported Channel Formats:**\n"
                    "• `@channelname`\n"
                    "• `t.me/channelname`\n"
                    "• `https://t.me/channelname`\n"
                    "• `-1001234567890` (chat ID)\n\n"
                    "**Features:**\n"
                    "• Flexible channel removal (by username/URL/ID)\n"
                    "• Enhanced channel listing with removal commands\n"
                    "• Admin status validation for bot channels\n"
                    "• Graceful degradation when user monitor unavailable",
                    parse_mode='Markdown'
                )
                return
            
            subcommand = context.args[0].lower()
            
            # Emit admin command executed event
            await self.event_bus.emit(EventType.ADMIN_COMMAND_EXECUTED, {
                'user_id': update.effective_user.id,
                'command': subcommand,
                'args': context.args[1:] if len(context.args) > 1 else []
            }, source='commands')
            
            # Route to appropriate handler
            if subcommand == "health":
                await self.admin_health_command(update, context)
            elif subcommand == "stats":
                await self.admin_stats_command(update, context)
            elif subcommand == "mode":
                await self.admin_mode_command(update, context)
            elif subcommand == "channels":
                await self.admin_list_channels_enhanced(update, context)
            elif subcommand == "add_bot_channel":
                await self.admin_add_bot_channel_enhanced(update, context)
            elif subcommand == "add_user_channel":
                await self.admin_add_user_channel_enhanced(update, context)
            elif subcommand == "remove_channel":
                await self.admin_remove_channel_enhanced(update, context)
            elif subcommand == "update_username":
                await self.admin_update_username(update, context)
            else:
                await update.message.reply_text(f"❓ Unknown admin command: {subcommand}")
                
        except Exception as e:
            logger.error(f"Error in admin command: {e}")
            await update.message.reply_text("❌ Error processing admin command")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'admin_command',
                'subcommand': context.args[0] if context.args else 'none'
            }, source='commands')
    
    # Enhanced admin command implementations
    async def admin_health_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin health check with graceful degradation"""
        try:
            health_status = []
            
            # Test database
            try:
                stats = await self.data_manager.get_system_stats()
                health_status.append("✅ Database: Connected")
                health_status.append(f"   Users: {stats.get('total_users', 0)}")
            except Exception as e:
                health_status.append(f"❌ Database: Error - {str(e)[:50]}")
            
            # Check user monitor with graceful degradation
            user_monitor = context.bot_data.get('user_monitor', None)
            if user_monitor:
                try:
                    auth_status = user_monitor.get_auth_status()
                    if auth_status == "authenticated":
                        health_status.append("✅ User Monitor: Authenticated")
                    else:
                        health_status.append(f"⚠️ User Monitor: {auth_status}")
                except Exception as e:
                    health_status.append(f"❌ User Monitor: Error - {str(e)[:50]}")
            else:
                health_status.append("ℹ️ User Monitor: Not configured/available")
            
            # Check bot mode
            bot_mode = getattr(context.bot_data.get('bot_instance'), 'mode', 'unknown')
            health_status.append(f"🎯 Bot Mode: {bot_mode}")
            
            message = "🏥 **System Health Check**\n\n"
            message += "\n".join(health_status)
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            await update.message.reply_text(f"❌ Health check failed: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'admin_health_command'
            }, source='commands')
    
    async def admin_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced admin stats"""
        try:
            stats = await self.data_manager.get_system_stats()
            
            message = (
                f"📊 **System Statistics**\n\n"
                f"👥 **Users:** {stats.get('total_users', 0)}\n"
                f"🔑 **Keywords:** {stats.get('total_keywords', 0)}\n"
                f"📤 **Forwards (24h):** {stats.get('forwards_24h', 0)}\n\n"
            )
            
            # Channel info
            channels = stats.get('channels', {})
            bot_channels = channels.get('bot', 0)
            user_channels = channels.get('user', 0)
            
            message += (
                f"📺 **Channels:**\n"
                f"• Bot channels: {bot_channels}\n"
                f"• User channels: {user_channels}\n\n"
            )
            
            # Language distribution
            languages = stats.get('languages', {})
            if languages:
                message += "🌐 **Languages:**\n"
                for lang, count in languages.items():
                    message += f"• {lang}: {count}\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            await update.message.reply_text(f"❌ Error getting statistics: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'admin_stats_command'
            }, source='commands')
    
    async def admin_mode_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current bot mode"""
    async def admin_mode_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current bot mode"""
        try:
            bot_instance = context.bot_data.get('bot_instance')
            mode = getattr(bot_instance, 'mode', 'unknown') if bot_instance else 'unknown'
            
            mode_descriptions = {
                'full': '🎯 **FULL MODE**\nBot + User Monitor active\nComplete functionality',
                'bot-only': '🤖 **BOT-ONLY MODE**\nOnly bot channels monitored\nUser monitor disabled/unavailable',
                'degraded': '⚠️ **DEGRADED MODE**\nPartial functionality\nSome components failed',
                'initializing': '🔄 **INITIALIZING**\nSystem starting up',
                'unknown': '❓ **UNKNOWN MODE**\nCannot determine current state'
            }
            
            description = mode_descriptions.get(mode, f"Current mode: {mode}")
            
            message = f"🔍 **Bot Operating Mode**\n\n{description}"
            
            # Add recommendations based on mode
            if mode == 'bot-only':
                message += "\n\n💡 **To enable full mode:**\nConfigure user monitor credentials and restart"
            elif mode == 'degraded':
                message += "\n\n🔧 **To restore full functionality:**\nCheck logs and restart components"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error getting mode: {e}")
            await update.message.reply_text(f"❌ Error getting mode: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'admin_mode_command'
            }, source='commands')
    
    async def admin_list_channels_enhanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin channels command with clearer display"""
        try:
            # Get all channels with display info
            channel_info = await self.data_manager.get_all_channels_with_usernames()
            
            if not channel_info:
                await update.message.reply_text("📺 No channels configured")
                return
            
            bot_channels = []
            user_channels = []
            
            for chat_id, info in channel_info.items():
                if info['type'] == 'bot':
                    bot_channels.append((chat_id, info))
                else:
                    user_channels.append((chat_id, info))
            
            message = "📺 **Channel Status** (Enhanced)\n\n"
            
            # Bot channels section
            message += f"🤖 **Bot Channels** ({len(bot_channels)}):\n"
            message += f"*(Channels where bot is admin)*\n\n"
            if bot_channels:
                for i, (chat_id, info) in enumerate(bot_channels, 1):
                    title = info['username'] if info['username'] else f"Channel {chat_id}"
                    
                    message += f"**{i}. {title}**\n"
                    message += f"   • Chat ID: `{chat_id}`\n"
                    if info['username']:
                        message += f"   • Remove: `/admin remove_channel {info['username']}`\n"
                    else:
                        message += f"   • Remove: `/admin remove_channel {chat_id}`\n"
                    message += "\n"
            else:
                message += "   *No bot channels configured*\n\n"
            
            # User channels section  
            message += f"👤 **User Channels** ({len(user_channels)}):\n"
            message += f"*(Channels monitored via user account)*\n\n"
            if user_channels:
                for i, (chat_id, info) in enumerate(user_channels, 1):
                    title = info['username'] if info['username'] else f"Channel {chat_id}"
                    
                    message += f"**{i}. {title}**\n"
                    message += f"   • Chat ID: `{chat_id}`\n"
                    if info['username']:
                        message += f"   • Remove: `/admin remove_channel {info['username']}`\n"
                    else:
                        message += f"   • Remove: `/admin remove_channel {chat_id}`\n"
                    message += "\n"
            else:
                message += "   *No user channels configured*\n\n"
            
            # Commands help
            message += "💡 **Quick Commands:**\n"
            message += "• **Add bot channel:** `/admin add_bot_channel @channel`\n"
            message += "• **Add user channel:** `/admin add_user_channel @channel`\n"
            message += "• **Remove any channel:** `/admin remove_channel @channel`\n"
            message += "• **Remove by ID:** `/admin remove_channel -1001234567890`"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error listing channels: {e}")
            await update.message.reply_text(f"❌ Error retrieving channels: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'admin_list_channels_enhanced'
            }, source='commands')

    async def admin_add_bot_channel_enhanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin add_bot_channel command with validation"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Usage: `/admin add_bot_channel <channel>`\n\n"
                "Examples:\n"
                "• `/admin add_bot_channel @techjobs`\n"
                "• `/admin add_bot_channel https://t.me/remotejobs`\n"
                "• `/admin add_bot_channel -1001234567890`",
                parse_mode='Markdown'
            )
            return
        
        channel_input = context.args[1]
        
        try:
            await update.message.reply_text(f"🔍 Adding bot channel: `{channel_input}`...", parse_mode='Markdown')
            
            # Try to get chat info using bot API
            chat_id = None
            username = None
            display_title = None
            
            # Parse input format
            if channel_input.startswith('@'):
                chat_id = channel_input
                display_title = channel_input
            elif 't.me/' in channel_input:
                # Extract username from URL
                url_pattern = r'(?:https?://)?t\.me/([^/\s]+)'
                match = re.search(url_pattern, channel_input)
                if match:
                    username = f"@{match.group(1)}"
                    chat_id = username
                    display_title = username
                else:
                    await update.message.reply_text("❌ Cannot parse channel URL")
                    return
            elif channel_input.lstrip('-').isdigit():
                chat_id = int(channel_input)
                display_title = f"Channel {chat_id}"
            else:
                await update.message.reply_text("❌ Invalid channel format")
                return
            
            # Get chat info from Telegram
            try:
                chat = await context.bot.get_chat(chat_id)
                actual_chat_id = chat.id
                username = f"@{chat.username}" if chat.username else None
                
                # Better display name logic
                if chat.title:
                    display_title = chat.title
                elif username:
                    display_title = username
                else:
                    display_title = f"Channel {actual_chat_id}"
                
                # Check if bot is admin
                try:
                    bot_member = await context.bot.get_chat_member(actual_chat_id, context.bot.id)
                    is_admin = bot_member.status in ['administrator', 'creator']
                    
                    if not is_admin:
                        await update.message.reply_text(
                            f"⚠️ **Warning:** Bot is not admin in **{display_title}**\n"
                            f"Add the bot as admin first, then try again.",
                            parse_mode='Markdown'
                        )
                        return
                except Exception:
                    await update.message.reply_text(
                        f"⚠️ **Warning:** Cannot check admin status in **{display_title}**",
                        parse_mode='Markdown'
                    )
                
            except Exception as e:
                await update.message.reply_text(f"❌ Cannot access channel: {str(e)}")
                return
            
            # Add to database
            success = await self.data_manager.add_channel_simple(actual_chat_id, username, 'bot')
            
            if success:
                await update.message.reply_text(
                    f"✅ **Bot channel added successfully!**\n\n"
                    f"📋 **Title:** {display_title}\n"
                    f"🔗 **Username:** {username or 'None'}\n"
                    f"🆔 **Chat ID:** `{actual_chat_id}`",
                    parse_mode='Markdown'
                )
                
                # Emit channel added event
                await self.event_bus.emit(EventType.CHANNEL_ADDED, {
                    'chat_id': actual_chat_id,
                    'username': username,
                    'type': 'bot',
                    'admin_user_id': update.effective_user.id,
                    'display_title': display_title
                }, source='commands')
                
                logger.info(f"Admin {update.effective_user.id} added bot channel: {display_title}")
                
            else:
                await update.message.reply_text(f"❌ Channel already exists in database")
                
        except Exception as e:
            logger.error(f"Error adding bot channel: {e}")
            await update.message.reply_text(f"❌ Error adding channel: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'admin_add_bot_channel_enhanced',
                'channel_input': channel_input
            }, source='commands')

    async def admin_add_user_channel_enhanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin add_user_channel command with graceful degradation"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Usage: `/admin add_user_channel <channel>`\n\n"
                "Note: Requires user monitor to be configured and authenticated.",
                parse_mode='Markdown'
            )
            return
        
        # Graceful degradation - check if user monitor is available
        user_monitor = context.bot_data.get('user_monitor', None)
        if not user_monitor:
            await update.message.reply_text("❌ User monitor not available or not configured")
            return
        
        if user_monitor.get_auth_status() != "authenticated":
            await update.message.reply_text("❌ User monitor not authenticated. Use `/auth_status` to check status.")
            return
        
        channel_input = context.args[1]
        
        try:
            success, message = await user_monitor.add_channel(channel_input)
            
            if success:
                await update.message.reply_text(f"✅ {message}")
                
                # Emit channel added event
                await self.event_bus.emit(EventType.CHANNEL_ADDED, {
                    'channel_input': channel_input,
                    'type': 'user',
                    'admin_user_id': update.effective_user.id,
                    'via_user_monitor': True
                }, source='commands')
                
                logger.info(f"Admin {update.effective_user.id} added user channel: {channel_input}")
            else:
                await update.message.reply_text(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"Error adding user channel: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'admin_add_user_channel_enhanced',
                'channel_input': channel_input
            }, source='commands')

    async def admin_remove_channel_enhanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin remove_channel command - accepts usernames/URLs/IDs"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Usage: `/admin remove_channel <channel>`\n\n"
                "**Supported formats:**\n"
                "• `/admin remove_channel @channelname`\n"
                "• `/admin remove_channel https://t.me/channelname`\n"
                "• `/admin remove_channel -1001234567890` (chat ID)\n\n"
                "Use `/admin channels` to see all channels with their identifiers.",
                parse_mode='Markdown'
            )
            return
        
        channel_input = context.args[1]
        
        try:
            await update.message.reply_text(f"🔍 Looking for channel: `{channel_input}`...", parse_mode='Markdown')
            
            target_chat_id = None
            target_channel_info = None
            search_method = "unknown"
            
            # Step 1: Try to get current info from Telegram first
            try:
                telegram_identifier = None
                
                if channel_input.lstrip('-').isdigit():
                    telegram_identifier = int(channel_input)
                elif channel_input.startswith('@'):
                    telegram_identifier = channel_input
                elif 't.me/' in channel_input:
                    url_pattern = r'(?:https?://)?t\.me/([^/\s]+)'
                    match = re.search(url_pattern, channel_input)
                    if match:
                        telegram_identifier = f"@{match.group(1)}"
                
                if telegram_identifier:
                    chat = await context.bot.get_chat(telegram_identifier)
                    target_chat_id = chat.id
                    search_method = "telegram_api"
                    logger.info(f"Found channel via Telegram API: {chat.title or chat.username} (ID: {target_chat_id})")
                    
                    # Find this chat_id in our database
                    channel_info = await self.data_manager.get_all_channels_with_usernames()
                    target_channel_info = channel_info.get(target_chat_id)
                    
                    if not target_channel_info:
                        await update.message.reply_text(
                            f"❌ **Channel exists on Telegram but not in bot database**\n\n"
                            f"📋 **Channel:** {chat.title or chat.username or target_chat_id}\n"
                            f"🆔 **Chat ID:** `{target_chat_id}`\n\n"
                            f"This channel is not being monitored by the bot.",
                            parse_mode='Markdown'
                        )
                        return
                        
            except Exception:
                # Telegram lookup failed, continue to database search
                pass
            
            # Step 2: If Telegram lookup failed, search database
            if not target_chat_id or not target_channel_info:
                channel_info = await self.data_manager.get_all_channels_with_usernames()
                search_method = "database_search"
                
                if channel_input.lstrip('-').isdigit():
                    target_chat_id = int(channel_input)
                    target_channel_info = channel_info.get(target_chat_id)
                elif channel_input.startswith('@'):
                    for chat_id, info in channel_info.items():
                        if info['username'] and info['username'].lower() == channel_input.lower():
                            target_chat_id = chat_id
                            target_channel_info = info
                            break
                elif 't.me/' in channel_input:
                    url_pattern = r'(?:https?://)?t\.me/([^/\s]+)'
                    match = re.search(url_pattern, channel_input)
                    if match:
                        username_from_url = f"@{match.group(1)}"
                        for chat_id, info in channel_info.items():
                            if info['username'] and info['username'].lower() == username_from_url.lower():
                                target_chat_id = chat_id
                                target_channel_info = info
                                break
            
            # Step 3: If still not found
            if not target_chat_id or not target_channel_info:
                await update.message.reply_text(
                    f"❌ **Channel not found:** `{channel_input}`\n\n"
                    f"Use `/admin channels` to see all monitored channels.",
                    parse_mode='Markdown'
                )
                return
            
            # Step 4: Remove the channel
            channel_type = target_channel_info['type']
            success = await self.data_manager.remove_channel_simple(target_chat_id, channel_type)
            
            if success:
                success_msg = f"✅ **Channel removed successfully!**\n\n"
                success_msg += f"📋 **Removed:** {target_channel_info['display_name']}\n"
                success_msg += f"🆔 **Chat ID:** `{target_chat_id}`\n"
                success_msg += f"🔗 **Username:** {target_channel_info['username'] or 'None'}\n"
                success_msg += f"📊 **Type:** {channel_type}\n"
                success_msg += f"\n🔍 **Found via:** {search_method.replace('_', ' ').title()}"
                
                await update.message.reply_text(success_msg, parse_mode='Markdown')
                
                # Emit channel removed event
                await self.event_bus.emit(EventType.CHANNEL_REMOVED, {
                    'chat_id': target_chat_id,
                    'username': target_channel_info['username'],
                    'type': channel_type,
                    'admin_user_id': update.effective_user.id,
                    'search_method': search_method
                }, source='commands')
                
                logger.info(f"Admin {update.effective_user.id} removed {channel_type} channel: {target_channel_info['display_name']}")
                
            else:
                await update.message.reply_text("❌ Failed to remove channel from database")
                
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            await update.message.reply_text(f"❌ Error removing channel: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'admin_remove_channel_enhanced',
                'channel_input': channel_input
            }, source='commands')

    async def admin_update_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Update channel username"""
        if len(context.args) < 3:
            await update.message.reply_text(
                "❌ Usage: `/admin update_username <chat_id> <@username>`\n\n"
                "Example: `/admin update_username -1001234567890 @newtechjobs`",
                parse_mode='Markdown'
            )
            return
        
        try:
            chat_id = int(context.args[1])
            new_username = context.args[2]
            
            # Ensure username starts with @
            if not new_username.startswith('@'):
                new_username = f"@{new_username}"
            
            success = await self.data_manager.update_channel_username(chat_id, new_username)
            
            if success:
                await update.message.reply_text(
                    f"✅ **Username updated successfully!**\n\n"
                    f"🆔 **Chat ID:** `{chat_id}`\n"
                    f"🔗 **New Username:** {new_username}",
                    parse_mode='Markdown'
                )
                
                logger.info(f"Admin {update.effective_user.id} updated username for {chat_id} to {new_username}")
            else:
                await update.message.reply_text(f"❌ Channel not found: `{chat_id}`", parse_mode='Markdown')
                
        except ValueError:
            await update.message.reply_text("❌ Invalid chat_id format. Must be a number.")
        except Exception as e:
            logger.error(f"Error updating username: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'admin_update_username',
                'chat_id': context.args[1] if len(context.args) > 1 else None
            }, source='commands')


# THIS IS THE END OF FILE