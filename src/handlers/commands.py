"""
Command Handlers - Production version with channel management
"""

import logging
import os
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

from storage.sqlite_manager import SQLiteManager
from utils.helpers import is_private_chat, create_main_menu, get_help_text, get_set_keywords_help, get_add_keyword_help

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
        """Register all command handlers"""
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("menu", self.menu_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("keywords", self.set_keywords_command))
        app.add_handler(CommandHandler("ignore_keywords", self.set_ignore_keywords_command))
        app.add_handler(CommandHandler("add_keyword_to_list", self.add_keyword_command))
        app.add_handler(CommandHandler("delete_keyword_from_list", self.delete_keyword_command))
        app.add_handler(CommandHandler("add_ignore_keyword", self.add_ignore_keyword_command))
        app.add_handler(CommandHandler("delete_ignore_keyword", self.delete_ignore_keyword_command))
        app.add_handler(CommandHandler("purge_ignore", self.purge_ignore_keywords_command))
        app.add_handler(CommandHandler("my_keywords", self.show_keywords_command))
        app.add_handler(CommandHandler("my_ignore", self.show_ignore_keywords_command))
        
        # SECURE authentication commands - only for authorized admin
        app.add_handler(CommandHandler("auth_status", self.auth_status_command))
        app.add_handler(CommandHandler("auth_restart", self.auth_restart_command))
        
        # Admin commands
        app.add_handler(CommandHandler("admin", self.admin_command))
        
        # Authentication handler for non-command messages (admin only)
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            self.handle_auth_message
        ), group=10)  # Very low priority
        
        logger.info("All command handlers registered successfully")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not is_private_chat(update):
            return
        
        logger.info(f"Start command from user {update.effective_user.id}")
        
        welcome_msg = (
            "🤖 Welcome to Job Collector Bot!\n\n"
            "I help you collect job postings from configured channels based on your keywords.\n\n"
            "✅ All users get unlimited job forwards\n"
            "✅ Advanced keyword filtering with ignore list\n\n"
            "Use the menu below to get started:"
        )
        
        menu_markup = create_main_menu()
        await update.message.reply_text(welcome_msg, reply_markup=menu_markup)
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command"""
        if not is_private_chat(update):
            return
        
        menu_markup = create_main_menu()
        await update.message.reply_text("📋 Main Menu:", reply_markup=menu_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not is_private_chat(update):
            return
        
        await update.message.reply_text(get_help_text())
    
    async def set_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /keywords command"""
        if not is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text(get_set_keywords_help())
            return
        
        keywords_text = ' '.join(context.args)
        keywords = [k.strip().lower() for k in keywords_text.split(',') if k.strip()]
        
        if not keywords:
            await update.message.reply_text("No valid keywords provided!")
            return
        
        await self.data_manager.set_user_keywords(chat_id, keywords)
        
        keywords_str = ', '.join(keywords)
        await update.message.reply_text(f"✅ Keywords set: {keywords_str}")
    
    async def set_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ignore_keywords command"""
        if not is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide ignore keywords: /ignore_keywords java, senior, manager")
            return
        
        keywords_text = ' '.join(context.args)
        keywords = [k.strip().lower() for k in keywords_text.split(',') if k.strip()]
        
        if not keywords:
            await update.message.reply_text("No valid ignore keywords provided!")
            return
        
        await self.data_manager.set_user_ignore_keywords(chat_id, keywords)
        
        keywords_str = ', '.join(keywords)
        await update.message.reply_text(f"✅ Ignore keywords set: {keywords_str}")
    
    async def add_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_keyword_to_list command"""
        if not is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text(get_add_keyword_help())
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if await self.data_manager.add_user_keyword(chat_id, keyword):
            await update.message.reply_text(f"✅ Added keyword: {keyword}")
        else:
            await update.message.reply_text(f"Keyword '{keyword}' already in your list!")
    
    async def delete_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_keyword_from_list command"""
        if not is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide a keyword: /delete_keyword_from_list python")
            return
        
        keyword_to_delete = ' '.join(context.args).strip().lower()
        keywords = await self.data_manager.get_user_keywords(chat_id)
        
        if not keywords:
            await update.message.reply_text("You don't have any keywords set!")
            return
        
        if await self.data_manager.remove_user_keyword(chat_id, keyword_to_delete):
            await update.message.reply_text(f"✅ Removed keyword: {keyword_to_delete}")
        else:
            current = ', '.join(keywords)
            await update.message.reply_text(
                f"❌ Keyword '{keyword_to_delete}' not found!\n\n"
                f"Your current keywords: {current}"
            )
    
    async def add_ignore_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_ignore_keyword command"""
        if not is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide an ignore keyword: /add_ignore_keyword java")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if await self.data_manager.add_user_ignore_keyword(chat_id, keyword):
            await update.message.reply_text(f"✅ Added ignore keyword: {keyword}")
        else:
            await update.message.reply_text(f"Ignore keyword '{keyword}' already in your list!")
    
    async def delete_ignore_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_ignore_keyword command"""
        if not is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide an ignore keyword: /delete_ignore_keyword java")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if await self.data_manager.remove_user_ignore_keyword(chat_id, keyword):
            await update.message.reply_text(f"✅ Removed ignore keyword: {keyword}")
        else:
            await update.message.reply_text(f"Ignore keyword '{keyword}' not found in your list!")
    
    async def purge_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /purge_ignore command"""
        if not is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if await self.data_manager.purge_user_ignore_keywords(chat_id):
            await update.message.reply_text("✅ All ignore keywords cleared!")
        else:
            await update.message.reply_text("You don't have any ignore keywords set!")
    
    async def show_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_keywords command"""
        if not is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        keywords = await self.data_manager.get_user_keywords(chat_id)
        
        if keywords:
            keywords_str = ', '.join(keywords)
            await update.message.reply_text(f"📝 Your keywords: {keywords_str}")
        else:
            await update.message.reply_text("You haven't set any keywords yet!")
    
    async def show_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_ignore command"""
        if not is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        ignore_keywords = await self.data_manager.get_user_ignore_keywords(chat_id)
        
        if ignore_keywords:
            ignore_str = ', '.join(ignore_keywords)
            await update.message.reply_text(f"🚫 Your ignore keywords: {ignore_str}")
        else:
            await update.message.reply_text("You haven't set any ignore keywords yet!")
    
    # ADMIN COMMANDS
    async def auth_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_status command - ADMIN ONLY"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
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
            await update.message.reply_text("📱 **Waiting for SMS verification code**\n\nPlease send the code you received.", parse_mode='Markdown')
        elif status == "waiting_for_2fa":
            await update.message.reply_text("🔐 **Waiting for 2FA password**\n\nPlease send your two-factor authentication password.", parse_mode='Markdown')
        elif status == "authenticated":
            await update.message.reply_text("✅ **User account authenticated!**\n\nMonitoring is active and working.", parse_mode='Markdown')
        else:
            await update.message.reply_text("❓ Unknown status. Use /auth_restart to restart authentication.")

    async def auth_restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_restart command - ADMIN ONLY"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        chat_id = update.effective_chat.id
        
        user_monitor = context.bot_data.get('user_monitor', None)
        if not user_monitor:
            await update.message.reply_text("❌ User account monitoring is not enabled.")
            return
        
        try:
            success = await user_monitor.restart_auth(chat_id)
            if success:
                await update.message.reply_text("🔄 **Authentication restarted**\n\nCheck your phone for the verification code.", parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Failed to restart authentication.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error restarting authentication: {str(e)}")
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command with subcommands - ADMIN ONLY"""
        if not is_private_chat(update) or not update.message:
            return
        
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📋 **Admin Commands**\n\n"
                "**System:**\n"
                "• `/admin health` - System health check\n"
                "• `/admin stats` - Database statistics\n"
                "• `/admin errors` - Show recent errors\n\n"
                "**Channel Management:**\n"
                "• `/admin channels` - List all channels\n"
                "• `/admin add_user_channel @channel` - Add user monitor channel\n"
                "• `/admin remove_user_channel @channel` - Remove user channel\n"
                "• `/admin export_config` - Update config.json\n",
                parse_mode='Markdown'
            )
            return
        
        subcommand = context.args[0].lower()
        
        if subcommand == "health":
            await self.admin_health_command(update, context)
        elif subcommand == "stats":
            await self.admin_stats_command(update, context)
        elif subcommand == "errors":
            await self.admin_errors_command(update, context)
        elif subcommand == "channels":
            await self.admin_channels_command(update, context)
        elif subcommand == "add_user_channel":
            await self.admin_add_user_channel_command(update, context)
        elif subcommand == "remove_user_channel":
            await self.admin_remove_user_channel_command(update, context)
        elif subcommand == "export_config":
            await self.admin_export_config_command(update, context)
        else:
            await update.message.reply_text(f"❓ Unknown admin command: {subcommand}")

    async def admin_health_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin health command"""
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
            
            message = "🏥 **System Health Check**\n\n"
            message += "\n".join(health_status)
            
            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Health check failed: {str(e)}")
    
    async def admin_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin stats command"""
        try:
            all_users = await self.data_manager.get_all_users_with_keywords()
            total_users = len(all_users)
            total_keywords = sum(len(keywords) for keywords in all_users.values())
            
            # Get channel counts
            bot_channels = await self.data_manager.get_bot_monitored_channels_db()
            user_channels = await self.data_manager.get_user_monitored_channels_db()
            
            message = (
                f"📊 **Database Statistics**\n\n"
                f"👥 Total Users: {total_users}\n"
                f"🎯 Total Keywords: {total_keywords}\n"
                f"📈 Avg Keywords/User: {total_keywords / total_users if total_users > 0 else 0:.1f}\n\n"
                f"📺 Bot Channels: {len(bot_channels)}\n"
                f"👤 User Channels: {len(user_channels)}\n"
            )
            
            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting statistics: {str(e)}")
    
    async def admin_errors_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin errors command"""
        try:
            from utils.error_monitor import get_error_collector
            collector = get_error_collector()
        except ImportError:
            await update.message.reply_text("❌ Error monitoring not available.")
            return
        
        if not collector:
            await update.message.reply_text("❌ Error monitoring not initialized.")
            return
        
        recent_errors = collector.get_recent_errors(24)
        
        if not recent_errors:
            await update.message.reply_text("✅ **No errors in last 24 hours**\n\nBot is running smoothly!", parse_mode='Markdown')
            return
        
        message = f"📋 **Recent Errors** (Last 24h)\n\n"
        message += f"📊 Total: {len(recent_errors)} errors\n\n"
        
        for error in recent_errors[-5:]:  # Show last 5
            timestamp = error['timestamp'].strftime("%H:%M:%S")
            message += f"❌ {timestamp} - {error['level']}\n"
            message += f"📍 {error['module']}.py:{error['lineno']}\n"
            message += f"📝 {error['message'][:100]}\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def admin_channels_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin channels command"""
        try:
            channels = await self.data_manager.get_all_monitored_channels_db()
            
            if not channels:
                await update.message.reply_text("📭 **No channels configured**\n\nUse `/admin add_user_channel @channel` to add channels.")
                return
            
            bot_channels = [ch['identifier'] for ch in channels if ch['type'] == 'bot']
            user_channels = [ch['identifier'] for ch in channels if ch['type'] == 'user']
            
            message = "📺 **Monitored Channels**\n\n"
            
            if bot_channels:
                message += f"**Bot Channels ({len(bot_channels)}):**\n"
                for channel in bot_channels:
                    message += f"• {channel}\n"
                message += "\n"
            
            if user_channels:
                message += f"**User Channels ({len(user_channels)}):**\n"
                for channel in user_channels:
                    message += f"• {channel}\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting channels: {str(e)}")
    
    async def admin_add_user_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin add_user_channel command"""
        if len(context.args) < 2:
            await update.message.reply_text("Usage: `/admin add_user_channel @channel`", parse_mode='Markdown')
            return
        
        channel_identifier = context.args[1]
        
        # Validate channel format
        if not (channel_identifier.startswith('@') or channel_identifier.startswith('-')):
            await update.message.reply_text("❌ Channel must start with @ or be a numeric ID starting with -")
            return
        
        try:
            user_monitor = context.bot_data.get('user_monitor', None)
            if not user_monitor:
                await update.message.reply_text("❌ User account monitoring not available.")
                return
            
            success, message = await user_monitor.add_channel(channel_identifier)
            await update.message.reply_text(message)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error adding channel: {str(e)}")
    
    async def admin_remove_user_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin remove_user_channel command"""
        if len(context.args) < 2:
            await update.message.reply_text("Usage: `/admin remove_user_channel @channel`", parse_mode='Markdown')
            return
        
        channel_identifier = context.args[1]
        
        try:
            user_monitor = context.bot_data.get('user_monitor', None)
            if not user_monitor:
                await update.message.reply_text("❌ User account monitoring not available.")
                return
            
            success, message = await user_monitor.remove_channel(channel_identifier)
            await update.message.reply_text(message)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error removing channel: {str(e)}")
    
    async def admin_export_config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin export_config command"""
        try:
            user_monitor = context.bot_data.get('user_monitor', None)
            if user_monitor:
                await user_monitor._export_config()
                await update.message.reply_text("✅ **Config exported**\n\nDatabase channels saved to config.json", parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ User monitor not available for config export.")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error exporting config: {str(e)}")
    
    async def handle_auth_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle authentication messages"""
        if not update.message or not update.message.text:
            return
        
        # Only handle for admin user
        if not self._is_authorized_admin(update, context):
            return
        
        user_monitor = context.bot_data.get('user_monitor', None)
        if not user_monitor or not user_monitor.is_waiting_for_auth():
            return
        
        user_id = update.effective_user.id
        message_text = update.message.text.strip()
        
        # Only handle likely auth codes/passwords
        if message_text.isdigit() and 5 <= len(message_text) <= 6:
            # SMS code
            await user_monitor.handle_auth_message(user_id, message_text)
        elif len(message_text) >= 8 and not message_text.isdigit():
            # 2FA password  
            await user_monitor.handle_auth_message(user_id, message_text)