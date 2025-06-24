"""
User Account Monitor - ROBUST VERSION
FIXES: Event loop compatibility, better error handling, production-ready
"""

import asyncio
import logging
import os
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError,
    FloodWaitError, RPCError, AuthKeyUnregisteredError, UserDeactivatedError
)

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
        
        # Connection management - ROBUST
        self._connected = False
        self._keep_alive_task = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._shutdown_event = None  # Will be created when needed
        
        # Authentication state - ROBUST
        self.auth_phone = None
        self.auth_phone_hash = None
        self.waiting_for_code = False
        self.waiting_for_2fa = False
        self.expected_user_id = None
        self.event_handler_registered = False
        
        # Configuration - ROBUST
        self.operation_timeout = 15
        self.keep_alive_interval = 600  # 10 minutes
        self.reconnect_delay = 30
        
        # SECURITY: Get authorized admin ID
        self.authorized_admin_id = None
        admin_id_str = os.getenv('AUTHORIZED_ADMIN_ID')
        if admin_id_str and admin_id_str.isdigit():
            self.authorized_admin_id = int(admin_id_str)
            logger.info(f"User Monitor: Authorized admin ID: {self.authorized_admin_id}")
        
        # Initialize client if credentials are available
        if self._has_credentials():
            try:
                api_id = int(os.getenv('API_ID'))
                api_hash = os.getenv('API_HASH')
                session_name = os.getenv('SESSION_NAME', 'user_monitor')
                
                # Use absolute path for session file
                session_path = os.path.abspath(f'data/{session_name}')
                
                self.client = TelegramClient(session_path, api_id, api_hash)
                self.enabled = True
                self.auth_phone = os.getenv('PHONE_NUMBER')
                logger.info("✅ User monitor client created successfully")
            except Exception as e:
                logger.error(f"❌ User monitor client creation failed: {e}")
                self.enabled = False
        else:
            logger.info("ℹ️ User monitor disabled (no credentials provided)")
    
    def _has_credentials(self):
        """Check if user account credentials are provided"""
        required_vars = ['API_ID', 'API_HASH', 'PHONE_NUMBER']
        return all(os.getenv(var) for var in required_vars)
    
    def is_authorized_admin(self, user_id: int):
        """Check if user is authorized admin"""
        if not self.authorized_admin_id:
            return True  # Allow during initial setup
        return user_id == self.authorized_admin_id
    
    def is_connected(self):
        """Check if client is connected"""
        return (self._connected and 
                self.client and 
                self.client.is_connected() and 
                not (self._shutdown_event and self._shutdown_event.is_set()))
    
    async def initialize(self):
        """Initialize the user client - ROBUST VERSION"""
        if not self.enabled or not self.client:
            logger.info("ℹ️ User monitor not enabled - skipping initialization")
            return True
        
        try:
            # Create shutdown event if not exists
            if not self._shutdown_event:
                self._shutdown_event = asyncio.Event()
            
            logger.info("🔄 Connecting user monitor client...")
            
            # Connect with timeout and retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await asyncio.wait_for(self.client.connect(), timeout=20)
                    self._connected = True
                    logger.info("✅ User monitor client connected")
                    break
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ Connection timeout (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                    else:
                        raise
                except Exception as e:
                    logger.error(f"❌ Connection error (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                    else:
                        raise
            
            # Check authorization
            if not await self.client.is_user_authorized():
                logger.info("🔐 User account not authorized - starting authentication")
                await self._start_auth_process()
                return False  # Authentication needed
            else:
                logger.info("✅ User account already authorized")
                
                # Get user info with timeout
                try:
                    me = await asyncio.wait_for(self.client.get_me(), timeout=10)
                    self.expected_user_id = me.id
                    logger.info(f"✅ Authorized as: {me.first_name} {me.last_name or ''} (ID: {me.id})")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Timeout getting user info - continuing anyway")
                
                # Initialize database and channels
                await self._init_channels_database_safe()
                await self._update_monitored_entities_safe()
                await self._register_event_handler_safe()
                
                logger.info(f"✅ User monitor initialized for {len(self.monitored_entities)} channels")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize user monitor: {e}")
            await self._notify_admin_safe(f"❌ **User Monitor Init Failed**\n\nError: {str(e)}")
            return True  # Don't block bot startup
    
    async def start_monitoring(self):
        """Start monitoring - ROBUST VERSION"""
        if not self.enabled or not self.client:
            logger.info("ℹ️ User monitor not enabled - no monitoring started")
            return
        
        try:
            # Ensure connected
            if not self.is_connected():
                success = await self.reconnect()
                if not success:
                    logger.error("❌ Cannot start monitoring - connection failed")
                    return
            
            # Start keep-alive task
            if not self._keep_alive_task or self._keep_alive_task.done():
                self._keep_alive_task = asyncio.create_task(self._keep_alive_loop())
                logger.info("🔄 User monitor keep-alive started")
            
            # Notify admin of successful start
            channel_count = len(self.monitored_entities)
            await self._notify_admin_safe(
                f"✅ **User Monitor Started**\n\n"
                f"📊 Monitoring {channel_count} channels\n"
                f"🔄 Keep-alive active\n"
                f"🎯 Ready for real-time forwarding\n\n"
                f"The bot can now monitor channels where it's not admin!"
            )
            
            logger.info(f"✅ User monitor started successfully - monitoring {channel_count} channels")
            
        except Exception as e:
            logger.error(f"❌ Failed to start user monitor: {e}")
            await self._notify_admin_safe(f"❌ **User Monitor Start Failed**\n\nError: {str(e)}")
    
    async def _keep_alive_loop(self):
        """Keep connection alive - ROBUST VERSION"""
        logger.info("🔄 User monitor keep-alive loop started")
        
        while self.enabled and not (self._shutdown_event and self._shutdown_event.is_set()):
            try:
                await asyncio.sleep(self.keep_alive_interval)
                
                if self._shutdown_event and self._shutdown_event.is_set():
                    break
                
                # Check connection health
                if not self.is_connected():
                    logger.warning("⚠️ User monitor disconnected, attempting reconnect...")
                    success = await self.reconnect()
                    if not success:
                        logger.error("❌ Keep-alive reconnection failed")
                        continue
                
                # Health ping with timeout
                try:
                    await asyncio.wait_for(self.client.get_me(), timeout=10)
                    logger.debug("✅ User monitor keep-alive ping successful")
                    # Reset reconnect attempts on successful ping
                    self._reconnect_attempts = 0
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Keep-alive ping timeout")
                    self._connected = False
                except Exception as e:
                    logger.warning(f"⚠️ Keep-alive ping failed: {e}")
                    self._connected = False
                
            except asyncio.CancelledError:
                logger.info("🛑 Keep-alive loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in keep-alive loop: {e}")
                # Brief pause before continuing
                await asyncio.sleep(60)
        
        logger.info("🛑 Keep-alive loop stopped")
    
    async def reconnect(self):
        """Attempt to reconnect - ROBUST VERSION"""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(f"❌ Max reconnection attempts ({self._max_reconnect_attempts}) reached")
            await self._notify_admin_safe(
                "❌ **User Monitor Disconnected**\n\n"
                "Max reconnection attempts reached.\n"
                "Use `/auth_restart` to retry manually."
            )
            return False
        
        self._reconnect_attempts += 1
        logger.info(f"🔄 Attempting reconnection {self._reconnect_attempts}/{self._max_reconnect_attempts}...")
        
        try:
            # Disconnect first if partially connected
            if self.client and self.client.is_connected():
                await self.client.disconnect()
                await asyncio.sleep(3)
            
            # Reconnect with timeout
            await asyncio.wait_for(self.client.connect(), timeout=25)
            self._connected = True
            
            # Verify authentication
            if await self.client.is_user_authorized():
                # Re-register event handlers
                await self._register_event_handler_safe()
                logger.info(f"✅ User monitor reconnected successfully (attempt {self._reconnect_attempts})")
                return True
            else:
                logger.error("❌ User monitor reconnected but not authorized")
                return False
                
        except Exception as e:
            logger.error(f"❌ Reconnection attempt {self._reconnect_attempts} failed: {e}")
            # Exponential backoff
            delay = min(self.reconnect_delay * (2 ** (self._reconnect_attempts - 1)), 300)
            await asyncio.sleep(delay)
            return False
    
    async def _init_channels_database_safe(self):
        """Initialize channels database - ROBUST VERSION"""
        try:
            await self.data_manager.init_channels_table()
            
            # Import from config if database is empty
            existing_channels = await self.data_manager.get_user_monitored_channels_db()
            if not existing_channels:
                config_channels = self.config_manager.get_user_monitored_channels()
                
                if config_channels:
                    valid_channels = []
                    for channel in config_channels:
                        if self._is_valid_channel_entry(channel):
                            valid_channels.append(channel)
                        else:
                            logger.warning(f"⚠️ Skipping invalid channel entry: {channel}")
                    
                    if valid_channels:
                        for channel_id in valid_channels:
                            await self.data_manager.add_channel_simple(channel_id, None, 'user')
                        
                        logger.info(f"✅ Imported {len(valid_channels)} valid channels from config")
                    else:
                        logger.info("ℹ️ No valid channels found in config")
                else:
                    logger.info("ℹ️ No user channels configured")
        except Exception as e:
            logger.error(f"❌ Error initializing channels database: {e}")
    
    def _is_valid_channel_entry(self, channel):
        """Validate if a channel entry is valid"""
        try:
            # Must be a negative number (channel) or large positive (supergroup)
            if isinstance(channel, int):
                return channel < 0 or channel > 1000000000
            elif isinstance(channel, str):
                if channel.startswith('@'):
                    return True
                elif channel.lstrip('-').isdigit():
                    return int(channel) < 0
            return False
        except Exception:
            return False
    
    async def _register_event_handler_safe(self):
        """Register event handler - ROBUST VERSION"""
        if self.event_handler_registered:
            return
        
        try:
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                try:
                    await self.process_channel_message(event)
                except Exception as e:
                    logger.error(f"❌ Error processing channel message: {e}")
            
            self.event_handler_registered = True
            logger.info("✅ Message event handler registered")
            
        except Exception as e:
            logger.error(f"❌ Failed to register event handler: {e}")
    
    async def _start_auth_process(self):
        """Start authentication - ROBUST VERSION"""
        try:
            logger.info(f"🔐 Starting authentication for {self.auth_phone}")
            
            result = await asyncio.wait_for(
                self.client.send_code_request(self.auth_phone),
                timeout=25
            )
            
            self.auth_phone_hash = result.phone_code_hash
            self.waiting_for_code = True
            
            logger.info(f"✅ Authentication code sent to {self.auth_phone}")
            
            await self._notify_admin_safe(
                f"🔐 **User Monitor Authentication Required**\n\n"
                f"📱 SMS code sent to: {self.auth_phone}\n"
                f"📨 **Send the verification code to this chat**\n\n"
                f"**Available commands:**\n"
                f"• `/auth_status` - Check authentication status\n"
                f"• `/auth_restart` - Restart authentication process\n\n"
                f"Just send the code (numbers only) when you receive it."
            )
                    
        except asyncio.TimeoutError:
            logger.error("❌ Authentication timeout - failed to send SMS code")
            await self._notify_admin_safe("❌ **Authentication Timeout**\n\nFailed to send SMS code. Use `/auth_restart` to retry.")
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            await self._notify_admin_safe(f"❌ **Authentication Error**\n\n{str(e)}\n\nUse `/auth_restart` to retry.")
    
    async def _notify_admin_safe(self, message: str):
        """Send notification to admin - ROBUST VERSION"""
        if not self.authorized_admin_id or not self.bot_instance:
            return
        
        try:
            await asyncio.wait_for(
                self.bot_instance.send_message(
                    chat_id=self.authorized_admin_id,
                    text=message,
                    parse_mode='Markdown'
                ),
                timeout=10
            )
        except Exception as e:
            logger.error(f"❌ Failed to notify admin: {e}")
    
    async def handle_auth_message(self, user_id: int, message_text: str):
        """Handle authentication messages - ROBUST VERSION"""
        if not self.is_authorized_admin(user_id):
            return False
        
        try:
            if self.waiting_for_code:
                code = message_text.strip()
                if not code.isdigit() or len(code) < 4:
                    await self._send_auth_message_safe(user_id, "❌ Please send only the numeric verification code (4-6 digits)")
                    return True
                
                try:
                    result = await asyncio.wait_for(
                        self.client.sign_in(phone=self.auth_phone, code=code, phone_code_hash=self.auth_phone_hash),
                        timeout=25
                    )
                    
                    self.waiting_for_code = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message_safe(
                        user_id, 
                        f"🎉 **Authentication Successful!**\n\n"
                        f"👤 Authenticated as: {result.first_name} {result.last_name or ''}\n"
                        f"🎯 User account monitoring is now active!\n\n"
                        f"The bot will now initialize user channels..."
                    )
                    
                    logger.info(f"✅ User authentication successful")
                    await self._complete_initialization_safe()
                    return True
                    
                except SessionPasswordNeededError:
                    self.waiting_for_code = False
                    self.waiting_for_2fa = True
                    await self._send_auth_message_safe(user_id, "🔐 **Two-Factor Authentication Required**\n\nPlease send your 2FA password:")
                    return True
                    
                except Exception as e:
                    await self._send_auth_message_safe(user_id, f"❌ **Authentication Error**\n\n{str(e)}\n\nUse `/auth_restart` to retry.")
                    return True
                    
            elif self.waiting_for_2fa:
                password = message_text.strip()
                
                try:
                    result = await asyncio.wait_for(
                        self.client.sign_in(password=password),
                        timeout=25
                    )
                    
                    self.waiting_for_2fa = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message_safe(
                        user_id,
                        f"🎉 **2FA Authentication Successful!**\n\n"
                        f"👤 Authenticated as: {result.first_name} {result.last_name or ''}\n"
                        f"🎯 User account monitoring is now active!\n\n"
                        f"The bot will now initialize user channels..."
                    )
                    
                    logger.info(f"✅ User 2FA authentication successful")
                    await self._complete_initialization_safe()
                    return True
                    
                except Exception as e:
                    await self._send_auth_message_safe(user_id, f"❌ **Invalid 2FA Password**\n\n{str(e)}\n\nPlease try again:")
                    return True
            
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            await self._send_auth_message_safe(user_id, f"❌ **Authentication Error**\n\n{str(e)}")
            return True
        
        return False
    
    async def _complete_initialization_safe(self):
        """Complete initialization after authentication - ROBUST VERSION"""
        try:
            await self._init_channels_database_safe()
            await self._update_monitored_entities_safe()
            await self._register_event_handler_safe()
            
            channel_count = len(self.monitored_entities)
            await self._notify_admin_safe(
                f"🎉 **User Monitor Setup Complete!**\n\n"
                f"✅ Authentication successful\n"
                f"📊 Monitoring {channel_count} user channels\n"
                f"🔄 Real-time forwarding active\n\n"
                f"**What this enables:**\n"
                f"• Monitor any public channel (even without bot admin)\n"
                f"• Real-time job forwarding from user channels\n"
                f"• Expanded job collection capabilities\n\n"
                f"Use `/admin add_user_channel @channel` to add more channels!"
            )
            
            logger.info(f"✅ User monitor setup completed - monitoring {channel_count} channels")
            
        except Exception as e:
            logger.error(f"❌ Failed to complete initialization: {e}")
            await self._notify_admin_safe(f"❌ **Setup Error**\n\n{str(e)}")
    
    async def _send_auth_message_safe(self, user_id: int, message: str):
        """Send authentication message - ROBUST VERSION"""
        if self.bot_instance:
            try:
                await asyncio.wait_for(
                    self.bot_instance.send_message(
                        chat_id=user_id, 
                        text=message,
                        parse_mode='Markdown'
                    ),
                    timeout=10
                )
            except Exception as e:
                logger.error(f"❌ Failed to send auth message: {e}")
    
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
        elif self.expected_user_id and self.is_connected():
            return "authenticated"
        else:
            return "not_authenticated"
    
    async def restart_auth(self, user_id: int):
        """Restart authentication - ROBUST VERSION"""
        if not self.is_authorized_admin(user_id):
            return False
        
        # Reset authentication state
        self.waiting_for_code = False
        self.waiting_for_2fa = False
        self.auth_phone_hash = None
        
        try:
            await self._start_auth_process()
            return True
        except Exception as e:
            logger.error(f"❌ Failed to restart authentication: {e}")
            return False
    
    async def _update_monitored_entities_safe(self):
        """Update monitored entities - ROBUST VERSION"""
        if not self.enabled or not self.is_connected():
            logger.info("ℹ️ User monitor not connected - skipping entity update")
            return
            
        try:
            user_channels = await self.data_manager.get_simple_user_channels()
            self.monitored_entities = {}
            
            if not user_channels:
                logger.info("ℹ️ No user-monitored channels in database")
                return
            
            valid_channels = []
            invalid_channels = []
            
            for chat_id in user_channels:
                try:
                    # Skip obviously invalid user IDs
                    if 0 < chat_id < 1000000000:
                        logger.warning(f"⚠️ Skipping invalid user ID as channel: {chat_id}")
                        invalid_channels.append(chat_id)
                        await self.data_manager.remove_channel_simple(chat_id, 'user')
                        continue
                    
                    # Get entity with timeout
                    entity = await asyncio.wait_for(
                        self.client.get_entity(chat_id),
                        timeout=20
                    )
                    
                    # Store entity info
                    self.monitored_entities[entity.id] = {
                        'entity': entity,
                        'chat_id': chat_id,
                        'identifier': f"@{entity.username}" if hasattr(entity, 'username') and entity.username else f"Channel {chat_id}"
                    }
                    valid_channels.append(chat_id)
                    
                    display_name = await self.data_manager.get_channel_display_name(chat_id)
                    logger.info(f"✅ User monitor loaded: {display_name}")
                    
                except asyncio.TimeoutError:
                    logger.error(f"❌ Timeout loading user channel {chat_id}")
                    invalid_channels.append(chat_id)
                except Exception as e:
                    logger.error(f"❌ Failed to load user channel {chat_id}: {e}")
                    invalid_channels.append(chat_id)
                    # Clean up invalid entries
                    await self.data_manager.remove_channel_simple(chat_id, 'user')
            
            # Notify about results
            if invalid_channels:
                await self._notify_admin_safe(
                    f"⚠️ **User Channel Loading Issues**\n\n"
                    f"✅ Successfully loaded: {len(valid_channels)}\n"
                    f"❌ Removed invalid entries: {len(invalid_channels)}\n"
                    f"🧹 Database cleaned automatically"
                )
            
            if valid_channels:
                logger.info(f"✅ All {len(valid_channels)} user channels loaded successfully")
            else:
                logger.info(f"ℹ️ No valid user channels found")
                
        except Exception as e:
            logger.error(f"❌ Error updating monitored entities: {e}")
            self.monitored_entities = {}
    
    async def update_monitored_entities(self):
        """Public method to update monitored entities"""
        await self._update_monitored_entities_safe()
    
    async def process_channel_message(self, event):
        """Process new message from channels - ROBUST VERSION"""
        if not self.enabled or not event.message or not event.message.text:
            return
        
        try:
            chat_id = event.chat_id
            
            # Convert chat_id to entity_id for lookup
            entity_id = None
            if chat_id < 0 and str(chat_id).startswith('-100'):
                entity_id = int(str(chat_id)[4:])  # Remove -100 prefix
            else:
                entity_id = abs(chat_id) if chat_id < 0 else chat_id
            
            # Check if monitored
            lookup_id = entity_id if entity_id in self.monitored_entities else chat_id
            if lookup_id not in self.monitored_entities:
                return
            
            channel_info = self.monitored_entities[lookup_id]
            message_text = event.message.text
            
            # Get display name
            display_name = channel_info.get('identifier', f"Channel {chat_id}")
            logger.info(f"📨 User monitor processing message from {display_name}")
            
            # Get users with timeout
            try:
                all_users = await asyncio.wait_for(
                    self.data_manager.get_all_users_with_keywords(), 
                    timeout=15
                )
            except asyncio.TimeoutError:
                logger.warning("⚠️ Timeout getting users for message processing")
                return
            
            forwarded_count = 0
            
            for user_chat_id, keywords in all_users.items():
                if user_chat_id <= 0:
                    continue
                
                try:
                    # Check user limits
                    if not await asyncio.wait_for(
                        self.data_manager.check_user_limit(user_chat_id), 
                        timeout=5
                    ):
                        continue
                    
                    # Check keyword matching
                    if not self.keyword_matcher.matches_user_keywords(message_text, keywords):
                        continue
                    
                    # Check ignore keywords
                    ignore_keywords = await asyncio.wait_for(
                        self.data_manager.get_user_ignore_keywords(user_chat_id),
                        timeout=5
                    )
                    if self.keyword_matcher.matches_ignore_keywords(message_text, ignore_keywords):
                        continue
                    
                    # Forward message via bot
                    if self.bot_instance:
                        try:
                            await asyncio.wait_for(
                                self.forward_message_via_bot(user_chat_id, event.message, chat_id),
                                timeout=15
                            )
                            forwarded_count += 1
                            await asyncio.sleep(0.3)  # Rate limiting
                        except Exception as e:
                            logger.error(f"❌ Failed to forward to user {user_chat_id}: {e}")
                
                except Exception as e:
                    logger.error(f"❌ Error processing user {user_chat_id}: {e}")
                    continue
            
            if forwarded_count > 0:
                logger.info(f"📤 User monitor forwarded message to {forwarded_count} users")
                
        except Exception as e:
            logger.error(f"❌ Error in process_channel_message: {e}")
    
    async def forward_message_via_bot(self, user_chat_id, message, source_chat_id):
        """Forward message via bot - ROBUST VERSION"""
        if not self.bot_instance:
            return
        
        try:
            display_name = await asyncio.wait_for(
                self.data_manager.get_channel_display_name(source_chat_id),
                timeout=5
            )
            
            formatted_message = f"📋 Job from {display_name}:\n\n{message.text}"
            
            await self.bot_instance.send_message(
                chat_id=user_chat_id,
                text=formatted_message
            )
            
            # Log the forward
            await self.data_manager.log_message_forward(
                user_chat_id, source_chat_id, message.id
            )
            
        except Exception as e:
            logger.error(f"❌ Error forwarding via bot: {e}")
            raise
    
    async def stop(self):
        """Stop the user monitor gracefully - ROBUST VERSION"""
        logger.info("🛑 Stopping user monitor...")
        
        try:
            # Signal shutdown
            if self._shutdown_event:
                self._shutdown_event.set()
            self.enabled = False
            
            # Cancel keep-alive task
            if self._keep_alive_task and not self._keep_alive_task.done():
                self._keep_alive_task.cancel()
                try:
                    await asyncio.wait_for(self._keep_alive_task, timeout=5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Disconnect client
            if self.client and self.client.is_connected():
                await asyncio.wait_for(self.client.disconnect(), timeout=10)
                self._connected = False
            
            logger.info("✅ User monitor stopped successfully")
            
        except Exception as e:
            logger.error(f"❌ Error stopping user monitor: {e}")
    
    # Additional helper methods for channel management
    async def add_channel(self, channel_identifier: str):
        """Add new channel to monitoring"""
        try:
            if not self.is_connected():
                return False, "User monitor not connected"
            
            # Try to get entity
            entity = await asyncio.wait_for(
                self.client.get_entity(channel_identifier),
                timeout=20
            )
            
            # Add to database
            username = f"@{entity.username}" if hasattr(entity, 'username') and entity.username else None
            success = await self.data_manager.add_channel_simple(entity.id, username, 'user')
            
            if success:
                # Update monitored entities
                await self._update_monitored_entities_safe()
                return True, f"Channel added successfully: {username or entity.id}"
            else:
                return False, "Channel already exists"
                
        except Exception as e:
            logger.error(f"❌ Error adding channel: {e}")
            return False, f"Error adding channel: {str(e)}"
    
    async def remove_channel(self, chat_id: int):
        """Remove channel from monitoring"""
        try:
            success = await self.data_manager.remove_channel_simple(chat_id, 'user')
            
            if success:
                # Update monitored entities
                await self._update_monitored_entities_safe()
                return True, "Channel removed successfully"
            else:
                return False, "Channel not found"
                
        except Exception as e:
            logger.error(f"❌ Error removing channel: {e}")
            return False, f"Error removing channel: {str(e)}"
    
    async def get_monitored_channels(self):
        """Get list of currently monitored channels"""
        try:
            channels = await self.data_manager.get_simple_user_channels()
            return channels
        except Exception as e:
            logger.error(f"❌ Error getting monitored channels: {e}")
            return []