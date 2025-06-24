"""
Callback Handlers - PRODUCTION VERSION
Integrated with BotConfig and event system
"""

import logging
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from config import BotConfig
from storage.sqlite_manager import SQLiteManager
from events import get_event_bus, EventType
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
    def __init__(self, config: BotConfig, data_manager: SQLiteManager):
        self.config = config
        self.data_manager = data_manager
        self.event_bus = get_event_bus()
        logger.info("Callback handlers initialized with configuration")
    
    def register(self, app):
        """Register callback query handler"""
        app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        logger.info("Callback query handler registered")
    
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
            # Answer the callback query immediately to remove loading state
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
                await query.edit_message_text(
                    help_text, 
                    reply_markup=create_back_menu(language),
                    parse_mode='Markdown' if '*' in help_text else None
                )
                
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
                
            else:
                logger.warning(f"Unknown callback data: {query.data}")
                
        except Exception as e:
            logger.error(f"Error handling callback query: {e}")
            # Try to answer the callback to prevent loading state
            try:
                error_msg = get_text("error_occurred", language)
                await query.answer(error_msg)
            except Exception:
                pass
            
            # Emit error event
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'callback_handlers',
                'error': str(e),
                'callback_data': query.data,
                'user_id': user_id
            }, source='callback_handlers')
    
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
        
        # Emit language change event
        await self.event_bus.emit(EventType.USER_LANGUAGE_CHANGED, {
            'user_id': user_id,
            'old_language': current_language,
            'new_language': selected_language
        }, source='callback_handlers')
    
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
                
                # Emit event for ignore keywords cleared
                await self.event_bus.emit(EventType.USER_KEYWORDS_UPDATED, {
                    'user_id': user_id,
                    'action': 'ignore_keywords_cleared',
                    'keywords': [],
                    'ignore_keywords': []
                }, source='callback_handlers')
                
            else:
                no_keywords_message = get_text("ignore_cleared_none", language)
                await query.edit_message_text(no_keywords_message, reply_markup=create_back_menu(language))
                
        except Exception as e:
            logger.error(f"Error clearing ignore keywords: {e}")
            error_msg = get_text("error_occurred", language)
            await query.edit_message_text(error_msg, reply_markup=create_back_menu(language))
            
            # Emit error event
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'callback_handlers',
                'error': str(e),
                'operation': 'clear_ignore_keywords',
                'user_id': user_id
            }, source='callback_handlers')
    
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
            # Get current keywords for event
            current_keywords = await self.data_manager.get_user_keywords(user_id)
            current_ignore = await self.data_manager.get_user_ignore_keywords(user_id)
            
            # Clear all keywords and ignore keywords
            await self.data_manager.set_user_keywords(user_id, [])
            await self.data_manager.set_user_ignore_keywords(user_id, [])
            
            # Show success message
            success_message = get_text("monitoring_stopped", language)
            keyboard = create_resume_monitoring_keyboard(language)
            
            await query.edit_message_text(success_message, reply_markup=keyboard)
            
            logger.info(f"User {user_id} stopped monitoring - all keywords cleared")
            
            # Emit monitoring stopped event
            await self.event_bus.emit(EventType.USER_KEYWORDS_UPDATED, {
                'user_id': user_id,
                'action': 'monitoring_stopped',
                'old_keywords': current_keywords,
                'old_ignore_keywords': current_ignore,
                'keywords': [],
                'ignore_keywords': []
            }, source='callback_handlers')
            
        except Exception as e:
            logger.error(f"Error stopping monitoring for user {user_id}: {e}")
            error_msg = get_text("error_occurred", language)
            await query.edit_message_text(error_msg, reply_markup=create_back_menu(language))
            
            # Emit error event
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'callback_handlers',
                'error': str(e),
                'operation': 'stop_monitoring',
                'user_id': user_id
            }, source='callback_handlers')