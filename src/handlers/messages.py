"""
Message Handlers - Enhanced with better channel display names
Uses chat_id for processing and username for display
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
        logger.info("MessageHandlers initialized with enhanced channel support")
    
    def register(self, app):
        """Register message handlers"""
        # ONLY handle channel/group messages (never private)
        app.add_handler(MessageHandler(
            filters.TEXT & 
            ~filters.COMMAND & 
            (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP | filters.ChatType.CHANNEL),
            self.handle_channel_message
        ))
        
        logger.info("Enhanced message handlers registered (channels/groups only)")
    
    async def handle_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages from monitored channels - ENHANCED with display names"""
        message = update.message
        if not message or not message.text:
            return
        
        # Safety check - should never be private due to filters
        if message.chat.type == 'private':
            logger.warning("Private message in channel handler - this shouldn't happen!")
            return
        
        chat_id = message.chat.id
        
        # Check if this channel is monitored by bot (using chat_id now)
        bot_channels = await self.data_manager.get_simple_bot_channels()
        if chat_id not in bot_channels:
            return
        
        # Get display name for the channel (username or fallback)
        display_name = await self.data_manager.get_channel_display_name(chat_id)
        logger.info(f"📨 EVENT: Processing message from: {display_name}")
        
        # Get all users with keywords
        all_users = await self.data_manager.get_all_users_with_keywords()
        
        forwarded_count = 0
        for user_chat_id, keywords in all_users.items():
            if user_chat_id <= 0 or user_chat_id == chat_id:
                continue
            
            # Check user limits
            if not await self.data_manager.check_user_limit(user_chat_id):
                continue
            
            # Check if message matches user's keywords
            if not self.keyword_matcher.matches_user_keywords(message.text, keywords):
                continue
            
            # Check ignore keywords
            ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_chat_id)
            if self.keyword_matcher.matches_ignore_keywords(message.text, ignore_keywords):
                continue
            
            # Forward the message
            try:
                # Option 1: Forward original message (preserves all formatting, recommended)
                await context.bot.forward_message(
                    chat_id=user_chat_id,
                    from_chat_id=chat_id,
                    message_id=message.message_id
                )
                
                # Option 2: Send with custom header (uncomment if you prefer this)
                # formatted_message = f"📋 Job from {display_name}:\n\n{message.text}"
                # await context.bot.send_message(chat_id=user_chat_id, text=formatted_message)
                
                forwarded_count += 1
                await asyncio.sleep(0.5)  # Rate limiting
                
            except TelegramError as e:
                logger.error(f"Failed to forward to user {user_chat_id}: {e}")
        
        if forwarded_count > 0:
            logger.info(f"📤 FORWARD: Bot forwarded message from {display_name} to {forwarded_count} users")
    
    async def collect_and_repost_jobs(self, bot):
        """Manual job collection function for scheduled runs - ENHANCED"""
        logger.info("⚙️ SYSTEM: Starting enhanced manual job collection...")
        
        # Get channels using enhanced method
        bot_channels = await self.data_manager.get_simple_bot_channels()
        if not bot_channels:
            logger.info("⚙️ SYSTEM: No bot channels configured for monitoring")
            return
        
        all_users = await self.data_manager.get_all_users_with_keywords()
        if not all_users:
            logger.info("⚙️ SYSTEM: No users with keywords found")
            return
        
        since_time = datetime.now() - timedelta(hours=12)
        total_forwarded = 0
        
        # Get channel display names for better logging
        channel_info = await self.data_manager.get_all_channels_with_usernames()
        
        for chat_id in bot_channels:
            try:
                display_name = channel_info.get(chat_id, {}).get('display_name', f"Channel {chat_id}")
                logger.info(f"⚙️ SYSTEM: Checking channel: {display_name}")
                
                messages = []
                async for message in bot.get_chat_history(chat_id=chat_id, limit=50):
                    if message.date > since_time and message.text:
                        messages.append(message)
                
                logger.info(f"⚙️ SYSTEM: Found {len(messages)} recent messages in {display_name}")
                
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
                                from_chat_id=chat_id,
                                message_id=message.message_id
                            )
                            
                            total_forwarded += 1
                            await asyncio.sleep(0.5)
                            
                        except TelegramError as e:
                            logger.error(f"Failed to forward to user {user_chat_id}: {e}")
            
            except Exception as e:
                display_name = channel_info.get(chat_id, {}).get('display_name', f"Channel {chat_id}")
                logger.error(f"⚙️ SYSTEM: Error processing channel {display_name}: {e}")
        
        logger.info(f"⚙️ SYSTEM: Enhanced manual job collection completed - {total_forwarded} messages forwarded")