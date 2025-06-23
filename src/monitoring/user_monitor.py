"""
OPTIONAL User Account Monitor with Telegram Chat Authentication
Allows authentication via direct messages with the bot for security and convenience
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError

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
        
        # Authentication state
        self.auth_phone = None
        self.auth_phone_hash = None
        self.waiting_for_code = False
        self.waiting_for_2fa = False
        self.expected_user_id = None  # User ID that should authenticate
        
        # Only initialize if credentials are available
        if self._has_credentials():
            try:
                api_id = int(os.getenv('API_ID'))
                api_hash = os.getenv('API_HASH')
                session_name = os.getenv('SESSION_NAME', 'user_monitor')
                
                self.client = TelegramClient(f'data/{session_name}', api_id, api_hash)
                self.enabled = True
                self.auth_phone = os.getenv('PHONE_NUMBER')
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
            # Try to connect with existing session
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.info("User account not authorized - starting authentication process")
                await self._start_auth_process()
                return False  # Will be initialized after successful auth
            else:
                logger.info("User account already authorized")
                # Get user info to set expected_user_id
                me = await self.client.get_me()
                self.expected_user_id = me.id
                logger.info(f"Authorized as: {me.first_name} {me.last_name or ''} (ID: {me.id})")
                
                # Continue with normal initialization
                await self.update_monitored_entities()
                
                # Set up message handler
                @self.client.on(events.NewMessage)
                async def handle_new_message(event):
                    await self.process_channel_message(event)
                
                logger.info(f"User monitor active for {len(self.monitored_entities)} additional channels")
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize user monitor: {e}")
            # Try to start auth process
            try:
                await self._start_auth_process()
            except:
                logger.error("Could not start authentication process")
            return False
    
    async def _start_auth_process(self):
        """Start the authentication process"""
        try:
            # Send authentication code
            result = await self.client.send_code_request(self.auth_phone)
            self.auth_phone_hash = result.phone_code_hash
            self.waiting_for_code = True
            
            logger.info(f"Authentication code sent to {self.auth_phone}")
            logger.info("📱 Please send the verification code to the bot via private message")
                    
        except PhoneNumberInvalidError:
            logger.error(f"Invalid phone number: {self.auth_phone}")
        except Exception as e:
            logger.error(f"Failed to start authentication: {e}")
    
    async def handle_auth_message(self, user_id: int, message_text: str):
        """Handle authentication messages from Telegram chat"""
        # If we don't know the expected user ID yet, we need to verify ownership
        if self.expected_user_id is not None and user_id != self.expected_user_id:
            # After initial auth, only accept from the authenticated user
            return False
        
        try:
            if self.waiting_for_code:
                # User sent verification code
                code = message_text.strip()
                if not code.isdigit() or len(code) < 4:
                    await self._send_auth_message(user_id, "❌ Please send only the numeric verification code (e.g., 12345)")
                    return True
                
                try:
                    result = await self.client.sign_in(phone=self.auth_phone, code=code, phone_code_hash=self.auth_phone_hash)
                    
                    # Authentication successful
                    self.waiting_for_code = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message(user_id, "✅ Authentication successful! User account monitoring is now active.")
                    logger.info(f"User authentication successful for {result.first_name} {result.last_name or ''} (ID: {result.id})")
                    
                    # Complete initialization
                    await self._complete_initialization()
                    return True
                    
                except SessionPasswordNeededError:
                    # 2FA is enabled
                    self.waiting_for_code = False
                    self.waiting_for_2fa = True
                    await self._send_auth_message(user_id, "🔐 Two-factor authentication is enabled. Please send your 2FA password:")
                    return True
                    
                except PhoneCodeInvalidError:
                    await self._send_auth_message(user_id, "❌ Invalid verification code. Please try again:")
                    return True
                    
            elif self.waiting_for_2fa:
                # User sent 2FA password
                password = message_text.strip()
                
                try:
                    result = await self.client.sign_in(password=password)
                    
                    # Authentication successful
                    self.waiting_for_2fa = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message(user_id, "✅ Two-factor authentication successful! User account monitoring is now active.")
                    logger.info(f"User 2FA authentication successful for {result.first_name} {result.last_name or ''} (ID: {result.id})")
                    
                    # Complete initialization
                    await self._complete_initialization()
                    return True
                    
                except Exception as e:
                    await self._send_auth_message(user_id, "❌ Invalid 2FA password. Please try again:")
                    return True
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            await self._send_auth_message(user_id, f"❌ Authentication error: {str(e)}")
            return True
        
        return False
    
    async def _complete_initialization(self):
        """Complete initialization after successful authentication"""
        try:
            await self.update_monitored_entities()
            
            # Set up message handler
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                await self.process_channel_message(event)
            
            logger.info(f"✅ User monitor initialization completed - monitoring {len(self.monitored_entities)} additional channels")
            
        except Exception as e:
            logger.error(f"Failed to complete initialization: {e}")
    
    async def _send_auth_message(self, user_id: int, message: str):
        """Send authentication-related message to user"""
        if self.bot_instance:
            try:
                await self.bot_instance.send_message(chat_id=user_id, text=message)
            except Exception as e:
                logger.error(f"Failed to send auth message: {e}")
    
    def is_waiting_for_auth(self):
        """Check if monitor is waiting for authentication"""
        return self.waiting_for_code or self.waiting_for_2fa
    
    def get_auth_status(self):
        """Get current authentication status"""
        if not self.enabled:
            return "disabled"
        elif not self.client:
            return "not_initialized"
        elif self.waiting_for_code:
            return "waiting_for_code"
        elif self.waiting_for_2fa:
            return "waiting_for_2fa"
        elif self.expected_user_id:
            return "authenticated"
        else:
            return "not_authenticated"
    
    async def restart_auth(self, user_id: int):
        """Restart authentication process (for troubleshooting)"""
        if self.expected_user_id and user_id != self.expected_user_id:
            return False
        
        self.waiting_for_code = False
        self.waiting_for_2fa = False
        self.auth_phone_hash = None
        
        await self._start_auth_process()
        await self._send_auth_message(user_id, "🔄 Authentication process restarted. Please check your phone for the verification code.")
        return True
    
    async def update_monitored_entities(self):
        """Update the list of entities to monitor (USER channels only)"""
        if not self.enabled or not await self.client.is_user_authorized():
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
