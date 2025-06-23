"""
Command Handlers - All bot command processing including admin commands
"""

import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from storage.sqlite_manager import SQLiteManager
from utils.helpers import is_private_chat, create_main_menu, get_help_text, get_set_keywords_help, get_add_keyword_help

logger = logging.getLogger(__name__)

class CommandHandlers:
    def __init__(self, data_manager: SQLiteManager):
        self.data_manager = data_manager
    
    def _is_authorized_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check if user is authorized admin"""
        user_monitor = getattr(context.bot_data, 'user_monitor', None)
        if not user_monitor:
            return False
        
        user_id = update.effective_user.id
        return user_monitor.is_authorized_admin(user_id)
    
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
        
        logger.info("Command handlers registered")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not is_private_chat(update):
            logger.info("Start command ignored - not a private chat")
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
        logger.info(f"Sending welcome with menu to user {update.effective_user.id}")
        
        await update.message.reply_text(welcome_msg, reply_markup=menu_markup)
        logger.info("Welcome message sent successfully")
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command"""
        if not is_private_chat(update):
            logger.info("Menu command ignored - not a private chat")
            return
        
        logger.info(f"Sending menu to user {update.effective_user.id}")
        menu_markup = create_main_menu()
        logger.info(f"Created menu with {len(menu_markup.inline_keyboard)} rows of buttons")
        
        await update.message.reply_text("📋 Main Menu:", reply_markup=menu_markup)
        logger.info("Menu sent successfully")
    
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
        
        # First try exact match
        if await self.data_manager.remove_user_keyword(chat_id, keyword_to_delete):
            await update.message.reply_text(f"✅ Removed keyword: {keyword_to_delete}")
            return
        
        # If no exact match, look for patterns containing this keyword
        matching_patterns = []
        for pattern in keywords:
            # Check if the keyword appears in a complex pattern
            if '+' in pattern and keyword_to_delete in pattern:
                matching_patterns.append(pattern)
            elif pattern.startswith('"') and pattern.endswith('"'):
                # Check if it matches a quoted phrase
                phrase = pattern[1:-1].strip()
                if phrase == keyword_to_delete.strip('"'):
                    matching_patterns.append(pattern)
        
        if matching_patterns:
            # Remove all matching patterns
            for pattern in matching_patterns:
                await self.data_manager.remove_user_keyword(chat_id, pattern)
            
            if len(matching_patterns) == 1:
                await update.message.reply_text(f"✅ Removed pattern: {matching_patterns[0]}")
            else:
                patterns_str = ', '.join(matching_patterns)
                await update.message.reply_text(f"✅ Removed {len(matching_patterns)} patterns: {patterns_str}")
        else:
            # Show current keywords to help user
            current = ', '.join(keywords)
            await update.message.reply_text(
                f"❌ Keyword '{keyword_to_delete}' not found!\n\n"
                f"Your current keywords: {current}\n\n"
                f"💡 Use the exact pattern to delete, e.g.:\n"
                f"/delete_keyword_from_list python+\"project manager\""
            )
    
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
    
    # SECURE Authentication commands - ADMIN ONLY
    async def auth_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_status command - ADMIN ONLY"""
        if not is_private_chat(update):
            return
        
        # Security check - only authorized admin
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        user_monitor = getattr(context.bot_data, 'user_monitor', None)
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
        if not is_private_chat(update):
            return
        
        # Security check - only authorized admin
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        chat_id = update.effective_chat.id
        
        user_monitor = getattr(context.bot_data, 'user_monitor', None)
        if not user_monitor:
            await update.message.reply_text("❌ User account monitoring is not enabled.")
            return
        
        success = await user_monitor.restart_auth(chat_id)
        if success:
            await update.message.reply_text("🔄 **Authentication restarted**\n\nCheck your phone for the verification code.", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Failed to restart authentication.")
    
    # ADMIN COMMANDS
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command with subcommands - ADMIN ONLY"""
        if not is_private_chat(update):
            return
        
        # Security check - only authorized admin
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📋 **Admin Commands**\n\n"
                "• `/admin errors` - Show recent errors\n"
                "• `/admin stats` - Bot statistics (coming soon)\n",
                parse_mode='Markdown'
            )
            return
        
        subcommand = context.args[0].lower()
        
        if subcommand == "errors":
            await self.admin_errors_command(update, context)
        else:
            await update.message.reply_text(f"❓ Unknown admin command: {subcommand}")

    async def admin_errors_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin errors command - ADMIN ONLY"""
        if not is_private_chat(update):
            return
        
        # Security check - only authorized admin
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        from utils.error_monitor import get_error_collector
        
        collector = get_error_collector()
        if not collector:
            await update.message.reply_text("❌ Error monitoring not initialized.")
            return
        
        # Get recent errors
        recent_errors = collector.get_recent_errors(24)
        stats = collector.get_error_stats()
        
        if not recent_errors:
            await update.message.reply_text("✅ **No errors in last 24 hours**\n\nBot is running smoothly!", parse_mode='Markdown')
            return
        
        # Format error list
        message = f"📋 **Recent Errors** (Last 24h)\n\n"
        message += f"📊 Total: {stats['total']} ({stats['critical']} critical)\n\n"
        
        # Show last 10 errors
        for error in recent_errors[-10:]:
            timestamp = error['timestamp'].strftime("%H:%M:%S")
            level_emoji = "🚨" if error['level'] == 'CRITICAL' else "❌"
            
            message += f"{level_emoji} {timestamp} - {error['level']}\n"
            message += f"📍 {error['module']}.py:{error['lineno']} in {error['funcName']}\n"
            message += f"📝 {error['message'][:150]}\n\n"
            
            # Telegram message limit
            if len(message) > 3500:
                message += f"... and {len(recent_errors) - len(recent_errors[-10:])} more errors\n"
                break
        
        if len(recent_errors) > 10:
            message += f"Showing last 10 of {len(recent_errors)} errors"
        
        await update.message.reply_text(message, parse_mode='Markdown')