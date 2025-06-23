"""
Message Handlers - WORKING VERSION - Channel processing only
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
        logger.info("MessageHandlers initialized")
    
    def register(self, app):
        """Register message handlers - SAFE VERSION"""
        # ONLY handle channel/group messages (never private)
        # Use specific chat type filters to be absolutely sure
        app.add_handler(MessageHandler(
            filters.TEXT & 
            ~filters.COMMAND & 
            (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP | filters.ChatType.CHANNEL),
            self.handle_channel_message
        ))
        
        logger.info("Message handlers registered (channels/groups only)")
    
    async def handle_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages from monitored channels"""
        message = update.message
        if not message or not message.text:
            return
        
        # Safety check - should never be private due to filters
        if message.chat.type == 'private':
            logger.warning("❌ Private message in channel handler - this shouldn't happen!")
            return
        
        chat_id = message.chat.id
        channel_username = message.chat.username
        
        # Check if this channel is monitored
        if not self.config_manager.is_monitored_channel(chat_id, channel_username):
            return
        
        channel_display = f"@{channel_username}" if channel_username else str(chat_id)
        logger.info(f"📨 Processing message from channel: {channel_display}")
        
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
                await context.bot.forward_message(
                    chat_id=user_chat_id,
                    from_chat_id=chat_id,
                    message_id=message.message_id
                )
                
                forwarded_count += 1
                logger.info(f"✅ Forwarded job to user {user_chat_id}")
                await asyncio.sleep(0.5)  # Rate limiting
                
            except TelegramError as e:
                logger.error(f"❌ Failed to forward to user {user_chat_id}: {e}")
        
        if forwarded_count > 0:
            logger.info(f"📊 Forwarded message to {forwarded_count} users")
    
    async def collect_and_repost_jobs(self, bot):
        """Manual job collection function for scheduled runs"""
        logger.info("Starting manual job collection...")
        
        channels = self.config_manager.get_channels_to_monitor()
        if not channels:
            logger.info("No channels configured for monitoring")
            return
        
        all_users = await self.data_manager.get_all_users_with_keywords()
        if not all_users:
            logger.info("No users with keywords found")
            return
        
        since_time = datetime.now() - timedelta(hours=12)
        total_forwarded = 0
        
        for channel in channels:
            try:
                logger.info(f"📋 Checking channel: {channel}")
                
                messages = []
                async for message in bot.get_chat_history(chat_id=channel, limit=50):
                    if message.date > since_time and message.text:
                        messages.append(message)
                
                logger.info(f"Found {len(messages)} recent messages in {channel}")
                
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
                            
                            total_forwarded += 1
                            logger.info(f"✅ Manual forward to user {user_chat_id}")
                            await asyncio.sleep(0.5)
                            
                        except TelegramError as e:
                            logger.error(f"❌ Failed to forward to user {user_chat_id}: {e}")
            
            except Exception as e:
                logger.error(f"❌ Error processing channel {channel}: {e}")
        
        logger.info(f"✅ Manual job collection completed - {total_forwarded} messages forwarded")