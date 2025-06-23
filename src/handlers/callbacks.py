"""
Callback Handlers - Simplified menu interactions with merged settings
"""

import logging
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from storage.sqlite_manager import SQLiteManager
from utils.helpers import create_main_menu, create_back_menu, get_help_text, get_keywords_help, get_ignore_help

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
                await query.edit_message_text(get_keywords_help(), reply_markup=create_back_menu(), parse_mode='Markdown')
            elif query.data == "menu_ignore":
                await query.edit_message_text(get_ignore_help(), reply_markup=create_back_menu(), parse_mode='Markdown')
            elif query.data == "menu_show_settings":
                chat_id = query.from_user.id
                
                # Get both keywords and ignore keywords
                keywords = await self.data_manager.get_user_keywords(chat_id)
                ignore_keywords = await self.data_manager.get_user_ignore_keywords(chat_id)
                
                # Build combined message
                msg = "⚙️ **Your Current Settings**\n\n"
                
                if keywords:
                    msg += f"📝 **Keywords:** {', '.join(keywords)}\n\n"
                else:
                    msg += "📝 **Keywords:** None set\nUse `/keywords` to set them.\n\n"
                
                if ignore_keywords:
                    msg += f"🚫 **Ignore Keywords:** {', '.join(ignore_keywords)}\n\n"
                else:
                    msg += "🚫 **Ignore Keywords:** None set\nUse `/ignore_keywords` to set them.\n\n"
                
                msg += "💡 **Quick Commands:**\n"
                msg += "• `/keywords` - Update search keywords\n"
                msg += "• `/ignore_keywords` - Update ignore keywords\n"
                msg += "• `/purge_ignore` - Clear all ignore keywords"
                
                await query.edit_message_text(msg, reply_markup=create_back_menu(), parse_mode='Markdown')
            elif query.data == "menu_help":
                await query.edit_message_text(get_help_text(), reply_markup=create_back_menu(), parse_mode='Markdown')
            elif query.data == "menu_back":
                await query.edit_message_text("📋 **Main Menu:**", reply_markup=create_main_menu(), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")