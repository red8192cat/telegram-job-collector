"""
Admin Command Handlers - ALL ADMIN FUNCTIONALITY
Enhanced channel management, system monitoring, and authentication
NO CONFIG EXPORT/IMPORT - Database is single source of truth
"""

import logging
import re
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

from config import BotConfig
from storage.sqlite_manager import SQLiteManager
from events import get_event_bus, EventType
from utils.translations import get_text

logger = logging.getLogger(__name__)

class AdminCommandHandlers:
    def __init__(self, config: BotConfig, data_manager: SQLiteManager):
        self.config = config
        self.data_manager = data_manager
        self.event_bus = get_event_bus()
        logger.info("Admin command handlers initialized")
    
    def _is_authorized_admin(self, update: Update) -> bool:
        """Check if user is authorized admin"""
        if not self.config.AUTHORIZED_ADMIN_ID:
            return False
        
        user_id = update.effective_user.id
        return user_id == self.config.AUTHORIZED_ADMIN_ID
    
    def register(self, app):
        """Register admin command handlers"""
        # Admin commands
        app.add_handler(CommandHandler("admin", self.admin_command))
        app.add_handler(CommandHandler("auth_status", self.auth_status_command))
        app.add_handler(CommandHandler("auth_restart", self.auth_restart_command))
        
        # Authentication handler for non-command messages (admin only)
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            self.handle_auth_message
        ), group=5)  # Higher priority than user handlers
        
        logger.info("Admin command handlers registered")
    
    # =============================================================================
    # AUTHENTICATION HANDLERS
    # =============================================================================
    
    async def handle_auth_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle authentication messages - ADMIN ONLY"""
        if not update.message or update.effective_chat.type != 'private':
            return
        
        if not self._is_authorized_admin(update):
            return  # Ignore non-admin messages
        
        user_monitor = context.bot_data.get('user_monitor', None)
        if not user_monitor:
            return  # No user monitor available
        
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
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'handle_auth_message'
            }, source='admin_commands')
    
    async def auth_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_status command - ADMIN ONLY"""
        if not update.effective_chat or update.effective_chat.type != 'private':
            return
        
        user_id = update.effective_user.id
        
        if not self._is_authorized_admin(update):
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("unknown_command", language))
            return
        
        try:
            user_monitor = context.bot_data.get('user_monitor', None)
            if not user_monitor:
                await update.message.reply_text("❌ User account monitoring is not enabled or unavailable.")
                return
            
            status = user_monitor.get_auth_status()
            
            status_messages = {
                "disabled": "ℹ️ User account monitoring is disabled (no credentials configured).",
                "not_initialized": "❌ User account monitoring failed to initialize.",
                "waiting_for_code": "📱 Waiting for SMS verification code\n\nPlease send the code you received.",
                "waiting_for_2fa": "🔐 Waiting for 2FA password\n\nPlease send your two-factor authentication password.",
                "authenticated": "✅ User account authenticated!\n\nMonitoring is active and working."
            }
            
            message = status_messages.get(status, "❓ Unknown status. Use /auth_restart to restart authentication.")
            await update.message.reply_text(message)
                
        except Exception as e:
            logger.error(f"Error in auth status command: {e}")
            await update.message.reply_text("❌ Error checking authentication status.")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'auth_status_command'
            }, source='admin_commands')

    async def auth_restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_restart command - ADMIN ONLY"""
        if not update.effective_chat or update.effective_chat.type != 'private':
            return
        
        user_id = update.effective_user.id
        
        if not self._is_authorized_admin(update):
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("unknown_command", language))
            return
        
        try:
            chat_id = update.effective_chat.id
            
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
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'auth_restart_command'
            }, source='admin_commands')
    
    # =============================================================================
    # MAIN ADMIN COMMAND ROUTER
    # =============================================================================
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command - Enhanced with database-only channel management"""
        if not update.effective_chat or update.effective_chat.type != 'private':
            return
        
        user_id = update.effective_user.id
        
        if not self._is_authorized_admin(update):
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("unknown_command", language))
            return
        
        try:
            if not context.args:
                await update.message.reply_text(
                    "📋 **Admin Commands**\n\n"
                    "**System:**\n"
                    "• `/admin health` - System health check\n"
                    "• `/admin stats` - Database statistics\n"
                    "• `/admin mode` - Current bot mode\n"
                    "• `/admin errors` - Show recent errors\n\n"
                    "**Channel Management (Database Only):**\n"
                    "• `/admin channels` - List all channels\n"
                    "• `/admin add_bot_channel <channel>` - Add bot channel\n"
                    "• `/admin add_user_channel <channel>` - Add user channel\n"
                    "• `/admin remove_channel <channel>` - Remove any channel\n"
                    "• `/admin update_username <chat_id> <username>` - Update username\n\n"
                    "**Supported Channel Formats:**\n"
                    "• `@channelname`\n"
                    "• `t.me/channelname`\n"
                    "• `https://t.me/channelname`\n"
                    "• `-1001234567890` (chat ID)\n\n"
                    "**Note:** Database is the single source of truth - no config files used.",
                    parse_mode='Markdown'
                )
                return
            
            subcommand = context.args[0].lower()
            
            # Emit admin command executed event
            await self.event_bus.emit(EventType.ADMIN_COMMAND_EXECUTED, {
                'user_id': user_id,
                'command': subcommand,
                'args': context.args[1:] if len(context.args) > 1 else []
            }, source='admin_commands')
            
            # Route to appropriate handler
            command_handlers = {
                "health": self.admin_health_command,
                "stats": self.admin_stats_command,
                "mode": self.admin_mode_command,
                "errors": self.admin_errors_command,
                "channels": self.admin_list_channels_command,
                "add_bot_channel": self.admin_add_bot_channel_command,
                "add_user_channel": self.admin_add_user_channel_command,
                "remove_channel": self.admin_remove_channel_command,
                "update_username": self.admin_update_username_command
            }
            
            handler = command_handlers.get(subcommand)
            if handler:
                await handler(update, context)
            else:
                await update.message.reply_text(f"❓ Unknown admin command: {subcommand}")
                
        except Exception as e:
            logger.error(f"Error in admin command: {e}")
            await update.message.reply_text("❌ Error processing admin command")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'admin_command',
                'subcommand': context.args[0] if context.args else 'none'
            }, source='admin_commands')
    
    # =============================================================================
    # SYSTEM MONITORING COMMANDS
    # =============================================================================
    
    async def admin_health_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin health check"""
        try:
            health_status = []
            
            # Test database
            try:
                stats = await self.data_manager.get_system_stats()
                health_status.append("✅ Database: Connected")
                health_status.append(f"   Users: {stats.get('total_users', 0)}")
            except Exception as e:
                health_status.append(f"❌ Database: Error - {str(e)[:50]}")
            
            # Check user monitor
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
            bot_instance = context.bot_data.get('bot_instance')
            bot_mode = getattr(bot_instance, 'mode', 'unknown') if bot_instance else 'unknown'
            health_status.append(f"🎯 Bot Mode: {bot_mode}")
            
            message = "🏥 **System Health Check**\n\n"
            message += "\n".join(health_status)
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            await update.message.reply_text(f"❌ Health check failed: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'admin_health_command'
            }, source='admin_commands')
    
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
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'admin_stats_command'
            }, source='admin_commands')
    
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
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'admin_mode_command'
            }, source='admin_commands')
    
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
    
    # =============================================================================
    # ENHANCED CHANNEL MANAGEMENT COMMANDS
    # =============================================================================
    
    async def admin_list_channels_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin channels command with cleaner display"""
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
            
            message = "📺 **Channel Status** (Database)\n\n"
            
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

    async def admin_add_bot_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin add_bot_channel command"""
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
            
            # Parse input format
            chat_id, username, display_title = await self._parse_channel_input(channel_input, context)
            if not chat_id:
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
                }, source='admin_commands')
                
                logger.info(f"Admin {update.effective_user.id} added bot channel: {display_title}")
                
            else:
                await update.message.reply_text(f"❌ Channel already exists in database")
                
        except Exception as e:
            logger.error(f"Error adding bot channel: {e}")
            await update.message.reply_text(f"❌ Error adding channel: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'admin_add_bot_channel_command',
                'channel_input': channel_input
            }, source='admin_commands')

    async def admin_add_user_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /admin add_user_channel command"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Usage: `/admin add_user_channel <channel>`\n\n"
                "Note: Requires user monitor to be configured and authenticated.",
                parse_mode='Markdown'
            )
            return
        
        # Check if user monitor is available
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
                }, source='admin_commands')
                
                logger.info(f"Admin {update.effective_user.id} added user channel: {channel_input}")
            else:
                await update.message.reply_text(f"❌ {message}")
                
        except Exception as e:
            logger.error(f"Error adding user channel: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'admin_add_user_channel_command',
                'channel_input': channel_input
            }, source='admin_commands')

    async def admin_remove_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                telegram_identifier = await self._parse_telegram_identifier(channel_input)
                
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
                target_chat_id, target_channel_info = await self._search_database_for_channel(channel_input)
                search_method = "database_search"
            
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
                }, source='admin_commands')
                
                logger.info(f"Admin {update.effective_user.id} removed {channel_type} channel: {target_channel_info['display_name']}")
                
            else:
                await update.message.reply_text("❌ Failed to remove channel from database")
                
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            await update.message.reply_text(f"❌ Error removing channel: {str(e)}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'admin_remove_channel_command',
                'channel_input': channel_input
            }, source='admin_commands')

    async def admin_update_username_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                'component': 'admin_commands',
                'error': str(e),
                'operation': 'admin_update_username_command',
                'chat_id': context.args[1] if len(context.args) > 1 else None
            }, source='admin_commands')
    
    # =============================================================================
    # HELPER METHODS
    # =============================================================================
    
    async def _parse_channel_input(self, channel_input: str, context):
        """Parse channel input and return chat_id, username, display_title"""
        chat_id = None
        username = None
        display_title = None
        
        try:
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
                    await context.bot.send_message(
                        chat_id=context.effective_chat.id,
                        text="❌ Cannot parse channel URL"
                    )
                    return None, None, None
            elif channel_input.lstrip('-').isdigit():
                chat_id = int(channel_input)
                display_title = f"Channel {chat_id}"
            else:
                await context.bot.send_message(
                    chat_id=context.effective_chat.id,
                    text="❌ Invalid channel format"
                )
                return None, None, None
                
            return chat_id, username, display_title
            
        except Exception as e:
            logger.error(f"Error parsing channel input: {e}")
            return None, None, None
    
    async def _parse_telegram_identifier(self, channel_input: str):
        """Parse channel input to Telegram API identifier"""
        if channel_input.lstrip('-').isdigit():
            return int(channel_input)
        elif channel_input.startswith('@'):
            return channel_input
        elif 't.me/' in channel_input or 'telegram.me/' in channel_input:
            url_pattern = r'(?:https?://)?(?:t\.me|telegram\.me)/([^/\s]+)'
            match = re.search(url_pattern, channel_input)
            if match:
                return f"@{match.group(1)}"
        return None
    
    async def _search_database_for_channel(self, channel_input: str):
        """Search database for channel by various identifiers"""
        channel_info = await self.data_manager.get_all_channels_with_usernames()
        
        if channel_input.lstrip('-').isdigit():
            # Direct chat ID
            target_chat_id = int(channel_input)
            target_channel_info = channel_info.get(target_chat_id)
            return target_chat_id, target_channel_info
            
        elif channel_input.startswith('@'):
            # Username format - search database
            for chat_id, info in channel_info.items():
                if info['username'] and info['username'].lower() == channel_input.lower():
                    return chat_id, info
                    
        elif 't.me/' in channel_input or 'telegram.me/' in channel_input:
            # URL format - extract username and search database
            url_pattern = r'(?:https?://)?(?:t\.me|telegram\.me)/([^/\s]+)'
            match = re.search(url_pattern, channel_input)
            if match:
                username_from_url = f"@{match.group(1)}"
                for chat_id, info in channel_info.items():
                    if info['username'] and info['username'].lower() == username_from_url.lower():
                        return chat_id, info
        
        return None, None