"""
Message Handlers - PRODUCTION VERSION
Event-driven architecture with BotConfig integration
FIXED: Removed invalid ApplicationContext import
"""

import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

from config import BotConfig
from storage.sqlite_manager import SQLiteManager
from events import get_event_bus, EventType, emit_job_received, emit_job_forwarded
from matching.keywords import KeywordMatcher

logger = logging.getLogger(__name__)

class MessageHandlers:
    def __init__(self, config: BotConfig, data_manager: SQLiteManager):
        self.config = config
        self.data_manager = data_manager
        self.keyword_matcher = KeywordMatcher()
        self.event_bus = get_event_bus()
        
        # Bot instance for forwarding (will be set later)
        self._bot_instance = None
        self._forward_original = True
        
        # Subscribe to job message events
        self.event_bus.subscribe(EventType.JOB_MESSAGE_RECEIVED, self.handle_job_message_event)
        
        logger.info("Message handlers initialized with configuration and event system")
    
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
    
    def set_bot_instance(self, bot_instance):
        """Set bot instance for message forwarding"""
        self._bot_instance = bot_instance
        logger.debug("Bot instance set for message forwarding")
    
    def set_forward_mode(self, forward_original: bool = True):
        """Set whether to forward original messages or send custom formatted messages"""
        self._forward_original = forward_original
    
    async def handle_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages from monitored bot channels"""
        message = update.message
        if not message or not message.text:
            return
        
        # Safety check - should never be private due to filters
        if message.chat.type == 'private':
            logger.warning("Private message in channel handler - this shouldn't happen!")
            return
        
        chat_id = message.chat.id
        
        try:
            # Check if this channel is monitored by bot (using chat_id now)
            bot_channels = await self.data_manager.get_simple_bot_channels()
            if chat_id not in bot_channels:
                logger.debug(f"Message from non-monitored channel: {chat_id}")
                return
            
            # Get display name for the channel
            display_name = await self.data_manager.get_channel_display_name(chat_id)
            logger.info(f"📨 Processing message from bot channel: {display_name}")
            
            # Emit job received event
            correlation_id = f"bot_{chat_id}_{message.message_id}_{datetime.now().timestamp()}"
            await emit_job_received(
                message_text=message.text,
                channel_id=chat_id,
                message_id=message.message_id,
                source='bot_channels',
                correlation_id=correlation_id
            )
            
        except Exception as e:
            logger.error(f"Error handling channel message: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'message_handlers',
                'error': str(e),
                'operation': 'handle_channel_message',
                'chat_id': chat_id
            }, source='message_handlers')
    
    async def handle_job_message_event(self, event):
        """Handle job message received event from any source"""
        try:
            message_text = event.data.get('message_text', '')
            channel_id = event.data.get('channel_id', 0)
            message_id = event.data.get('message_id', 0)
            source = event.source
            correlation_id = event.correlation_id
            
            logger.debug(f"Processing job message from {source} (channel: {channel_id})")
            
            await self.process_job_message(message_text, channel_id, message_id, source, correlation_id)
            
        except Exception as e:
            logger.error(f"Error handling job message event: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'message_handlers',
                'error': str(e),
                'operation': 'handle_job_message_event'
            }, source='message_handlers')
    
    async def process_job_message(self, message_text: str, channel_id: int, message_id: int, 
                                source: str, correlation_id: str = None):
        """Process job message and forward to matching users"""
        try:
            # Get all users with keywords
            all_users = await self.data_manager.get_all_users_with_keywords()
            
            if not all_users:
                logger.debug("No users with keywords found")
                return
            
            forwarded_count = 0
            matched_users = []
            
            for user_chat_id, keywords in all_users.items():
                if user_chat_id <= 0 or user_chat_id == channel_id:
                    continue
                
                try:
                    # Check user limits
                    if not await self.data_manager.check_user_limit(user_chat_id):
                        logger.debug(f"User {user_chat_id} exceeded daily limit")
                        continue
                    
                    # Check if message matches user's keywords
                    if not self.keyword_matcher.matches_user_keywords(message_text, keywords):
                        continue
                    
                    # Check ignore keywords
                    ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_chat_id)
                    if self.keyword_matcher.matches_ignore_keywords(message_text, ignore_keywords):
                        logger.debug(f"Message ignored for user {user_chat_id} due to ignore keywords")
                        continue
                    
                    # Determine which keywords matched (for analytics)
                    matched_keywords = self._get_matched_keywords(message_text, keywords)
                    
                    # Forward the message
                    success = await self._forward_message_to_user(
                        user_chat_id, channel_id, message_id, message_text, source
                    )
                    
                    if success:
                        # Log the forward
                        await self.data_manager.log_message_forward(
                            user_chat_id, channel_id, message_id, matched_keywords
                        )
                        
                        # Emit forwarded event
                        await emit_job_forwarded(
                            user_id=user_chat_id,
                            channel_id=channel_id,
                            message_id=message_id,
                            keywords_matched=matched_keywords,
                            source='message_handlers',
                            correlation_id=correlation_id
                        )
                        
                        forwarded_count += 1
                        matched_users.append(user_chat_id)
                        
                        # Rate limiting
                        await asyncio.sleep(self.config.MESSAGE_FORWARD_DELAY)
                
                except Exception as e:
                    logger.error(f"Error processing user {user_chat_id}: {e}")
                    continue
            
            if forwarded_count > 0:
                display_name = await self.data_manager.get_channel_display_name(channel_id)
                logger.info(f"📤 Forwarded message from {display_name} to {forwarded_count} users")
                
                # Emit job processed event
                await self.event_bus.emit(EventType.JOB_MESSAGE_PROCESSED, {
                    'channel_id': channel_id,
                    'message_id': message_id,
                    'source': source,
                    'users_matched': len(matched_users),
                    'forwards_sent': forwarded_count,
                    'correlation_id': correlation_id
                }, source='message_handlers')
            
        except Exception as e:
            logger.error(f"Error processing job message: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'message_handlers',
                'error': str(e),
                'operation': 'process_job_message',
                'channel_id': channel_id
            }, source='message_handlers')
    
    def _get_matched_keywords(self, message_text: str, user_keywords: list) -> list:
        """Get list of keywords that matched in the message"""
        matched = []
        message_lower = message_text.lower()
        
        for keyword in user_keywords:
            # Simple check - could be enhanced with the full matching logic
            if keyword.startswith('[') and keyword.endswith(']'):
                # Required keyword
                clean_keyword = keyword[1:-1].lower()
                if clean_keyword in message_lower:
                    matched.append(keyword)
            elif '*' in keyword:
                # Wildcard keyword
                base = keyword.replace('*', '').lower()
                if base in message_lower:
                    matched.append(keyword)
            else:
                # Regular keyword
                if keyword.lower() in message_lower:
                    matched.append(keyword)
        
        return matched
    
    async def _forward_message_to_user(self, user_chat_id: int, channel_id: int, 
                                     message_id: int, message_text: str, source: str) -> bool:
        """Forward message to user with error handling - FIXED"""
        try:
            if not self._bot_instance:
                logger.error("Bot instance not available for forwarding")
                return False
            
            # Option 1: Forward original message (preserves all formatting)
            if self._forward_original:
                await asyncio.wait_for(
                    self._bot_instance.forward_message(
                        chat_id=user_chat_id,
                        from_chat_id=channel_id,
                        message_id=message_id
                    ),
                    timeout=self.config.TELEGRAM_API_TIMEOUT
                )
            else:
                # Option 2: Send with custom header
                display_name = await self.data_manager.get_channel_display_name(channel_id)
                formatted_message = f"📋 Job from {display_name}:\n\n{message_text}"
                
                await asyncio.wait_for(
                    self._bot_instance.send_message(
                        chat_id=user_chat_id, 
                        text=formatted_message
                    ),
                    timeout=self.config.TELEGRAM_API_TIMEOUT
                )
            
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout forwarding to user {user_chat_id}")
            return False
        except TelegramError as e:
            logger.error(f"Telegram error forwarding to user {user_chat_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error forwarding to user {user_chat_id}: {e}")
            return False
    
    # Legacy method for backward compatibility
    async def collect_and_repost_jobs(self, bot):
        """Manual job collection function for scheduled runs"""
        logger.info("⚙️ Starting enhanced manual job collection...")
        
        # Set bot instance for this operation
        self.set_bot_instance(bot)
        
        # Get channels using enhanced method
        bot_channels = await self.data_manager.get_simple_bot_channels()
        if not bot_channels:
            logger.info("⚙️ No bot channels configured for monitoring")
            return
        
        all_users = await self.data_manager.get_all_users_with_keywords()
        if not all_users:
            logger.info("⚙️ No users with keywords found")
            return
        
        since_time = datetime.now() - timedelta(hours=12)
        total_forwarded = 0
        
        # Get channel display names for better logging
        channel_info = await self.data_manager.get_all_channels_with_usernames()
        
        for chat_id in bot_channels:
            try:
                display_name = channel_info.get(chat_id, {}).get('display_name', f"Channel {chat_id}")
                logger.info(f"⚙️ Checking channel: {display_name}")
                
                # This would need to be implemented based on your needs
                # For now, just log that we would collect messages
                logger.info(f"⚙️ Would collect recent messages from {display_name}")
                
                # In a real implementation, you'd:
                # 1. Get recent messages from the channel
                # 2. Process each message through process_job_message
                # 3. Count total forwards
                
            except Exception as e:
                display_name = channel_info.get(chat_id, {}).get('display_name', f"Channel {chat_id}")
                logger.error(f"⚙️ Error processing channel {display_name}: {e}")
        
        logger.info(f"⚙️ Enhanced manual job collection completed - {total_forwarded} messages forwarded")
    
    # Event handling for external job sources
    async def handle_external_job_message(self, message_text: str, channel_identifier: str, 
                                        source: str = "external"):
        """Handle job messages from external sources (like user monitor)"""
        try:
            # Generate a correlation ID
            correlation_id = f"{source}_{channel_identifier}_{datetime.now().timestamp()}"
            
            # Emit job received event
            await emit_job_received(
                message_text=message_text,
                channel_id=hash(channel_identifier) % 1000000000,  # Generate consistent ID
                message_id=0,  # External messages don't have telegram message IDs
                source=source,
                correlation_id=correlation_id
            )
            
        except Exception as e:
            logger.error(f"Error handling external job message: {e}")
            await self.event_bus.emit(EventType.SYSTEM_ERROR, {
                'component': 'message_handlers',
                'error': str(e),
                'operation': 'handle_external_job_message',
                'source': source
            }, source='message_handlers')
    
    # Rate limiting and monitoring
    async def get_forwarding_stats(self) -> dict:
        """Get forwarding statistics for monitoring"""
        try:
            stats = await self.data_manager.get_system_stats()
            return {
                'forwards_24h': stats.get('forwards_24h', 0),
                'total_users': stats.get('total_users', 0),
                'active_channels': len(await self.data_manager.get_simple_bot_channels()),
                'message_forward_delay': self.config.MESSAGE_FORWARD_DELAY,
                'max_daily_forwards_per_user': self.config.MAX_DAILY_FORWARDS_PER_USER
            }
        except Exception as e:
            logger.error(f"Error getting forwarding stats: {e}")
            return {}