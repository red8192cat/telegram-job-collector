"""
OPTIONAL User Account Monitor - Extends monitoring capabilities
Only runs if API credentials are provided, otherwise gracefully disabled
"""

import asyncio
import logging
import os
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat

from storage.sqlite_manager import SQLiteManager
from matching.keywords import KeywordMatcher
from utils.config import ConfigManager

logger = logging.getLogger(__name__)

class UserAccountMonitor:
    def __init__(self, data_manager: SQLiteManager, config_manager: ConfigManager, bot_instance=None):
        self.data_manager = data_manager
        self.config_manager = config_manager
        self.keyword_matcher = KeywordMatcher()
        self.bot_instance = bot_instance
        self.client = None
        self.monitored_entities = {}
        self.enabled = False
        
        # Only initialize if credentials are available
        if self._has_credentials():
            try:
                api_id = int(os.getenv('API_ID'))
                api_hash = os.getenv('API_HASH')
                session_name = os.getenv('SESSION_NAME', 'user_monitor')
                
                self.client = TelegramClient(f'data/{session_name}', api_id, api_hash)
                self.enabled = True
                logger.info("User account monitor initialized (credentials found)")
            except Exception as e:
                logger.warning(f"User monitor initialization failed: {e}")
                self.enabled = False
        else:
            logger.info("User account monitor disabled (no credentials provided)")
    
    def _has_credentials(self):
        """Check if user account credentials are provided"""
        return all([
            os.getenv('API_ID'),
            os.getenv('API_HASH'),
            os.getenv('PHONE_NUMBER')
        ])
    
    async def initialize(self):
        """Initialize the user client and set up monitoring (only if enabled)"""
        if not self.enabled or not self.client:
            logger.info("User monitor not enabled - skipping initialization")
            return False
        
        try:
            await self.client.start(phone=os.getenv('PHONE_NUMBER'))
            logger.info("User account client started successfully")
            
            # Get monitoring entities for USER-monitored channels only
            await self.update_monitored_entities()
            
            # Set up message handler
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                await self.process_channel_message(event)
            
            logger.info(f"User monitor active for {len(self.monitored_entities)} additional channels")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize user monitor: {e}")
            self.enabled = False
            return False
    
    async def update_monitored_entities(self):
        """Update the list of entities to monitor (USER channels only)"""
        if not self.enabled:
            return
            
        # Get ONLY user-monitored channels (not the bot channels)
        channels = self.config_manager.get_user_monitored_channels()
        self.monitored_entities = {}
        
        if not channels:
            logger.info("No user-monitored channels configured")
            return
        
        for channel_identifier in channels:
            try:
                if channel_identifier.startswith('@'):
                    entity = await self.client.get_entity(channel_identifier)
                elif channel_identifier.startswith('-'):
                    entity = await self.client.get_entity(int(channel_identifier))
                else:
                    # Try as username first, then as ID
                    try:
                        entity = await self.client.get_entity(channel_identifier)
                    except:
                        entity = await self.client.get_entity(int(channel_identifier))
                
                self.monitored_entities[entity.id] = {
                    'entity': entity,
                    'identifier': channel_identifier
                }
                logger.info(f"User monitor added: {channel_identifier}")
                
            except Exception as e:
                logger.error(f"Failed to get entity for {channel_identifier}: {e}")
    
    async def process_channel_message(self, event):
        """Process new message from user-monitored channels"""
        if not self.enabled or not event.message or not event.message.text:
            return
        
        chat_id = event.chat_id
        if chat_id not in self.monitored_entities:
            return
        
        # Get channel info
        channel_info = self.monitored_entities[chat_id]
        logger.info(f"Processing user-monitored message from: {channel_info['identifier']}")
        
        message_text = event.message.text
        
        # Get all users with keywords
        all_users = await self.data_manager.get_all_users_with_keywords()
        
        forwarded_count = 0
        for user_chat_id, keywords in all_users.items():
            if user_chat_id <= 0:
                continue
            
            # Check user limits
            if not await self.data_manager.check_user_limit(user_chat_id):
                continue
            
            # Check keyword matching
            if not self.keyword_matcher.matches_user_keywords(message_text, keywords):
                continue
            
            # Check ignore keywords
            ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_chat_id)
            if self.keyword_matcher.matches_ignore_keywords(message_text, ignore_keywords):
                continue
            
            # Forward message using the bot
            if self.bot_instance:
                try:
                    await self.forward_message_via_bot(user_chat_id, event.message, chat_id)
                    forwarded_count += 1
                    await asyncio.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logger.error(f"Failed to forward to user {user_chat_id}: {e}")
        
        if forwarded_count > 0:
            logger.info(f"User monitor forwarded message to {forwarded_count} users")
    
    async def forward_message_via_bot(self, user_chat_id, message, source_chat_id):
        """Forward message to user via bot"""
        if not self.bot_instance:
            return
        
        try:
            # Create a nice formatted message
            source_info = self.monitored_entities.get(source_chat_id, {})
            source_name = source_info.get('identifier', 'Unknown Channel')
            
            formatted_message = f"📋 Job from {source_name}:\n\n{message.text}"
            
            await self.bot_instance.send_message(
                chat_id=user_chat_id,
                text=formatted_message
            )
            
            # Log the forward
            await self.data_manager.log_message_forward(
                user_chat_id, source_chat_id, message.id
            )
            
        except Exception as e:
            logger.error(f"Error forwarding via bot: {e}")
            raise
    
    async def run_forever(self):
        """Keep the client running (only if enabled)"""
        if not self.enabled or not self.client:
            logger.info("User monitor not running (disabled)")
            return
            
        logger.info("User monitor running...")
        try:
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"User monitor disconnected: {e}")
            self.enabled = False
    
    async def stop(self):
        """Stop the client"""
        if self.client:
            await self.client.disconnect()
            logger.info("User account monitor stopped")
