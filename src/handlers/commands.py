"""
Command Handlers - DEBUG VERSION with enhanced auth logging
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
        """Check if user is authorized admin - INDEPENDENT of user monitor"""
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
        
        # 🔥 DEBUG: Authentication handler for non-command messages (admin only)
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            self.handle_auth_message_debug
        ), group=10)  # Very low priority
        
        logger.info("All command handlers registered successfully (WITH AUTH DEBUG)")
    
    # 🔥 DEBUG: Enhanced authentication message handler
    async def handle_auth_message_debug(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle authentication messages with DEBUG logging"""
        message = update.message
        if not message or not message.text:
            logger.info("🔥 AUTH DEBUG: No message or text")
            return
        
        user_id = update.effective_user.id
        message_text = message.text.strip()
        
        logger.info(f"🔥 AUTH DEBUG: Received private message from user {user_id}: '{message_text}'")
        
        # Check if user is admin
        is_admin = self._is_authorized_admin(update, context)
        logger.info(f"🔥 AUTH DEBUG: User {user_id} is admin: {is_admin}")
        
        if not is_admin:
            logger.info(f"🔥 AUTH DEBUG: User {user_id} is not admin, ignoring message")
            return
        
        # Check if user monitor exists
        user_monitor = getattr(context.bot_data, 'user_monitor', None)
        logger.info(f"🔥 AUTH DEBUG: User monitor exists: {user_monitor is not None}")
        
        if not user_monitor:
            logger.info("🔥 AUTH DEBUG: No user monitor found in bot_data")
            await message.reply_text("🔥 DEBUG: No user monitor available")
            return
        
        # Check if waiting for auth
        waiting_for_auth = user_monitor.is_waiting_for_auth()
        logger.info(f"🔥 AUTH DEBUG: User monitor waiting for auth: {waiting_for_auth}")
        
        if not waiting_for_auth:
            logger.info("🔥 AUTH DEBUG: User monitor not waiting for auth")
            await message.reply_text("🔥 DEBUG: User monitor not waiting for authentication")
            return
        
        # Check auth status
        auth_status = user_monitor.get_auth_status()
        logger.info(f"🔥 AUTH DEBUG: Auth status: {auth_status}")
        
        # Process the message
        logger.info(f"🔥 AUTH DEBUG: Processing message '{message_text}' as potential auth code")
        
        # Check if it looks like auth code/password
        if message_text.isdigit() and 5 <= len(message_text) <= 6:
            logger.info(f"🔥 AUTH DEBUG: Message looks like SMS code: {len(message_text)} digits")
            await message.reply_text(f"🔥 DEBUG: Processing SMS code ({len(message_text)} digits)")
            
            try:
                handled = await user_monitor.handle_auth_message(user_id, message_text)
                logger.info(f"🔥 AUTH DEBUG: SMS code handling result: {handled}")
                await message.reply_text(f"🔥 DEBUG: SMS code processed, result: {handled}")
            except Exception as e:
                logger.error(f"🔥 AUTH DEBUG: Error processing SMS code: {e}")
                await message.reply_text(f"🔥 DEBUG: Error processing SMS code: {str(e)}")
                
        elif len(message_text) >= 8 and not message_text.isdigit():
            logger.info(f"🔥 AUTH DEBUG: Message looks like 2FA password: {len(message_text)} chars")
            await message.reply_text(f"🔥 DEBUG: Processing 2FA password ({len(message_text)} chars)")
            
            try:
                handled = await user_monitor.handle_auth_message(user_id, message_text)
                logger.info(f"🔥 AUTH DEBUG: 2FA password handling result: {handled}")
                await message.reply_text(f"🔥 DEBUG: 2FA password processed, result: {handled}")
            except Exception as e:
                logger.error(f"🔥 AUTH DEBUG: Error processing 2FA password: {e}")
                await message.reply_text(f"🔥 DEBUG: Error processing 2FA password: {str(e)}")
        else:
            logger.info(f"🔥 AUTH DEBUG: Message doesn't look like auth code: '{message_text}'")
            await message.reply_text(f"🔥 DEBUG: Message doesn't look like auth code")
    
    # All the existing command methods stay exactly the same...
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
        await update.message.reply_text(welcome_msg, reply_markup=menu_markup)
    
    async def auth_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /auth_status command - ADMIN ONLY with DEBUG"""
        if not is_private_chat(update) or not update.message:
            return
        
        # Security check - only authorized admin
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        logger.info("🔥 AUTH DEBUG: /auth_status command called")
        
        user_monitor = getattr(context.bot_data, 'user_monitor', None)
        logger.info(f"🔥 AUTH DEBUG: User monitor found in bot_data: {user_monitor is not None}")
        
        if not user_monitor:
            await update.message.reply_text("❌ User account monitoring is not enabled.")
            return
        
        status = user_monitor.get_auth_status()
        logger.info(f"🔥 AUTH DEBUG: Auth status: {status}")
        
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
        """Handle /auth_restart command - ADMIN ONLY with DEBUG"""
        if not is_private_chat(update) or not update.message:
            return
        
        # Security check - only authorized admin
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        logger.info("🔥 AUTH DEBUG: /auth_restart command called")
        
        user_monitor = getattr(context.bot_data, 'user_monitor', None)
        logger.info(f"🔥 AUTH DEBUG: User monitor found for restart: {user_monitor is not None}")
        
        if not user_monitor:
            await update.message.reply_text("❌ User account monitoring is not enabled.")
            return
        
        chat_id = update.effective_chat.id
        
        try:
            success = await user_monitor.restart_auth(chat_id)
            logger.info(f"🔥 AUTH DEBUG: Restart auth result: {success}")
            if success:
                await update.message.reply_text("🔄 **Authentication restarted**\n\nCheck your phone for the verification code.", parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Failed to restart authentication.")
        except Exception as e:
            logger.error(f"🔥 AUTH DEBUG: Error restarting authentication: {e}")
            await update.message.reply_text(f"❌ Error restarting authentication: {str(e)}")
    
    # Simplified versions of other commands for space...
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_private_chat(update):
            return
        menu_markup = create_main_menu()
        await update.message.reply_text("📋 Main Menu:", reply_markup=menu_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_private_chat(update):
            return
        await update.message.reply_text(get_help_text())
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_private_chat(update) or not update.message:
            return
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        await update.message.reply_text("📋 **Admin Commands**\n\n• `/auth_status` - Check auth status\n• `/auth_restart` - Restart auth", parse_mode='Markdown')
    
    # Add minimal versions of other commands here if needed...