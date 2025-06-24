"""
User Account Monitor - PRODUCTION VERSION
Integrated with BotConfig and event system for robust operation
"""

import asyncio
import logging
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError,
    FloodWaitError, RPCError, AuthKeyUnregisteredError, UserDeactivatedError
)

from config import BotConfig
from storage.sqlite_manager import SQLiteManager
from events import get_event_bus, EventType, emit_job_received, emit_user_monitor_status
from matching.keywords import KeywordMatcher

logger = logging.getLogger(__name__)

class UserAccountMonitor:
    def __init__(self, config: BotConfig, data_manager: SQLiteManager, bot_instance=None):
        self.config = config
        self.data_manager = data_manager
        self.keyword_matcher = KeywordMatcher()
        self.bot_instance = bot_instance
        self.event_bus = get_event_bus()
        
        # Connection management
        self.client = None
        self.monitored_entities = {}
        self.enabled = False
        self._connected = False
        self._keep_alive_task = None
        self._reconnect_attempts = 0
        self._shutdown_event = None
        
        # Authentication state
        self.auth_phone = None
        self.auth_phone_hash = None
        self.waiting_for_code = False
        self.waiting_for_2fa = False
        self.expected_user_id = None
        self.event_handler_registered = False
        
        # Initialize client if credentials are available
        credentials = self.config.get_user_monitor_credentials()
        if credentials:
            try:
                session_path = f"data/{credentials['session_name']}"
                
                self.client = TelegramClient(
                    session_path, 
                    credentials['api_id'], 
                    credentials['api_hash']
                )
                self.enabled = True
                self.auth_phone = credentials['phone']
                logger.info("✅ User monitor client created successfully")
            except Exception as e:
                logger.error(f"❌ User monitor client creation failed: {e}")
                self.enabled = False
        else:
            logger.info("ℹ️ User monitor disabled (no credentials provided)")
    
    def is_authorized_admin(self, user_id: int):
        """Check if user is authorized admin"""
        return self.config.is_admin(user_id)
    
    def is_connected(self):
        """Check if client is connected"""
        return (self._connected and 
                self.client and 
                self.client.is_connected() and 
                not (self._shutdown_event and self._shutdown_event.is_set()))
    
    async def initialize(self):
        """Initialize the user client"""
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
                    await asyncio.wait_for(
                        self.client.connect(), 
                        timeout=self.config.USER_MONITOR_TIMEOUT
                    )
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
                    me = await asyncio.wait_for(
                        self.client.get_me(), 
                        timeout=self.config.USER_MONITOR_TIMEOUT
                    )
                    self.expected_user_id = me.id
                    logger.info(f"✅ Authorized as: {me.first_name} {me.last_name or ''} (ID: {me.id})")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Timeout getting user info - continuing anyway")
                
                # Initialize database and channels
                await self._init_channels_database_safe()
                await self._update_monitored_entities_safe()
                await self._register_event_handler_safe()
                
                logger.info(f"✅ User monitor initialized for {len(self.monitored_entities)} channels")
                
                # Emit connected event
                await emit_user_monitor_status(
                    "connected", 
                    f"Monitoring {len(self.monitored_entities)} channels"
                )
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize user monitor: {e}")
            await emit_user_monitor_status("error", "Initialization failed", str(e))
            return True  # Don't block bot startup
    
    async def start_monitoring(self):
        """Start monitoring"""
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
            
            # Emit monitoring started event
            channel_count = len(self.monitored_entities)
            await emit_user_monitor_status(
                "connected",
                f"Monitoring {channel_count} channels with keep-alive active"
            )
            
            logger.info(f"✅ User monitor started successfully - monitoring {channel_count} channels")
            
        except Exception as e:
            logger.error(f"❌ Failed to start user monitor: {e}")
            await emit_user_monitor_status("error", "Start monitoring failed", str(e))
    
    async def _keep_alive_loop(self):
        """Keep connection alive"""
        logger.info("🔄 User monitor keep-alive loop started")
        
        while self.enabled and not (self._shutdown_event and self._shutdown_event.is_set()):
            try:
                await asyncio.sleep(self.config.KEEP_ALIVE_INTERVAL)
                
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
                    await asyncio.wait_for(
                        self.client.get_me(), 
                        timeout=self.config.USER_MONITOR_TIMEOUT
                    )
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
        """Attempt to reconnect"""
        if self._reconnect_attempts >= self.config.MAX_RECONNECT_ATTEMPTS:
            logger.error(f"❌ Max reconnection attempts ({self.config.MAX_RECONNECT_ATTEMPTS}) reached")
            await emit_user_monitor_status(
                "disconnected",
                "Max reconnection attempts reached",
                "Use /auth_restart to retry manually"
            )
            return False
        
        self._reconnect_attempts += 1
        logger.info(f"🔄 Attempting reconnection {self._reconnect_attempts}/{self.config.MAX_RECONNECT_ATTEMPTS}...")
        
        try:
            # Disconnect first if partially connected
            if self.client and self.client.is_connected():
                await self.client.disconnect()
                await asyncio.sleep(3)
            
            # Reconnect with timeout
            await asyncio.wait_for(
                self.client.connect(), 
                timeout=self.config.USER_MONITOR_TIMEOUT
            )
            self._connected = True
            
            # Verify authentication
            if await self.client.is_user_authorized():
                # Re-register event handlers
                await self._register_event_handler_safe()
                logger.info(f"✅ User monitor reconnected successfully (attempt {self._reconnect_attempts})")
                
                await emit_user_monitor_status(
                    "connected",
                    f"Reconnected on attempt {self._reconnect_attempts}"
                )
                
                return True
            else:
                logger.error("❌ User monitor reconnected but not authorized")
                await emit_user_monitor_status("auth_required", "Reconnected but needs authentication")
                return False
                
        except Exception as e:
            logger.error(f"❌ Reconnection attempt {self._reconnect_attempts} failed: {e}")
            # Exponential backoff
            delay = min(
                self.config.RECONNECT_DELAY * (self.config.RECONNECT_BACKOFF_MULTIPLIER ** (self._reconnect_attempts - 1)),
                self.config.MAX_RECONNECT_DELAY
            )
            await asyncio.sleep(delay)
            return False
    
    async def _init_channels_database_safe(self):
        """Initialize channels database"""
        try:
            await self.data_manager.init_channels_table()
            
            # Import from config if database is empty
            existing_channels = await self.data_manager.get_simple_user_channels()
            if not existing_channels:
                logger.info("ℹ️ No user channels in database - will use channels as configured")
        except Exception as e:
            logger.error(f"❌ Error initializing channels database: {e}")
    
    async def _register_event_handler_safe(self):
        """Register event handler"""
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
        """Start authentication"""
        try:
            logger.info(f"🔐 Starting authentication for {self.auth_phone}")
            
            result = await asyncio.wait_for(
                self.client.send_code_request(self.auth_phone),
                timeout=self.config.AUTH_TIMEOUT
            )
            
            self.auth_phone_hash = result.phone_code_hash
            self.waiting_for_code = True
            
            logger.info(f"✅ Authentication code sent to {self.auth_phone}")
            
            await emit_user_monitor_status(
                "auth_required",
                f"SMS code sent to {self.auth_phone}",
                "Send verification code to chat"
            )
                    
        except asyncio.TimeoutError:
            logger.error("❌ Authentication timeout - failed to send SMS code")
            await emit_user_monitor_status("error", "Authentication timeout", "Failed to send SMS code")
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            await emit_user_monitor_status("error", "Authentication error", str(e))
    
    async def handle_auth_message(self, user_id: int, message_text: str):
        """Handle authentication messages"""
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
                        timeout=self.config.AUTH_TIMEOUT
                    )
                    
                    self.waiting_for_code = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message_safe(
                        user_id, 
                        f"🎉 **Authentication Successful!**\n\n"
                        f"👤 Authenticated as: {result.first_name} {result.last_name or ''}\n"
                        f"🎯 User account monitoring is now active!"
                    )
                    
                    logger.info(f"✅ User authentication successful")
                    await emit_user_monitor_status("auth_success", "Authentication completed successfully")
                    await self._complete_initialization_safe()
                    return True
                    
                except SessionPasswordNeededError:
                    self.waiting_for_code = False
                    self.waiting_for_2fa = True
                    await self._send_auth_message_safe(user_id, "🔐 **Two-Factor Authentication Required**\n\nPlease send your 2FA password:")
                    return True
                    
                except Exception as e:
                    await self._send_auth_message_safe(user_id, f"❌ **Authentication Error**\n\n{str(e)}")
                    await emit_user_monitor_status("error", "Authentication failed", str(e))
                    return True
                    
            elif self.waiting_for_2fa:
                password = message_text.strip()
                
                try:
                    result = await asyncio.wait_for(
                        self.client.sign_in(password=password),
                        timeout=self.config.AUTH_TIMEOUT
                    )
                    
                    self.waiting_for_2fa = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message_safe(
                        user_id,
                        f"🎉 **2FA Authentication Successful!**\n\n"
                        f"👤 Authenticated as: {result.first_name} {result.last_name or ''}\n"
                        f"🎯 User account monitoring is now active!"
                    )
                    
                    logger.info(f"✅ User 2FA authentication successful")
                    await emit_user_monitor_status("auth_success", "2FA authentication completed successfully")
                    await self._complete_initialization_safe()
                    return True
                    
                except Exception as e:
                    await self._send_auth_message_safe(user_id, f"❌ **Invalid 2FA Password**\n\n{str(e)}\n\nPlease try again:")
                    return True
            
        except Exception as e:
            logger.error(f"❌ Authentication error: {e}")
            await self._send_auth_message_safe(user_id, f"❌ **Authentication Error**\n\n{str(e)}")
            await emit_user_monitor_status("error", "Authentication handler error", str(e))
            return True
        
        return False
    
    async def _complete_initialization_safe(self):
        """Complete initialization after authentication"""
        try:
            await self._init_channels_database_safe()
            await self._update_monitored_entities_safe()
            await self._register_event_handler_safe()
            
            channel_count = len(self.monitored_entities)
            await emit_user_monitor_status(
                "connected",
                f"Setup complete - monitoring {channel_count} channels"
            )
            
            logger.info(f"✅ User monitor setup completed - monitoring {channel_count} channels")
            
        except Exception as e:
            logger.error(f"❌ Failed to complete initialization: {e}")
            await emit_user_monitor_status("error", "Setup completion failed", str(e))
    
    async def _send_auth_message_safe(self, user_id: int, message: str):
        """Send authentication message"""
        if self.bot_instance:
            try:
                await asyncio.wait_for(
                    self.bot_instance.send_message(
                        chat_id=user_id, 
                        text=message,
                        parse_mode='Markdown'
                    ),
                    timeout=self.config.TELEGRAM_API_TIMEOUT
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
        """Restart authentication"""
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
        """Update monitored entities"""
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
                        timeout=self.config.CHANNEL_VALIDATION_TIMEOUT
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
            
            # Emit channel validation events
            if invalid_channels:
                await self.event_bus.emit(EventType.CHANNEL_ACCESS_LOST, {
                    'invalid_channels': invalid_channels,
                    'valid_channels': len(valid_channels),
                    'cleaned_up': True
                }, source='user_monitor')
            
            if valid_channels:
                logger.info(f"✅ All {len(valid_channels)} user channels loaded successfully")
                await self.event_bus.emit(EventType.CHANNEL_VALIDATED, {
                    'channel_count': len(valid_channels),
                    'monitor_type': 'user'
                }, source='user_monitor')
            else:
                logger.info(f"ℹ️ No valid user channels found")
                
        except Exception as e:
            logger.error(f"❌ Error updating monitored entities: {e}")
            self.monitored_entities = {}
            await emit_user_monitor_status("error", "Failed to update monitored channels", str(e))
    
    async def update_monitored_entities(self):
        """Public method to update monitored entities"""
        await self._update_monitored_entities_safe()
    
    async def process_channel_message(self, event):
        """Process new message from channels"""
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
            
            # Generate correlation ID
            correlation_id = f"user_monitor_{chat_id}_{event.message.id}_{datetime.now().timestamp()}"
            
            # Emit job received event
            await emit_job_received(
                message_text=message_text,
                channel_id=chat_id,
                message_id=event.message.id,
                source='user_monitor',
                correlation_id=correlation_id
            )
                
        except Exception as e:
            logger.error(f"❌ Error in process_channel_message: {e}")
            await self.event_bus.emit(EventType.USER_MONITOR_ERROR, {
                'error': str(e),
                'operation': 'process_channel_message',
                'chat_id': getattr(event, 'chat_id', 'unknown')
            }, source='user_monitor')
    
    async def stop(self):
        """Stop the user monitor gracefully"""
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
                await asyncio.wait_for(
                    self.client.disconnect(), 
                    timeout=self.config.USER_MONITOR_TIMEOUT
                )
                self._connected = False
            
            logger.info("✅ User monitor stopped successfully")
            await emit_user_monitor_status("disconnected", "User monitor stopped gracefully")
            
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
                timeout=self.config.CHANNEL_VALIDATION_TIMEOUT
            )
            
            # Add to database
            username = f"@{entity.username}" if hasattr(entity, 'username') and entity.username else None
            success = await self.data_manager.add_channel_simple(entity.id, username, 'user')
            
            if success:
                # Update monitored entities
                await self._update_monitored_entities_safe()
                
                # Emit channel added event
                await self.event_bus.emit(EventType.CHANNEL_ADDED, {
                    'channel_id': entity.id,
                    'username': username,
                    'type': 'user',
                    'source': 'user_monitor'
                }, source='user_monitor')
                
                return True, f"Channel added successfully: {username or entity.id}"
            else:
                return False, "Channel already exists"
                
        except asyncio.TimeoutError:
            return False, "Timeout accessing channel"
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
                
                # Emit channel removed event
                await self.event_bus.emit(EventType.CHANNEL_REMOVED, {
                    'channel_id': chat_id,
                    'type': 'user',
                    'source': 'user_monitor'
                }, source='user_monitor')
                
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
    
    # Health and monitoring methods
    async def get_monitor_stats(self) -> dict:
        """Get user monitor statistics"""
        try:
            return {
                'enabled': self.enabled,
                'connected': self.is_connected(),
                'auth_status': self.get_auth_status(),
                'monitored_channels': len(self.monitored_entities),
                'reconnect_attempts': self._reconnect_attempts,
                'max_reconnect_attempts': self.config.MAX_RECONNECT_ATTEMPTS,
                'keep_alive_running': self._keep_alive_task and not self._keep_alive_task.done(),
                'expected_user_id': self.expected_user_id
            }
        except Exception as e:
            logger.error(f"Error getting monitor stats: {e}")
            return {
                'enabled': self.enabled,
                'error': str(e)
            }
    
    async def health_check(self) -> dict:
        """Perform health check and return status"""
        try:
            health = {
                'status': 'healthy',
                'issues': []
            }
            
            if not self.enabled:
                health['status'] = 'disabled'
                health['issues'].append('User monitor not enabled')
                return health
            
            if not self.is_connected():
                health['status'] = 'unhealthy'
                health['issues'].append('Not connected to Telegram')
            
            if self.get_auth_status() != 'authenticated':
                health['status'] = 'degraded'
                health['issues'].append(f"Authentication status: {self.get_auth_status()}")
            
            if self._reconnect_attempts >= self.config.MAX_RECONNECT_ATTEMPTS:
                health['status'] = 'critical'
                health['issues'].append('Max reconnection attempts reached')
            
            if not self.monitored_entities:
                health['status'] = 'degraded'
                health['issues'].append('No channels being monitored')
            
            return health
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return {
                'status': 'error',
                'issues': [f'Health check failed: {str(e)}']
            }