"""
Callback Handlers - Updated with manage_keywords flow and stop monitoring
All user-facing messages are now translated based on user's language preference
"""

import logging
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from storage.sqlite_manager import SQLiteManager
from utils.helpers import (
    create_main_menu, create_back_menu, create_ignore_keywords_help_keyboard, 
    create_keywords_help_keyboard, create_language_selection_keyboard,
    format_settings_message, format_manage_keywords_message,
    create_manage_keywords_keyboard, create_settings_keyboard,
    create_stop_monitoring_keyboard, create_resume_monitoring_keyboard
)
from utils.translations import get_text, is_supported_language

logger = logging.getLogger(__name__)

class CallbackHandlers:
    def __init__(self, data_manager: SQLiteManager):
        self.data_manager = data_manager
    
    def register(self, app):
        """Register callback query handler"""
        app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        logger.info("Callback query handler with manage_keywords flow registered")
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons"""
        query = update.callback_query
        if not query:
            return
            
        user_id = query.from_user.id
        logger.debug(f"Callback received: {query.data} from user {user_id}")
        
        # Get user's language preference
        language = await self.data_manager.get_user_language(user_id)
        
        try:
            await query.answer()
            
            # Language selection callbacks
            if query.data.startswith("lang_"):
                await self._handle_language_selection(query, context, language)
                
            elif query.data == "menu_manage_keywords":
                await self._handle_manage_keywords(query, context, language)
                
            elif query.data == "menu_show_settings":
                await self._handle_show_settings(query, context, language)
                
            elif query.data == "menu_help":
                help_text = get_text("help_text", language)
                await query.edit_message_text(help_text, reply_markup=create_back_menu(language))
                
            elif query.data == "menu_language":
                # Show language selection
                title = get_text("language_selection_title", language)
                await query.edit_message_text(title, reply_markup=create_language_selection_keyboard())
                
            elif query.data == "menu_back":
                # Back to main menu - use CURRENT user language
                current_language = await self.data_manager.get_user_language(user_id)
                welcome_msg = get_text("welcome_message", current_language)
                await query.edit_message_text(welcome_msg, reply_markup=create_main_menu(current_language))
                
            # Manage keywords flow callbacks
            elif query.data == "manage_set_keywords":
                await self._handle_set_keywords_help(query, context, language)
                
            elif query.data == "manage_set_ignore":
                await self._handle_set_ignore_help(query, context, language)
                
            elif query.data == "manage_clear_ignore":
                await self._handle_clear_ignore_keywords(query, context, language)
                
            elif query.data == "manage_stop_monitoring":
                await self._handle_stop_monitoring_confirm(query, context, language)
                
            elif query.data == "confirm_stop_monitoring":
                await self._handle_confirm_stop_monitoring(query, context, language)
                
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            # Try to answer the callback to prevent loading state
            try:
                error_msg = get_text("error_occurred", language)
                await query.answer(error_msg)
            except:
                pass
    
    async def _handle_language_selection(self, query, context, current_language):
        """Handle language selection from callback"""
        # Extract language code from callback data
        selected_language = query.data.replace("lang_", "")
        
        logger.info(f"Language selection: {selected_language} for user {query.from_user.id}")
        
        if not is_supported_language(selected_language):
            logger.warning(f"Unsupported language selected: {selected_language}")
            return
        
        user_id = query.from_user.id
        
        # Update user's language preference
        await self.data_manager.set_user_language(user_id, selected_language)
        
        # Send confirmation message in the NEW language
        success_msg = get_text("language_changed", selected_language)
        await query.edit_message_text(success_msg, reply_markup=create_back_menu(selected_language))
        
        logger.info(f"User {user_id} changed language to {selected_language}")
    
    async def _handle_manage_keywords(self, query, context, language):
        """Handle manage keywords menu"""
        user_id = query.from_user.id
        
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
        
        await query.edit_message_text(full_msg, reply_markup=keyboard)
    
    async def _handle_show_settings(self, query, context, language):
        """Handle show settings action"""
        user_id = query.from_user.id
        
        # Get both keywords and ignore keywords
        keywords = await self.data_manager.get_user_keywords(user_id)
        ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_id)
        
        # Use helper to format message
        msg = format_settings_message(keywords, ignore_keywords, language)
        keyboard = create_settings_keyboard(bool(keywords), language)
        
        await query.edit_message_text(msg, reply_markup=keyboard)
    
    async def _handle_set_keywords_help(self, query, context, language):
        """Handle set keywords help"""
        help_text = get_text("keywords_help_text", language)
        await query.edit_message_text(help_text, reply_markup=create_keywords_help_keyboard(language))
    
    async def _handle_set_ignore_help(self, query, context, language):
        """Handle set ignore keywords help"""
        help_text = get_text("ignore_help_text", language)
        await query.edit_message_text(help_text, reply_markup=create_ignore_keywords_help_keyboard(language))
    
    async def _handle_clear_ignore_keywords(self, query, context, language):
        """Handle clear ignore keywords action"""
        user_id = query.from_user.id
        logger.debug(f"Clear ignore keywords requested by user {user_id}")
        
        try:
            result = await self.data_manager.purge_user_ignore_keywords(user_id)
            logger.debug(f"Purge ignore keywords result: {result}")
            
            if result:
                success_message = get_text("ignore_cleared_success", language)
                await query.edit_message_text(success_message, reply_markup=create_back_menu(language))
            else:
                no_keywords_message = get_text("ignore_cleared_none", language)
                await query.edit_message_text(no_keywords_message, reply_markup=create_back_menu(language))
                
        except Exception as e:
            logger.error(f"Error clearing ignore keywords: {e}")
            error_msg = get_text("error_occurred", language)
            await query.edit_message_text(error_msg, reply_markup=create_back_menu(language))
    
    async def _handle_stop_monitoring_confirm(self, query, context, language):
        """Handle stop monitoring confirmation dialog"""
        confirm_text = get_text("stop_monitoring_confirm", language)
        keyboard = create_stop_monitoring_keyboard(language)
        
        await query.edit_message_text(confirm_text, reply_markup=keyboard)
    
    async def _handle_confirm_stop_monitoring(self, query, context, language):
        """Handle confirmed stop monitoring action"""
        user_id = query.from_user.id
        logger.info(f"Stop monitoring confirmed by user {user_id}")
        
        try:
            # Clear all keywords and ignore keywords
            await self.data_manager.set_user_keywords(user_id, [])
            await self.data_manager.set_user_ignore_keywords(user_id, [])
            
            # Show success message
            success_message = get_text("monitoring_stopped", language)
            keyboard = create_resume_monitoring_keyboard(language)
            
            await query.edit_message_text(success_message, reply_markup=keyboard)
            
            logger.info(f"User {user_id} stopped monitoring - all keywords cleared")
            
        except Exception as e:
            logger.error(f"Error stopping monitoring for user {user_id}: {e}")
            error_msg = get_text("error_occurred", language)
            await query.edit_message_text(error_msg, reply_markup=create_back_menu(language))
