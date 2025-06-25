"""
Command Handlers - USER COMMANDS ONLY (Admin moved to separate module)
All user-facing messages are translated based on user's language preference
"""

import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

from config import BotConfig
from storage.sqlite_manager import SQLiteManager
from events import get_event_bus, EventType
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
    def __init__(self, config: BotConfig, data_manager: SQLiteManager):
        self.config = config
        self.data_manager = data_manager
        self.event_bus = get_event_bus()
        logger.info("Command handlers initialized with configuration")
    
    def register(self, app):
        """Register command handlers"""
        # Essential user commands
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("manage_keywords", self.manage_keywords_command))
        app.add_handler(CommandHandler("my_settings", self.show_settings_command))
        
        # Legacy commands (backward compatibility)
        app.add_handler(CommandHandler("keywords", self.set_keywords_command))
        app.add_handler(CommandHandler("ignore_keywords", self.set_ignore_keywords_command))
        app.add_handler(CommandHandler("purge_ignore", self.purge_ignore_keywords_command))
        
        # Handler for messages that start with @bot_name (from inline queries)
        app.add_handler(MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE,
            self.handle_bot_mention_message
        ), group=20)
        
        logger.info("User command handlers registered")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with language selection for new users"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        logger.info(f"Start command from user {user_id}")
        
        try:
            # Get user's current language
            user_language = await self.data_manager.get_user_language(user_id)
            
            # Check if user is completely new
            user_exists = await self._user_has_interacted_before(user_id)
            
            if not user_exists:
                # New user - show language selection first
                welcome_msg = get_text("language_selection_message", self.config.DEFAULT_LANGUAGE)
                keyboard = create_language_selection_keyboard()
                
                await update.message.reply_text(welcome_msg, reply_markup=keyboard)
                
                # Emit user registered event
                await self.event_bus.emit(EventType.USER_REGISTERED, {
                    'user_id': user_id,
                    'language': self.config.DEFAULT_LANGUAGE
                }, source='commands')
                
            else:
                # Existing user - show main menu in their language
                welcome_msg = get_text("welcome_message", user_language)
                menu_markup = create_main_menu(user_language)
                await update.message.reply_text(welcome_msg, reply_markup=menu_markup)
                
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'start_command',
                'user_id': user_id
            }, source='commands')
            
            # Fallback response
            await update.message.reply_text("Welcome! Please try again.")
    
    async def _user_has_interacted_before(self, user_id: int) -> bool:
        """Check if user has interacted with bot before"""
        try:
            # Check if user has keywords set
            keywords = await self.data_manager.get_user_keywords(user_id)
            if keywords:
                return True
            
            # Check if user has custom language
            language = await self.data_manager.get_user_language(user_id)
            return language != self.config.DEFAULT_LANGUAGE
            
        except Exception:
            return False
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_help_text(language))
            
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'help_command',
                'user_id': user_id
            }, source='commands')
    
    async def manage_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /manage_keywords command - unified keyword management"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
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
            
        except Exception as e:
            logger.error(f"Error in manage keywords command: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'manage_keywords_command',
                'user_id': user_id
            }, source='commands')
    
    async def show_settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_settings command - shows read-only dashboard"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
            language = await self.data_manager.get_user_language(user_id)
            
            keywords = await self.data_manager.get_user_keywords(user_id)
            ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_id)
            
            # Use helper to format message
            msg = format_settings_message(keywords, ignore_keywords, language)
            keyboard = create_settings_keyboard(bool(keywords), language)
            
            await update.message.reply_text(msg, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error in show settings command: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'show_settings_command',
                'user_id': user_id
            }, source='commands')
    
    # Legacy commands (keep for backward compatibility)
    async def set_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /keywords command - legacy support"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
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
            
            # Set keywords (this will validate limits)
            await self.data_manager.set_user_keywords(user_id, keywords)
            
            # Enhanced success message
            keywords_str = ', '.join(keywords)
            success_message = get_text("keywords_success", language, keywords=keywords_str)
            
            await update.message.reply_text(success_message)
            
            # Emit keywords updated event
            await self.event_bus.emit(EventType.USER_KEYWORDS_UPDATED, {
                'user_id': user_id,
                'keywords': keywords,
                'keyword_count': len(keywords),
                'action': 'set_keywords'
            }, source='commands')
            
            logger.info(f"User {user_id} set {len(keywords)} keywords")
            
        except ValueError as e:
            # Handle validation errors (too many keywords, etc.)
            await update.message.reply_text(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"Error setting keywords: {e}")
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("error_occurred", language))
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'set_keywords_command',
                'user_id': user_id
            }, source='commands')
    
    async def set_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ignore_keywords command - legacy support"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
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
            
            # Set ignore keywords (this will validate limits)
            await self.data_manager.set_user_ignore_keywords(user_id, keywords)
            
            # Enhanced success message
            keywords_str = ', '.join(keywords)
            success_message = get_text("ignore_keywords_success", language, keywords=keywords_str)
            
            await update.message.reply_text(success_message)
            
            # Emit keywords updated event
            await self.event_bus.emit(EventType.USER_KEYWORDS_UPDATED, {
                'user_id': user_id,
                'ignore_keywords': keywords,
                'ignore_keyword_count': len(keywords),
                'action': 'set_ignore_keywords'
            }, source='commands')
            
            logger.info(f"User {user_id} set {len(keywords)} ignore keywords")
            
        except ValueError as e:
            # Handle validation errors
            await update.message.reply_text(f"❌ {str(e)}")
        except Exception as e:
            logger.error(f"Error setting ignore keywords: {e}")
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("error_occurred", language))
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'set_ignore_keywords_command',
                'user_id': user_id
            }, source='commands')
    
    async def purge_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /purge_ignore command - legacy support"""
        if not is_private_chat(update):
            return
        
        user_id = update.effective_user.id
        
        try:
            language = await self.data_manager.get_user_language(user_id)
            
            if await self.data_manager.purge_user_ignore_keywords(user_id):
                success_message = get_text("ignore_cleared_success", language)
                await update.message.reply_text(success_message)
                
                # Emit keywords updated event
                await self.event_bus.emit(EventType.USER_KEYWORDS_UPDATED, {
                    'user_id': user_id,
                    'ignore_keywords': [],
                    'action': 'purge_ignore_keywords'
                }, source='commands')
                
                logger.info(f"User {user_id} purged ignore keywords")
            else:
                await update.message.reply_text(get_text("ignore_cleared_none", language))
                
        except Exception as e:
            logger.error(f"Error purging ignore keywords: {e}")
            language = await self.data_manager.get_user_language(user_id)
            await update.message.reply_text(get_text("error_occurred", language))
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'purge_ignore_keywords_command',
                'user_id': user_id
            }, source='commands')
    
    async def handle_bot_mention_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages that start with @bot_name from inline queries"""
        if not is_private_chat(update) or not update.message:
            return
        
        message_text = update.message.text
        if not message_text:
            return
        
        try:
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
                        context.args = args_text.split()
                        await self.set_keywords_command(update, context)
                    else:
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
                        
        except Exception as e:
            logger.error(f"Error handling bot mention message: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'commands',
                'error': str(e),
                'operation': 'handle_bot_mention_message'
            }, source='commands')