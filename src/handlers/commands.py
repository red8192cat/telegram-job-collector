"""
Command Handlers - Enhanced with improved admin channel management
All user-facing messages are now translated based on user's language preference
UPDATED: Enhanced admin channel management with flexible input formats
"""

import logging
import os
import re
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

from storage.sqlite_manager import SQLiteManager
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
    def __init__(self, data_manager: SQLiteManager):
        self.data_manager = data_manager
        # Cache admin ID for better performance
        self._admin_id = None
        admin_id_str = os.getenv('AUTHORIZED_ADMIN_ID')
        if admin_id_str and admin_id_str.isdigit():
            self._admin_id = int(admin_id_str)
            logger.info(f"Admin ID configured: {self._admin_id}")
    
    def _is_authorized_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check if user is authorized admin"""
        if not self._admin_id:
            return False
        
        user_id = update.effective_user.id
        return user_id == self._admin_id
    
    def register(self, app):
        """Register command handlers"""
        # Essential user commands - UPDATED
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("manage_keywords", self.manage_keywords_command))
        app.add_handler(CommandHandler("my_settings", self.show_settings_command))
        
        # Legacy commands (hidden from menu but still work)
        app.add_handler(CommandHandler("keywords", self.set_keywords_command))
        app.add_handler(CommandHandler("ignore_keywords", self.set_ignore_keywords_command))
        app.add_handler(CommandHandler("purge_ignore", self.purge_ignore_keywords_command))
        
        # Admin commands (hidden from public menu, keep in English)
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
        
        logger.info("Enhanced command handlers with improved channel management registered")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with language selection for new users"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        logger.info(f"Start command from user {user_id}")
        
        # Get user's current language
        user_language = await self.data_manager.get_user_language(user_id)
        
        # Check if user is completely new (no language set or default 'en' for new user)
        user_exists = await self._user_has_interacted_before(user_id)
        
        if not user_exists:
            # New user - show language selection first
            welcome_msg = get_text("language_selection_message", "en")  # Show in both languages
            keyboard = create_language_selection_keyboard()
            
            await update.message.reply_text(welcome_msg, reply_markup=keyboard)
        else:
            # Existing user - show main menu in their language
            welcome_msg = get_text("welcome_message", user_language)
            menu_markup = create_main_menu(user_language)
            await update.message.reply_text(welcome_msg, reply_markup=menu_markup)
    
    async def _user_has_interacted_before(self, user_id: int) -> bool:
        """Check if user has interacted with bot before (has keywords or custom language)"""
        try:
            # Check if user has keywords set
            keywords = await self.data_manager.get_user_keywords(user_id)
            if keywords:
                return True
            
            # Check if user has custom language (not default 'en')
            language = await self.data_manager.get_user_language(user_id)
            # If language is set to something other than 'en', user has interacted
            return language != 'en'
            
        except Exception:
            return False
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        language = await self.data_manager.get_user_language(user_id)
        
        await update.message.reply_text(get_help_text(language))
    
    async def manage_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /manage_keywords command - NEW unified keyword management"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
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
    
    async def show_settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_settings command - shows read-only dashboard"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        language = await self.data_manager.get_user_language(user_id)
        
        keywords = await self.data_manager.get_user_keywords(user_id)
        ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_id)
        
        # Use helper to format message
        msg = format_settings_message(keywords, ignore_keywords, language)
        keyboard = create_settings_keyboard(bool(keywords), language)
        
        await update.message.reply_text(msg, reply_markup=keyboard)
    
    # Legacy commands (keep for backward compatibility but hide from menu)
    async def set_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /keywords command - legacy support"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
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
        
        await self.data_manager.set_user_keywords(user_id, keywords)
        
        # Enhanced success message
        keywords_str = ', '.join(keywords)
        success_message = get_text("keywords_success", language, keywords=keywords_str)
        
        await update.message.reply_text(success_message)
    
    async def set_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ignore_keywords command - legacy support"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
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
        
        await self.data_manager.set_user_ignore_keywords(user_id, keywords)
        
        # Enhanced success message
        keywords_str = ', '.join(keywords)
        success_message = get_text("ignore_keywords_success", language, keywords=keywords_str)
        
        await update.message.reply_text(success_message)
    
    async def purge_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /purge_ignore command - legacy support"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        language = await self.data_manager.get_user_language(user_id)
        
        if await self.data_manager.purge_user_ignore_keywords(user_id):
            success_message = get_text("ignore_cleared_success", language)
            await update.message.reply_text(success_message)
        else:
            await update.message.reply_text(get_text("ignore_cleared_none", language))
    
    # Admin commands and authentication handlers (keep in English)
    async def handle_auth_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle authentication messages - ADMIN ONLY - Keep in English"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update, context):
            return  # Ignore non-admin messages
        
        user_monitor = context.bot_data.get('user_monitor', None)
        if not user_monitor:
            return  # No user monitor available
        
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
    
    async def handle_bot_mention_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages that start with @bot_name from inline queries"""
        if not is_private_chat(update) or not update.message:
            return
        
        message_text = update.message.text
        if not message_text:
            return
        
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
                    # Create a fake context with args
                    context.args = args_text.split()
                    await self.set_keywords_command(update, context)
                else:
                    # No args, show help
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
    
    # Admin commands - ALL STAY IN ENGLISH
    async def auth_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_status command - ADMIN ONLY - Keep in English"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update, context):
            # Use user's language for unknown command message
            user_id = update.effective_user.id
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("unknown_command", language))
            return
        
        user_monitor = context.bot_data.get('user_monitor', None)
        if not user_monitor:
            await update.message.reply_text("❌ User account monitoring is not enabled.")
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

    async def auth_restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_restart command - ADMIN ONLY - Keep in English"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update, context):
            user_id = update.effective_user.id
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("unknown_command", language))
            return
        
        chat_id = update.effective_chat.id
        
        user_monitor = context.bot_data.get('user_monitor', None)
        if not user_monitor:
            await update.message.reply_text("❌ User account monitoring is not enabled.")
            return
        
        try:
            success = await user_monitor.restart_auth(chat_id)
            if success:
                await update.message.reply_text("🔄 Authentication restarted\n\nCheck your phone for the verification code.")
            else:
                await update.message.reply_text("❌ Failed to restart authentication.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error restarting authentication: {str(e)}")
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command - ENHANCED with improved channel management"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update, context):
            user_id = update.effective_user.id
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("unknown_command", language))
            return
        
        if not context.args:
            await update.message.reply_text(
                "📋 **Enhanced Admin Commands**\n\n"
                "**System:**\n"
                "• `/admin health` - System health check\n"
                "• `/admin stats` - Database statistics\n"
                "• `/admin errors` - Show recent errors\n\n"
                "**Enhanced Channel Management:**\n"
                "• `/admin channels` - List all channels (improved display)\n"
                "• `/admin add_bot_channel <channel>` - Add bot channel\n"
                "• `/admin add_user_channel <channel>` - Add user channel\n"
                "• `/admin remove_channel <channel>` - Remove any channel (flexible)\n"
                "• `/admin update_username <chat_id> <username>` - Update username\n\n"
                "**Data Management:**\n"
                "• `/admin export` - Export enhanced config\n"
                "• `/admin import` - Import from config files\n"
                "• `/admin backup_manual` - Create manual backup\n"
                "• `/admin list_backups` - List all backups\n\n"
                "**Supported Channel Formats:**\n"
                "• `@channelname`\n"
                "• `t.me/channelname`\n"
                "• `https://t.me/channelname`\n"
                "• `-1001234567890` (chat ID)\n\n"
                "**New Features:**\n"
                "• Flexible channel removal (by username/URL/ID)\n"
                "• Better channel listing with removal commands\n"
                "• Admin status validation for bot channels",
                parse_mode='Markdown'
            )
            return
        
        subcommand = context.args[0].lower()
        
        # Enhanced channel management commands
        if subcommand == "channels":
            await self.admin_list_channels_enhanced(update, context)
        elif subcommand == "add_bot_channel":
            await self.admin_add_bot_channel_enhanced(update, context)
        elif subcommand == "add_user_channel":
            await self.admin_add_user_channel_enhanced(update, context)
        elif subcommand == "remove_channel":
            await self.admin_remove_channel_enhanced(update, context)
        elif subcommand == "update_username":
            await self.admin_update_channel_username(update, context)
        elif subcommand == "export":
            await self.admin_export_enhanced_command(update, context)
        elif subcommand == "import":
            await self.admin_import_command(update, context)
        elif subcommand == "health":
            await self.admin_health_command(update, context)
        elif subcommand == "stats":
            await self.admin_stats_command(update, context)
        elif subcommand == "errors":
            await self.admin_errors_command(update, context)
        elif subcommand == "backup_manual":
            await self.admin_backup_manual_command(update, context)
        elif subcommand == "list_backups":
            await self.admin_list_backups_command(update, context)
        else:
            await update.message.reply_text(f"❓ Unknown admin command: {subcommand}")
    
    # Enhanced channel management admin commands - UPDATED WITH IMPROVEMENTS
    
    async def admin_remove_channel_enhanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin remove_channel command - FIXED to accept usernames/URLs"""
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
            await update.message.reply_text(f"🔍 Looking for channel: `{channel_input}`...")
            
            target_chat_id = None
            target_channel_info = None
            search_method = "unknown"
            
            # STEP 1: Try to get current info from Telegram FIRST (for any input format)
            try:
                # Parse the input to a format Telegram API can understand
                telegram_identifier = None
                
                if channel_input.lstrip('-').isdigit():
                    # Direct chat ID - use as is
                    telegram_identifier = int(channel_input)
                elif channel_input.startswith('@'):
                    # Username format - use as is
                    telegram_identifier = channel_input
                elif 't.me/' in channel_input or 'telegram.me/' in channel_input:
                    # URL format - extract username
                    url_pattern = r'(?:https?://)?(?:t\.me|telegram\.me)/([^/\s]+)'
                    match = re.search(url_pattern, channel_input)
                    if match:
                        telegram_identifier = f"@{match.group(1)}"
                
                # Try to get current channel info from Telegram
                if telegram_identifier:
                    chat = await context.bot.get_chat(telegram_identifier)
                    target_chat_id = chat.id  # Use CURRENT chat_id from Telegram
                    search_method = "telegram_api"
                    logger.info(f"Found channel via Telegram API: {chat.title or chat.username} (ID: {target_chat_id})")
                    
                    # Now find this chat_id in our database to get the type
                    channel_info = await self.data_manager.get_all_channels_with_usernames()
                    target_channel_info = channel_info.get(target_chat_id)
                    
                    if not target_channel_info:
                        await update.message.reply_text(
                            f"❌ **Channel exists on Telegram but not in bot database**\n\n"
                            f"📋 **Channel:** {chat.title or chat.username or target_chat_id}\n"
                            f"🆔 **Chat ID:** `{target_chat_id}`\n\n"
                            f"This channel is not being monitored by the bot.\n"
                            f"Use `/admin channels` to see monitored channels.",
                            parse_mode='Markdown'
                        )
                        return
                        
            except Exception as telegram_error:
                logger.info(f"Telegram API lookup failed for {channel_input}: {telegram_error}")
                # Continue to database fallback
                pass
            
            # STEP 2: If Telegram lookup failed, search database for stored info
            if not target_chat_id or not target_channel_info:
                logger.info(f"Falling back to database search for: {channel_input}")
                channel_info = await self.data_manager.get_all_channels_with_usernames()
                search_method = "database_fallback"
                
                if channel_input.lstrip('-').isdigit():
                    # Direct chat ID
                    target_chat_id = int(channel_input)
                    target_channel_info = channel_info.get(target_chat_id)
                    
                elif channel_input.startswith('@'):
                    # Username format - search database
                    for chat_id, info in channel_info.items():
                        if info['username'] and info['username'].lower() == channel_input.lower():
                            target_chat_id = chat_id
                            target_channel_info = info
                            break
                            
                elif 't.me/' in channel_input or 'telegram.me/' in channel_input:
                    # URL format - extract username and search database
                    url_pattern = r'(?:https?://)?(?:t\.me|telegram\.me)/([^/\s]+)'
                    match = re.search(url_pattern, channel_input)
                    if match:
                        username_from_url = f"@{match.group(1)}"
                        for chat_id, info in channel_info.items():
                            if info['username'] and info['username'].lower() == username_from_url.lower():
                                target_chat_id = chat_id
                                target_channel_info = info
                                break
                
                # STEP 3: Last resort - partial display name search
                if not target_chat_id or not target_channel_info:
                    for chat_id, info in channel_info.items():
                        if channel_input.lower() in info['display_name'].lower():
                            target_chat_id = chat_id
                            target_channel_info = info
                            search_method = "display_name_search"
                            break
            
            # STEP 4: Final check - if still nothing found
            if not target_chat_id or not target_channel_info:
                await update.message.reply_text(
                    f"❌ **Channel not found:** `{channel_input}`\n\n"
                    f"**Searched:**\n"
                    f"• Telegram API (current info)\n"
                    f"• Bot database (stored channels)\n"
                    f"• Display name matching\n\n"
                    f"Use `/admin channels` to see all monitored channels.",
                    parse_mode='Markdown'
                )
                return
            
            # STEP 5: Remove the channel
            channel_type = target_channel_info['type']
            success = await self.data_manager.remove_channel_simple(target_chat_id, channel_type)
            
            if success:
                # Export config
                await self._export_enhanced_config()
                
                # Create success message with search method info
                success_msg = f"✅ **Channel removed successfully!**\n\n"
                success_msg += f"📋 **Removed:** {target_channel_info['display_name']}\n"
                success_msg += f"🆔 **Chat ID:** `{target_chat_id}`\n"
                success_msg += f"🔗 **Username:** {target_channel_info['username'] or 'None'}\n"
                success_msg += f"📊 **Type:** {channel_type}\n"
                
                # Add search method info for transparency
                if search_method == "telegram_api":
                    success_msg += f"\n🔍 **Found via:** Telegram API (current info)\n"
                elif search_method == "database_fallback":
                    success_msg += f"\n🔍 **Found via:** Database search (stored info)\n"
                elif search_method == "display_name_search":
                    success_msg += f"\n🔍 **Found via:** Display name matching\n"
                
                if channel_type == 'user':
                    success_msg += f"\n💡 **Note:** User monitor will auto-leave this channel"
                
                await update.message.reply_text(success_msg, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Failed to remove channel from database")
                
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            await update.message.reply_text(f"❌ Error removing channel: {str(e)}")

    async def admin_list_channels_enhanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin channels command with clearer display - FIXED"""
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

    async def admin_add_bot_channel_enhanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin add_bot_channel command - FIXED display"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Usage: `/admin add_bot_channel <channel>`\n\n"
                "Supported formats:\n"
                "• `@channelname`\n"
                "• `t.me/channelname`\n"
                "• `https://t.me/channelname`\n"
                "• `-1001234567890` (chat ID)",
                parse_mode='Markdown'
            )
            return
        
        channel_input = context.args[1]
        
        try:
            await update.message.reply_text(f"🔍 Adding bot channel: `{channel_input}`...")
            
            # Try to get chat info using bot API
            chat_id = None
            username = None
            display_title = None
            
            # Parse input format
            if channel_input.startswith('@'):
                chat_id = channel_input
                display_title = channel_input
            elif 't.me/' in channel_input:
                from utils.config import ConfigManager
                config_manager = ConfigManager()
                parsed_username = config_manager.parse_channel_input(channel_input)
                if parsed_username:
                    chat_id = parsed_username
                    display_title = parsed_username
                else:
                    await update.message.reply_text("❌ Cannot add private channels to bot monitoring")
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
                    display_title = chat.title  # Use actual channel title
                elif username:
                    display_title = username    # Use username as fallback
                else:
                    display_title = f"Channel {actual_chat_id}"  # Use chat ID as last resort
                
                # Check if bot is admin
                try:
                    bot_member = await context.bot.get_chat_member(actual_chat_id, context.bot.id)
                    is_admin = bot_member.status in ['administrator', 'creator']
                    
                    if not is_admin:
                        await update.message.reply_text(
                            f"⚠️ **Warning:** Bot is not admin in **{display_title}**\n"
                            f"The bot needs admin permissions to monitor messages.\n\n"
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
                # Export to config
                await self._export_enhanced_config()
                
                await update.message.reply_text(
                    f"✅ **Bot channel added successfully!**\n\n"
                    f"📋 **Title:** {display_title}\n"
                    f"🔗 **Username:** {username or 'None'}\n"
                    f"🆔 **Chat ID:** `{actual_chat_id}`\n"
                    f"📊 **Type:** Bot Channel (admin required)\n\n"
                    f"**Remove with:** `/admin remove_channel {username or actual_chat_id}`",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"❌ **Channel already exists**\n\n"
                    f"Channel **{display_title}** is already being monitored.\n"
                    f"Use `/admin channels` to see all channels.",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            logger.error(f"Error adding bot channel: {e}")
            await update.message.reply_text(f"❌ Error adding channel: {str(e)}")

    async def admin_add_user_channel_enhanced(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin add_user_channel command"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Usage: `/admin add_user_channel <channel>`\n\n"
                "Same formats as bot channels, but for user account monitoring",
                parse_mode='Markdown'
            )
            return
        
        channel_input = context.args[1]
        
        try:
            await update.message.reply_text(f"🔍 Adding user channel: `{channel_input}`...")
            
            # For user channels, we might not have bot access, so handle more gracefully
            chat_id = None
            username = None
            display_name = channel_input
            
            # Parse and set defaults
            if channel_input.startswith('@'):
                username = channel_input
                display_name = channel_input
                # Use hash for temporary chat_id (will be updated when user monitor validates)
                chat_id = hash(channel_input) % 1000000000
            elif 't.me/' in channel_input:
                from utils.config import ConfigManager
                config_manager = ConfigManager()
                parsed_username = config_manager.parse_channel_input(channel_input)
                username = parsed_username
                display_name = parsed_username or "Private Channel"
                chat_id = hash(channel_input) % 1000000000
            elif channel_input.lstrip('-').isdigit():
                chat_id = int(channel_input)
                display_name = f"Channel {chat_id}"
            else:
                await update.message.reply_text("❌ Invalid channel format")
                return
            
            # Try to get real chat info (might fail for private channels)
            actual_title = None
            try:
                chat = await context.bot.get_chat(chat_id if isinstance(chat_id, int) and chat_id > 1000000000 else username)
                chat_id = chat.id
                username = f"@{chat.username}" if chat.username else None
                actual_title = chat.title  # Get the real channel title
                display_name = actual_title or username or f"Channel {chat_id}"
                logger.info(f"Successfully fetched channel info: title='{actual_title}', username='{username}'")
            except Exception as e:
                # Bot can't access - that's OK for user channels
                logger.info(f"Bot cannot access user channel {channel_input} - will be validated by user monitor: {e}")
                actual_title = None
            
            # Add to database
            success = await self.data_manager.add_channel_simple(chat_id, username, 'user')
            
            if success:
                # Export to config
                await self._export_enhanced_config()
                
                # Better success message with proper title display
                message = f"✅ **User channel added successfully!**\n\n"
                
                if actual_title and actual_title != username:
                    # Show both title and username when they're different
                    message += f"📋 **Title:** {actual_title}\n"
                    message += f"🔗 **Username:** {username or 'None'}\n"
                elif username:
                    # Show only username when no title available
                    message += f"📋 **Channel:** {username}\n"
                else:
                    # Fallback to chat ID display
                    message += f"📋 **Channel:** Channel {chat_id}\n"
                
                message += f"🆔 **Chat ID:** `{chat_id}`\n\n"
                message += f"💡 **Note:** User monitor will validate and auto-join this channel"
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Channel already exists or failed to add")
            
        except Exception as e:
            logger.error(f"Error adding user channel: {e}")
            await update.message.reply_text(f"❌ Error adding channel: {str(e)}")

    async def admin_update_channel_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Update a channel's username when it changes"""
        if len(context.args) < 3:
            await update.message.reply_text(
                "❌ Usage: `/admin update_username <chat_id> <new_username>`\n\n"
                "Example: `/admin update_username -1001234567890 @newtechjobs`",
                parse_mode='Markdown'
            )
            return
        
        try:
            chat_id = int(context.args[1])
            new_username = context.args[2]
            
            if not new_username.startswith('@'):
                new_username = f"@{new_username}"
            
            # Find channel
            channel_info = await self.data_manager.get_all_channels_with_usernames()
            channel = channel_info.get(chat_id)
            
            if not channel:
                await update.message.reply_text(f"❌ Channel with chat_id `{chat_id}` not found")
                return
            
            old_username = channel['username'] or 'None'
            
            # Update username
            success = await self.data_manager.update_channel_username(chat_id, new_username)
            
            if success:
                # Export config
                await self._export_enhanced_config()
                
                await update.message.reply_text(
                    f"✅ **Channel username updated!**\n\n"
                    f"🆔 **Chat ID:** `{chat_id}`\n"
                    f"📋 **Old username:** {old_username}\n"
                    f"🔗 **New username:** {new_username}",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Failed to update username")
                
        except ValueError:
            await update.message.reply_text("❌ Invalid chat_id. Must be a number.")
        except Exception as e:
            logger.error(f"Error updating username: {e}")
            await update.message.reply_text(f"❌ Error updating username: {str(e)}")

    async def _export_enhanced_config(self):
        """Export current database state to config files"""
        try:
            bot_channels, user_channels = await self.data_manager.export_all_channels_for_config()
            
            # Import ConfigManager if available
            try:
                from utils.config import ConfigManager
                config_manager = ConfigManager()
                config_manager.export_channels_config(bot_channels, user_channels)
                logger.info("Exported enhanced config after channel update")
            except Exception as e:
                logger.error(f"Failed to export enhanced config: {e}")
        except Exception as e:
            logger.error(f"Failed to export config: {e}")

    async def admin_export_enhanced_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Export enhanced configuration"""
        try:
            await self._export_enhanced_config()
            
            # Also export users
            users_data = await self.data_manager.export_all_users_for_config()
            try:
                from utils.config import ConfigManager
                config_manager = ConfigManager()
                config_manager.export_users_config(users_data)
            except Exception as e:
                logger.error(f"Failed to export users config: {e}")
            
            await update.message.reply_text(
                "✅ **Enhanced Configuration Exported**\n\n"
                "📁 Updated files:\n"
                "• `data/config/channels.json` (with chat_id + username)\n"
                "• `data/config/users.json`\n\n"
                "💾 Automatic backups created",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in enhanced export: {e}")
            await update.message.reply_text(f"❌ Export failed: {str(e)}")

    # Keep existing admin helper methods
    async def admin_health_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin health check"""
        try:
            health_status = []
            
            # Test database
            try:
                await self.data_manager.get_all_users_with_keywords()
                health_status.append("✅ Database: Connected")
            except Exception as e:
                health_status.append(f"❌ Database: Error - {str(e)[:50]}")
            
            # Check user monitor
            user_monitor = context.bot_data.get('user_monitor', None)
            if user_monitor:
                auth_status = user_monitor.get_auth_status()
                if auth_status == "authenticated":
                    health_status.append("✅ User Monitor: Authenticated")
                else:
                    health_status.append(f"⚠️ User Monitor: {auth_status}")
            else:
                health_status.append("ℹ️ User Monitor: Not configured")
            
            # Check channels
            try:
                channel_info = await self.data_manager.get_all_channels_with_usernames()
                bot_count = sum(1 for info in channel_info.values() if info['type'] == 'bot')
                user_count = sum(1 for info in channel_info.values() if info['type'] == 'user')
                health_status.append(f"✅ Channels: {bot_count} bot, {user_count} user")
            except Exception as e:
                health_status.append(f"❌ Channels: Error - {str(e)[:50]}")
            
            message = "🏥 **System Health Check**\n\n"
            message += "\n".join(health_status)
            
            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Health check failed: {str(e)}")
    
    async def admin_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced admin stats with channel info"""
        try:
            all_users = await self.data_manager.get_all_users_with_keywords()
            total_users = len(all_users)
            total_keywords = sum(len(keywords) for keywords in all_users.values())
            
            # Get channel counts with enhanced info
            channel_info = await self.data_manager.get_all_channels_with_usernames()
            bot_channels = [info for info in channel_info.values() if info['type'] == 'bot']
            user_channels = [info for info in channel_info.values() if info['type'] == 'user']
            
            # Language stats
            try:
                language_stats = await self.data_manager.get_language_statistics()
            except:
                language_stats = {}
            
            message = (
                f"📊 **Enhanced Database Statistics**\n\n"
                f"👥 **Users:**\n"
                f"• Total users: {total_users}\n"
                f"• Total keywords: {total_keywords}\n"
                f"• Avg keywords/user: {total_keywords / total_users if total_users > 0 else 0:.1f}\n"
            )
            
            if language_stats:
                message += f"• Languages: "
                lang_parts = [f"{lang} ({count})" for lang, count in language_stats.items()]
                message += ", ".join(lang_parts) + "\n"
            
            message += (
                f"\n📺 **Channels:**\n"
                f"• Bot channels: {len(bot_channels)}\n"
                f"• User channels: {len(user_channels)}\n"
            )
            
            # Show usernames for channels
            bot_with_usernames = sum(1 for ch in bot_channels if ch['username'])
            user_with_usernames = sum(1 for ch in user_channels if ch['username'])
            
            message += (
                f"• Bot channels with usernames: {bot_with_usernames}/{len(bot_channels)}\n"
                f"• User channels with usernames: {user_with_usernames}/{len(user_channels)}"
            )
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting statistics: {str(e)}")
    
    async def admin_errors_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent errors"""
        try:
            # Try to get error collector if available
            try:
                from utils.error_monitor import get_error_collector
                error_collector = get_error_collector()
                
                if error_collector:
                    recent_errors = error_collector.get_recent_errors(hours=24)
                    stats = error_collector.get_error_stats()
                    
                    if not recent_errors:
                        await update.message.reply_text("✅ No errors in the last 24 hours!")
                        return
                    
                    message = f"⚠️ **Recent Errors (24h)**\n\n"
                    message += f"📊 **Summary:** {stats['total']} total"
                    if stats['critical'] > 0:
                        message += f", {stats['critical']} critical"
                    message += "\n\n"
                    
                    # Show last 5 errors
                    for i, error in enumerate(recent_errors[:5], 1):
                        timestamp = error['timestamp'].strftime("%H:%M:%S")
                        level_icon = "🚨" if error['level'] == 'CRITICAL' else "⚠️"
                        
                        message += f"{i}. {level_icon} {timestamp} - {error['module']}\n"
                        message += f"   {error['message'][:100]}\n"
                    
                    if len(recent_errors) > 5:
                        message += f"\n... and {len(recent_errors) - 5} more errors"
                    
                    await update.message.reply_text(message, parse_mode='Markdown')
                else:
                    await update.message.reply_text("ℹ️ Error monitoring not available")
                    
            except ImportError:
                await update.message.reply_text("ℹ️ Error monitoring module not found")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error retrieving errors: {str(e)}")
    
    async def admin_import_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Import from config files"""
        try:
            from utils.config import ConfigManager
            config_manager = ConfigManager()
            
            # Load and import channels
            config_manager.load_channels_config()
            bot_channels = config_manager.get_channels_to_monitor()
            user_channels = config_manager.get_user_monitored_channels()
            
            # Convert to enhanced format if needed
            bot_channel_dicts = []
            user_channel_dicts = []
            
            for channel in bot_channels:
                if isinstance(channel, dict):
                    bot_channel_dicts.append(channel)
                else:
                    # Legacy format
                    bot_channel_dicts.append({'chat_id': int(channel) if channel.lstrip('-').isdigit() else hash(channel) % 1000000000, 'username': channel if channel.startswith('@') else None})
            
            for channel in user_channels:
                if isinstance(channel, dict):
                    user_channel_dicts.append(channel)
                else:
                    # Legacy format
                    user_channel_dicts.append({'chat_id': int(channel) if channel.lstrip('-').isdigit() else hash(channel) % 1000000000, 'username': channel if channel.startswith('@') else None})
            
            await self.data_manager.import_channels_from_config(bot_channel_dicts, user_channel_dicts)
            
            # Load and import users
            users_data = config_manager.load_users_config()
            if users_data:
                await self.data_manager.import_users_from_config(users_data)
            
            await update.message.reply_text(
                f"✅ **Enhanced Configuration Imported**\n\n"
                f"📊 Imported:\n"
                f"• {len(bot_channel_dicts)} bot channels\n"
                f"• {len(user_channel_dicts)} user channels\n"
                f"• {len(users_data)} users",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in enhanced import: {e}")
            await update.message.reply_text(f"❌ Import failed: {str(e)}")
    
    async def admin_backup_manual_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create manual backup"""
        try:
            from utils.config import ConfigManager
            config_manager = ConfigManager()
            
            timestamp = config_manager.create_manual_backup()
            
            if timestamp:
                await update.message.reply_text(
                    f"✅ **Manual Backup Created**\n\n"
                    f"📅 Timestamp: {timestamp}\n"
                    f"📁 Location: `data/config/backups/`\n\n"
                    f"💡 Manual backups are never auto-deleted",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Failed to create manual backup")
                
        except Exception as e:
            logger.error(f"Error creating manual backup: {e}")
            await update.message.reply_text(f"❌ Backup failed: {str(e)}")
    
    async def admin_list_backups_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all backups"""
        try:
            from utils.config import ConfigManager
            config_manager = ConfigManager()
            
            backups = config_manager.list_backups()
            
            if not backups:
                await update.message.reply_text("📁 No backups found")
                return
            
            message = f"📁 **Available Backups ({len(backups)})**\n\n"
            
            manual_backups = [b for b in backups if b['type'] == 'manual']
            auto_backups = [b for b in backups if b['type'] == 'auto']
            
            if manual_backups:
                message += f"📌 **Manual Backups ({len(manual_backups)}):**\n"
                for backup in manual_backups[:5]:  # Show last 5
                    message += f"• {backup['filename']} - {backup['created']}\n"
                message += "\n"
            
            if auto_backups:
                message += f"🔄 **Auto Backups ({len(auto_backups)}):**\n"
                for backup in auto_backups[:5]:  # Show last 5
                    message += f"• {backup['filename']} - {backup['created']}\n"
            
            if len(backups) > 10:
                message += f"\n... and {len(backups) - 10} more backups"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error listing backups: {e}")
            await update.message.reply_text(f"❌ Error listing backups: {str(e)}")
