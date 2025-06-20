"""
Callback Handlers - Menu button interactions
"""

import logging
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from storage.data_manager import DataManager
from utils.helpers import create_main_menu, create_back_menu, get_help_text, get_keywords_help, get_ignore_help, get_contact_info

logger = logging.getLogger(__name__)

class CallbackHandlers:
    def __init__(self, data_manager: DataManager):
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
                await query.edit_message_text(get_keywords_help(), reply_markup=create_back_menu())
            elif query.data == "menu_ignore":
                await query.edit_message_text(get_ignore_help(), reply_markup=create_back_menu())
            elif query.data == "menu_show_keywords":
                chat_id = query.from_user.id
                keywords = await self.data_manager.get_user_keywords(chat_id)
                if keywords:
                    msg = f"📝 Your keywords: {', '.join(keywords)}"
                else:
                    msg = "You haven't set any keywords yet!"
                await query.edit_message_text(msg, reply_markup=create_back_menu())
            elif query.data == "menu_show_ignore":
                chat_id = query.from_user.id
                ignore_keywords = await self.data_manager.get_user_ignore_keywords(chat_id)
                if ignore_keywords:
                    msg = f"🚫 Your ignore keywords: {', '.join(ignore_keywords)}"
                else:
                    msg = "You haven't set any ignore keywords yet!"
                await query.edit_message_text(msg, reply_markup=create_back_menu())
            elif query.data == "menu_contact":
                await query.edit_message_text(get_contact_info(), reply_markup=create_back_menu())
            elif query.data == "menu_help":
                await query.edit_message_text(get_help_text(), reply_markup=create_back_menu())
            elif query.data == "menu_back":
                await query.edit_message_text("📋 Main Menu:", reply_markup=create_main_menu())
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
