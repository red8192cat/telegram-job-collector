"""
Message Handlers - Channel message processing and job forwarding
"""

import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

from storage.sqlite_manager import SQLiteManager
from utils.config import ConfigManager
from matching.keywords import KeywordMatcher

logger = logging.getLogger(__name__)

class MessageHandlers:
    def __init__(self, data_manager: SQLiteManager, config_manager: ConfigManager):
        self.data_manager = data_manager
        self.config_manager = config_manager
        self.keyword_matcher = KeywordMatcher()
    
    def register(self, app):
        # Authentication message handler (highest priority)
        app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, self.handle_potential_auth_message), group=0)
        """Register message handlers"""
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_channel_message))
        logger.info("Message handlers registered")
    
    async def handle_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages from monitored channels"""
        message = update.message
        if not message or not message.text:
            return
        
        if message.chat.type == 'private':
            return
        
        chat_id = message.chat.id
        channel_username = message.chat.username
        
        if not self.config_manager.is_monitored_channel(chat_id, channel_username):
            return
        
        channel_display = f"@{channel_username}" if channel_username else str(chat_id)
        logger.info(f"Processing message from channel: {channel_display}")
        
        all_users = await self.data_manager.get_all_users_with_keywords()
        
        for user_chat_id, keywords in all_users.items():
            if user_chat_id <= 0 or user_chat_id == chat_id:
                continue
            
            if not await self.data_manager.check_user_limit(user_chat_id):
                continue
            
            if not self.keyword_matcher.matches_user_keywords(message.text, keywords):
                continue
            
            ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_chat_id)
            if self.keyword_matcher.matches_ignore_keywords(message.text, ignore_keywords):
                continue
            
            try:
                await context.bot.forward_message(
                    chat_id=user_chat_id,
                    from_chat_id=chat_id,
                    message_id=message.message_id
                )
                
                logger.info(f"Forwarded job to private user {user_chat_id}")
                await asyncio.sleep(0.5)
                
            except TelegramError as e:
                logger.error(f"Failed to forward to user {user_chat_id}: {e}")
    
    async def collect_and_repost_jobs(self, bot):
        """Manual job collection function for scheduled runs"""
        logger.info("Starting manual job collection...")
        
        channels = self.config_manager.get_channels_to_monitor()
        if not channels:
            return
        
        all_users = await self.data_manager.get_all_users_with_keywords()
        if not all_users:
            return
        
        since_time = datetime.now() - timedelta(hours=12)
        
        for channel in channels:
            try:
                logger.info(f"Checking channel: {channel}")
                
                messages = []
                async for message in bot.get_chat_history(chat_id=channel, limit=50):
                    if message.date > since_time and message.text:
                        messages.append(message)
                
                for message in messages:
                    for user_chat_id, keywords in all_users.items():
                        if user_chat_id <= 0:
                            continue
                        
                        if not await self.data_manager.check_user_limit(user_chat_id):
                            continue
                        
                        if not self.keyword_matcher.matches_user_keywords(message.text, keywords):
                            continue
                        
                        ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_chat_id)
                        if self.keyword_matcher.matches_ignore_keywords(message.text, ignore_keywords):
                            continue
                        
                        try:
                            await bot.forward_message(
                                chat_id=user_chat_id,
                                from_chat_id=channel,
                                message_id=message.message_id
                            )
                            
                            logger.info(f"Forwarded job to private user {user_chat_id}")
                            await asyncio.sleep(0.5)
                            
                        except TelegramError as e:
                            logger.error(f"Failed to forward to user {user_chat_id}: {e}")
            
            except Exception as e:
                logger.error(f"Error processing channel {channel}: {e}")
        
        logger.info("Manual job collection completed")

    async def handle_auth_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle potential authentication messages"""
        if not update.message or not update.message.text or update.message.chat.type != 'private':
            return False
        
        user_monitor = getattr(context.bot_data, 'user_monitor', None)
        if not user_monitor or not user_monitor.is_waiting_for_auth():
            return False
        
        user_id = update.effective_user.id
        message_text = update.message.text
        
        # Handle authentication message
        handled = await user_monitor.handle_auth_message(user_id, message_text)
        return handled

    async def handle_potential_auth_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle potential authentication messages first"""
        # Try auth message handling first
        auth_handled = await self.handle_auth_message(update, context)
        if auth_handled:
            return  # Stop processing if it was an auth message
        
        # Continue with normal private message handling if needed
        pass
