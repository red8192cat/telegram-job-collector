"""
Callback Handlers - Only for settings and help (keywords buttons pre-fill directly)
"""

import logging
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from storage.sqlite_manager import SQLiteManager
from utils.helpers import create_main_menu, create_back_menu, get_help_text, create_ignore_keywords_help_keyboard

logger = logging.getLogger(__name__)

class CallbackHandlers:
    def __init__(self, data_manager: SQLiteManager):
        self.data_manager = data_manager
    
    def register(self, app):
        """Register callback query handler"""
        app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        logger.info("Callback query handler registered")
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons"""
        query = update.callback_query
        if not query:
            return
            
        try:
            await query.answer()
            
            if query.data == "menu_keywords":
                # Send same instruction message as bot menu command
                help_text = (
                    "🎯 Set Keywords\n\n"
                    "Use commas to separate keywords:\n"
                    "/keywords [remote*|online*], python, develop*, support* engineer*\n\n"
                    "Types:\n"
                    "• Required: [remote*] (MUST be in every message)\n"
                    "• Required OR: [remote*|online*] (either must be present)\n"
                    "• Exact: python, java, linux\n"
                    "• Wildcard: develop*, engineer* (matches variations)\n"
                    "• Phrases: support* engineer* (adjacent words)\n"
                    "• AND: python+django (advanced - both required)\n\n"
                    "💡 Logic: (ALL required) AND (at least one optional)\n"
                    "✨ No quotes needed - just use commas!\n\n"
                    "👇 Tap the button below to fill the command:"
                )
                
                from utils.helpers import create_keywords_help_keyboard
                await query.edit_message_text(help_text, reply_markup=create_keywords_help_keyboard())
                
            elif query.data == "menu_ignore":
                # Send same instruction message as bot menu command
                help_text = (
                    "🚫 Set Ignore Keywords\n\n"
                    "Use commas to separate ignore keywords:\n"
                    "/ignore_keywords javascript*, manage*, senior*\n\n"
                    "Same rules as regular keywords:\n"
                    "• Exact: java, php, manager\n"
                    "• Wildcard: manage*, senior*, lead*\n"
                    "• Phrases: team* lead*, project* manager*\n\n"
                    "These will block job posts even if they match your keywords.\n\n"
                    "🗑️ Use /purge_ignore to clear all ignore keywords\n\n"
                    "👇 Tap the button below to fill the command:"
                )
                
                from utils.helpers import create_ignore_keywords_help_keyboard
                await query.edit_message_text(help_text, reply_markup=create_ignore_keywords_help_keyboard())
            
            if query.data == "menu_show_settings":
                chat_id = query.from_user.id
                
                # Get both keywords and ignore keywords
                keywords = await self.data_manager.get_user_keywords(chat_id)
                ignore_keywords = await self.data_manager.get_user_ignore_keywords(chat_id)
                
                # Build combined message - same as /my_settings command
                msg = "⚙️ Your Current Settings\n\n"
                
                if keywords:
                    msg += f"📝 Keywords: {', '.join(keywords)}\n\n"
                else:
                    msg += "📝 Keywords: None set\nUse /keywords to set them.\n\n"
                
                if ignore_keywords:
                    msg += f"🚫 Ignore Keywords: {', '.join(ignore_keywords)}\n\n"
                else:
                    msg += "🚫 Ignore Keywords: None set\nUse /ignore_keywords to set them.\n\n"
                
                # Add status information
                if keywords:
                    msg += "🎯 Status: Monitoring for NEW jobs that match your keywords\n"
                    msg += "⏰ Only fresh posts are forwarded - no old jobs\n\n"
                
                msg += "💡 Quick Commands:\n"
                msg += "• /keywords - Update search keywords\n"
                msg += "• /ignore_keywords - Update ignore keywords\n"
                msg += "• /purge_ignore - Clear all ignore keywords"
                
                await query.edit_message_text(msg, reply_markup=create_back_menu())
                
            elif query.data == "menu_help":
                await query.edit_message_text(get_help_text(), reply_markup=create_back_menu())
                
            elif query.data == "menu_back":
                # Back button shows the /start message with menu
                welcome_msg = (
                    "🤖 Welcome to JobFinderBot!\n\n"
                    "I help you collect job postings from some channels based on your keywords.\n\n"
                    "✅ Advanced keyword filtering\n"
                    "✅ Ignore unwanted posts\n"
                    "⏰ Real-time alerts for NEW jobs only (no old posts!)\n\n"
                    "Use the menu below to get started:"
                )
                await query.edit_message_text(welcome_msg, reply_markup=create_main_menu())
                
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            # Try to answer the callback to prevent loading state
            try:
                await query.answer("❌ Something went wrong. Please try again.")
            except:
                pass