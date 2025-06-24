"""
User Account Monitor with Enhanced Database Compatibility and Robust Error Handling
IMPROVED VERSION - Better error handling, timeout management, and graceful degradation
"""

import asyncio
import logging
import os
import json
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
        
        # Authentication state
        self.auth_phone = None
        self.auth_phone_hash = None
        self.waiting_for_code = False
        self.waiting_for_2fa = False
        self.expected_user_id = None
        self.event_handler_registered = False
        
        # Error handling and timeouts
        self.max_retries = 3
        self.operation_timeout = 30  # seconds
        self.startup_timeout = 60   # seconds for full initialization
        
        # SECURITY: Get authorized admin ID
        self.authorized_admin_id = None
        admin_id_str = os.getenv('AUTHORIZED_ADMIN_ID')
        if admin_id_str and admin_id_str.isdigit():
            self.authorized_admin_id = int(admin_id_str)
            logger.info(f"Authorized admin ID: {self.authorized_admin_id}")
        
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
    
    def is_authorized_admin(self, user_id: int):
        """Check if user is authorized admin"""
        if not self.authorized_admin_id:
            return True  # Allow during initial setup
        return user_id == self.authorized_admin_id
    
    async def initialize(self):
        """Initialize the user client with robust error handling and timeouts"""
        if not self.enabled or not self.client:
            logger.info("User monitor not enabled - skipping initialization")
            return True  # Return True to not block bot startup
        
        try:
            # Use timeout for entire initialization
            return await asyncio.wait_for(
                self._initialize_with_timeout(), 
                timeout=self.startup_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"User monitor initialization timed out after {self.startup_timeout}s")
            await self._notify_admin_safe("⚠️ **User Monitor Timeout**\n\nInitialization timed out. Bot continues with core functionality only.")
            return True  # Don't block bot startup
        except Exception as e:
            logger.error(f"Unexpected error in user monitor initialization: {e}")
            await self._notify_admin_safe(f"❌ **User Monitor Error**\n\nUnexpected error: {str(e)}")
            return True  # Don't block bot startup
    
    async def _initialize_with_timeout(self):
        """Internal initialization with proper error handling"""
        try:
            logger.info("Starting user monitor initialization...")
            
            # Connect with timeout
            await asyncio.wait_for(self.client.connect(), timeout=10)
            logger.info("User monitor client connected")
            
            if not await self.client.is_user_authorized():
                logger.info("User account not authorized - starting authentication process")
                await self._start_auth_process()
                return False  # Authentication needed, but don't block startup
            else:
                logger.info("User account already authorized")
                
                # Get user info with timeout
                try:
                    me = await asyncio.wait_for(self.client.get_me(), timeout=10)
                    self.expected_user_id = me.id
                    logger.info(f"Authorized as: {me.first_name} {me.last_name or ''} (ID: {me.id})")
                except asyncio.TimeoutError:
                    logger.error("Timeout getting user info")
                    return True  # Continue anyway
                
                # Initialize database (this is safe)
                await self._init_channels_database_safe()
                
                # Load channels with robust error handling
                await self._update_monitored_entities_safe()
                
                # Register event handler
                await self._register_event_handler_safe()
                
                # Notify admin of success
                channel_count = len(self.monitored_entities)
                await self._notify_admin_safe(
                    f"✅ **User Account Monitoring Active**\n\n"
                    f"👤 Authenticated as: {me.first_name} {me.last_name or ''}\n"
                    f"📊 Monitoring {channel_count} channels"
                )
                
                logger.info(f"⚙️ SYSTEM: User monitor active for {channel_count} channels")
                return True
                
        except AuthKeyUnregisteredError:
            logger.warning("Auth key unregistered - need to re-authenticate")
            await self._notify_admin_safe("🔐 **Re-authentication Required**\n\nAuth key expired. Use `/auth_restart` to authenticate again.")
            return True
        except UserDeactivatedError:
            logger.error("User account deactivated")
            await self._notify_admin_safe("❌ **Account Deactivated**\n\nUser account has been deactivated by Telegram.")
            return True
        except FloodWaitError as e:
            logger.warning(f"Rate limited for {e.seconds} seconds")
            await self._notify_admin_safe(f"⚠️ **Rate Limited**\n\nTelegram rate limit: wait {e.seconds} seconds.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize user monitor: {e}")
            await self._notify_admin_safe(f"❌ **Authentication Failed**\n\nError: {str(e)}")
            try:
                await self._start_auth_process()
            except Exception as auth_e:
                logger.error(f"Could not start authentication process: {auth_e}")
            return True  # Don't block bot startup
    
    async def _init_channels_database_safe(self):
        """Initialize channels database with error handling"""
        try:
            await self.data_manager.init_channels_table()
            
            # Import from config.json if database is empty (for legacy compatibility)
            existing_channels = await self.data_manager.get_user_monitored_channels_db()
            if not existing_channels:
                config_channels = self.config_manager.get_user_monitored_channels()
                
                # Validate and filter config channels
                valid_channels = []
                for channel in config_channels:
                    if self._is_valid_channel_entry(channel):
                        valid_channels.append(channel)
                    else:
                        logger.warning(f"Skipping invalid channel entry: {channel}")
                
                if valid_channels:
                    for channel in valid_channels:
                        # Handle both string and integer formats
                        if isinstance(channel, str):
                            # Legacy string format - parse it
                            username = channel if channel.startswith('@') else None
                            chat_id = int(channel) if channel.lstrip('-').isdigit() else hash(channel) % 1000000000
                            await self.data_manager.add_channel_simple(chat_id, username, 'user')
                        elif isinstance(channel, int):
                            # Direct chat ID
                            await self.data_manager.add_channel_simple(channel, None, 'user')
                    
                    logger.info(f"⚙️ SYSTEM: Imported {len(valid_channels)} valid channels from config.json")
                else:
                    logger.info("⚙️ SYSTEM: No valid channels found in config.json")
        except Exception as e:
            logger.error(f"Error initializing channels database: {e}")
            # Continue anyway - this shouldn't block startup
    
    def _is_valid_channel_entry(self, channel):
        """Validate if a channel entry is valid (not a user ID)"""
        try:
            if isinstance(channel, dict):
                chat_id = channel.get('chat_id')
                return chat_id is not None and (chat_id < 0 or chat_id > 1000000000)
            elif isinstance(channel, str):
                if channel.startswith('@'):
                    return True
                elif channel.lstrip('-').isdigit():
                    return int(channel) < 0  # Channel IDs should be negative
            elif isinstance(channel, int):
                return channel < 0  # Channel IDs should be negative
            return False
        except Exception:
            return False
    
    async def _register_event_handler_safe(self):
        """Register event handler with error handling"""
        if self.event_handler_registered:
            return
        
        try:
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                try:
                    await self.process_channel_message(event)
                except Exception as e:
                    logger.error(f"Error processing channel message: {e}")
                    # Don't let message processing errors crash the monitor
            
            self.event_handler_registered = True
            logger.info("📨 EVENT: Message event handler registered successfully")
            
        except Exception as e:
            logger.error(f"Failed to register event handler: {e}")
            # Continue anyway - core functionality should still work
    
    async def _start_auth_process(self):
        """Start authentication with better error handling"""
        try:
            result = await asyncio.wait_for(
                self.client.send_code_request(self.auth_phone),
                timeout=15
            )
            self.auth_phone_hash = result.phone_code_hash
            self.waiting_for_code = True
            
            logger.info(f"🔐 AUTH: Authentication code sent to {self.auth_phone}")
            
            await self._notify_admin_safe(
                f"🔐 **Authentication Required**\n\n"
                f"📱 SMS code sent to: {self.auth_phone}\n"
                f"📨 Please send the verification code to this chat\n\n"
                f"Commands: `/auth_status` `/auth_restart`"
            )
                    
        except asyncio.TimeoutError:
            logger.error("🔐 AUTH: Timeout sending authentication code")
            await self._notify_admin_safe("❌ **Authentication Timeout**\n\nFailed to send SMS code (timeout)")
        except PhoneNumberInvalidError:
            logger.error(f"🔐 AUTH: Invalid phone number: {self.auth_phone}")
            await self._notify_admin_safe(f"❌ **Invalid Phone Number**\n\n{self.auth_phone}")
        except FloodWaitError as e:
            logger.error(f"🔐 AUTH: Rate limited for {e.seconds} seconds")
            await self._notify_admin_safe(f"⚠️ **Rate Limited**\n\nWait {e.seconds} seconds before retrying")
        except Exception as e:
            logger.error(f"🔐 AUTH: Authentication error: {e}")
            await self._notify_admin_safe(f"❌ **Authentication Error**\n\n{str(e)}")
    
    async def _notify_admin_safe(self, message: str):
        """Send notification to authorized admin with error handling"""
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
        except asyncio.TimeoutError:
            logger.warning("Timeout sending admin notification")
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")
    
    async def handle_auth_message(self, user_id: int, message_text: str):
        """Handle authentication messages with better error handling"""
        if not self.is_authorized_admin(user_id):
            return False
        
        try:
            if self.waiting_for_code:
                code = message_text.strip()
                if not code.isdigit() or len(code) < 4:
                    await self._send_auth_message_safe(user_id, "❌ Please send only the numeric verification code")
                    return True
                
                try:
                    result = await asyncio.wait_for(
                        self.client.sign_in(phone=self.auth_phone, code=code, phone_code_hash=self.auth_phone_hash),
                        timeout=15
                    )
                    
                    self.waiting_for_code = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message_safe(
                        user_id, 
                        f"✅ **Authentication Successful!**\n\n"
                        f"👤 Authenticated as: {result.first_name} {result.last_name or ''}\n"
                        f"🎯 User account monitoring is now active!"
                    )
                    
                    logger.info(f"🔐 AUTH: User authentication successful for {result.first_name} {result.last_name or ''}")
                    await self._complete_initialization_safe()
                    return True
                    
                except SessionPasswordNeededError:
                    self.waiting_for_code = False
                    self.waiting_for_2fa = True
                    await self._send_auth_message_safe(user_id, "🔐 **Two-Factor Authentication Required**\n\nPlease send your 2FA password:")
                    return True
                    
                except PhoneCodeInvalidError:
                    await self._send_auth_message_safe(user_id, "❌ **Invalid Code**\n\nPlease try again:")
                    return True
                
                except asyncio.TimeoutError:
                    await self._send_auth_message_safe(user_id, "❌ **Authentication Timeout**\n\nPlease try again or use `/auth_restart`")
                    return True
                    
            elif self.waiting_for_2fa:
                password = message_text.strip()
                
                try:
                    result = await asyncio.wait_for(
                        self.client.sign_in(password=password),
                        timeout=15
                    )
                    
                    self.waiting_for_2fa = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message_safe(
                        user_id,
                        f"✅ **2FA Authentication Successful!**\n\n"
                        f"👤 Authenticated as: {result.first_name} {result.last_name or ''}\n"
                        f"🎯 User account monitoring is now active!"
                    )
                    
                    logger.info(f"🔐 AUTH: User 2FA authentication successful")
                    await self._complete_initialization_safe()
                    return True
                    
                except asyncio.TimeoutError:
                    await self._send_auth_message_safe(user_id, "❌ **2FA Timeout**\n\nPlease try again:")
                    return True
                except Exception:
                    await self._send_auth_message_safe(user_id, "❌ **Invalid 2FA Password**\n\nPlease try again:")
                    return True
            
        except Exception as e:
            logger.error(f"🔐 AUTH: Authentication error: {e}")
            await self._send_auth_message_safe(user_id, f"❌ **Authentication Error**\n\n{str(e)}")
            return True
        
        return False
    
    async def _complete_initialization_safe(self):
        """Complete initialization after successful authentication with error handling"""
        try:
            await self._init_channels_database_safe()
            await self._update_monitored_entities_safe()
            await self._register_event_handler_safe()
            
            channel_count = len(self.monitored_entities)
            await self._notify_admin_safe(
                f"🎉 **Setup Complete!**\n\n"
                f"📊 Monitoring {channel_count} channels\n"
                f"🚀 User account monitoring is active!"
            )
            
            logger.info(f"⚙️ SYSTEM: User monitor initialization completed - monitoring {channel_count} channels")
            
        except Exception as e:
            logger.error(f"Failed to complete initialization: {e}")
            await self._notify_admin_safe(f"❌ **Setup Error**\n\n{str(e)}")
    
    async def _send_auth_message_safe(self, user_id: int, message: str):
        """Send authentication message to admin with error handling"""
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
        """Restart authentication with better error handling"""
        if not self.is_authorized_admin(user_id):
            return False
        
        self.waiting_for_code = False
        self.waiting_for_2fa = False
        self.auth_phone_hash = None
        
        try:
            await self._start_auth_process()
            return True
        except Exception as e:
            logger.error(f"Failed to restart authentication: {e}")
            return False
    
    async def _update_monitored_entities_safe(self):
        """Update the list of entities to monitor with robust error handling"""
        if not self.enabled or not await self.client.is_user_authorized():
            logger.info("User monitor not authenticated - skipping entity update")
            return
            
        # Get channels from enhanced database
        try:
            user_channels = await self.data_manager.get_simple_user_channels()
            self.monitored_entities = {}
            
            if not user_channels:
                logger.info("⚙️ SYSTEM: No user-monitored channels in database")
                return
            
            valid_channels = []
            invalid_channels = []
            
            for chat_id in user_channels:
                try:
                    # Skip obviously invalid user IDs
                    if chat_id > 0 and chat_id < 1000000000:
                        logger.warning(f"Skipping invalid user ID as channel: {chat_id}")
                        invalid_channels.append(chat_id)
                        # Remove from database
                        await self.data_manager.remove_channel_simple(chat_id, 'user')
                        continue
                    
                    # Get entity with timeout
                    entity = await asyncio.wait_for(
                        self.client.get_entity(chat_id),
                        timeout=10
                    )
                    
                    # Store with both chat_id and entity
                    self.monitored_entities[entity.id] = {
                        'entity': entity,
                        'chat_id': chat_id,
                        'identifier': f"@{entity.username}" if hasattr(entity, 'username') and entity.username else f"Channel {chat_id}"
                    }
                    valid_channels.append(chat_id)
                    
                    # Get display name from database for logging
                    display_name = await self.data_manager.get_channel_display_name(chat_id)
                    logger.info(f"✅ STARTUP: User monitor loaded: {display_name}")
                    
                except asyncio.TimeoutError:
                    logger.error(f"❌ STARTUP: Timeout loading user channel {chat_id}")
                    invalid_channels.append(chat_id)
                except ValueError as e:
                    if "Could not find the input entity" in str(e) or "PeerUser" in str(e):
                        logger.warning(f"❌ STARTUP: Invalid entity (likely user ID): {chat_id}")
                        invalid_channels.append(chat_id)
                        # Remove from database
                        await self.data_manager.remove_channel_simple(chat_id, 'user')
                    else:
                        logger.error(f"❌ STARTUP: Failed to load user channel {chat_id}: {e}")
                        invalid_channels.append(chat_id)
                except Exception as e:
                    logger.error(f"❌ STARTUP: Failed to load user channel {chat_id}: {e}")
                    invalid_channels.append(chat_id)
            
            # Only notify about issues if there are any and we successfully loaded some
            if invalid_channels and (valid_channels or len(invalid_channels) < len(user_channels)):
                await self._notify_admin_safe(
                    f"⚠️ **Channel Loading Issues**\n\n"
                    f"✅ Loaded channels: {len(valid_channels)}\n"
                    f"❌ Failed to load: {len(invalid_channels)}\n\n"
                    f"**Chat IDs with issues:**\n" + 
                    "\n".join([f"• {ch}" for ch in invalid_channels[:5]]) +
                    (f"\n... and {len(invalid_channels) - 5} more" if len(invalid_channels) > 5 else "") +
                    f"\n\nInvalid entries have been removed from database."
                )
            elif valid_channels:
                logger.info(f"⚙️ SYSTEM: All {len(valid_channels)} user channels loaded successfully")
            else:
                logger.info(f"⚙️ SYSTEM: No valid user channels found")
                
        except Exception as e:
            logger.error(f"Error updating monitored entities: {e}")
            # Continue with empty entities rather than crashing
            self.monitored_entities = {}
    
    # Keep the existing methods but add error handling...
    async def update_monitored_entities(self):
        """Public method that calls the safe version"""
        await self._update_monitored_entities_safe()
    
    async def add_channel(self, channel_identifier: str):
        """Add new channel to monitoring with auto-join and better error handling"""
        if not self.enabled or not await self.client.is_user_authorized():
            return False, "User monitor not authenticated"

        try:
            # Parse channel identifier and get entity with timeout
            entity = None
            if channel_identifier.startswith('@'):
                entity = await asyncio.wait_for(self.client.get_entity(channel_identifier), timeout=15)
            elif 't.me/' in channel_identifier:
                entity = await asyncio.wait_for(self.client.get_entity(channel_identifier), timeout=15)
            elif channel_identifier.lstrip('-').isdigit():
                chat_id = int(channel_identifier)
                if chat_id > 0 and chat_id < 1000000000:
                    return False, "❌ Invalid channel ID (appears to be a user ID)"
                entity = await asyncio.wait_for(self.client.get_entity(chat_id), timeout=15)
            else:
                entity = await asyncio.wait_for(self.client.get_entity(channel_identifier), timeout=15)

            chat_id = entity.id
            username = f"@{entity.username}" if hasattr(entity, 'username') and entity.username else None

            # Check if already in database
            existing_channels = await self.data_manager.get_simple_user_channels()
            if chat_id in existing_channels:
                return False, "Channel already exists in monitoring list"

            # Try to join the channel with timeout
            try:
                from telethon.tl.functions.channels import JoinChannelRequest
                await asyncio.wait_for(self.client(JoinChannelRequest(entity)), timeout=15)
                logger.info(f"⚙️ SYSTEM: Successfully joined channel: {chat_id}")
                join_status = "joined and monitoring"
                
            except asyncio.TimeoutError:
                logger.warning(f"⚙️ SYSTEM: Timeout joining {chat_id}")
                join_status = "monitoring (join timed out)"
            except Exception as join_error:
                # Check if the error is because we're already a member
                error_msg = str(join_error).lower()
                if any(phrase in error_msg for phrase in ["already", "participant", "member"]):
                    logger.info(f"⚙️ SYSTEM: Already member of: {chat_id}")
                    join_status = "already joined, now monitoring"
                else:
                    # Real join failure
                    logger.error(f"⚙️ SYSTEM: Failed to join {chat_id}: {join_error}")
                    return False, f"❌ Cannot join channel: {str(join_error)}"

            # Add to database with enhanced format
            success = await self.data_manager.add_channel_simple(chat_id, username, 'user')
            if not success:
                return False, "Failed to add channel to database"

            # Add to monitored entities
            self.monitored_entities[entity.id] = {
                'entity': entity,
                'chat_id': chat_id,
                'identifier': username or f"Channel {chat_id}"
            }

            # Export config
            await self._export_config_safe()

            display_name = username or getattr(entity, 'title', f'Channel {chat_id}')
            logger.info(f"⚙️ SYSTEM: Added user channel: {display_name}")
            return True, f"✅ Successfully {join_status}: {display_name}"

        except asyncio.TimeoutError:
            logger.error(f"⚙️ SYSTEM: Timeout adding channel {channel_identifier}")
            return False, f"❌ Timeout accessing channel"
        except Exception as e:
            logger.error(f"⚙️ SYSTEM: Failed to add channel {channel_identifier}: {e}")
            return False, f"❌ Cannot access channel: {str(e)}"
    
    async def remove_channel(self, chat_id: int):
        """Remove channel from monitoring with auto-leave and better error handling"""
        try:
            # Check if in database
            existing_channels = await self.data_manager.get_simple_user_channels()
            if chat_id not in existing_channels:
                return False, "Channel not found in monitoring list"
            
            display_name = await self.data_manager.get_channel_display_name(chat_id)
            
            # Auto-leave the channel with timeout
            leave_status = "stopped monitoring"
            if self.enabled and await self.client.is_user_authorized():
                try:
                    entity = await asyncio.wait_for(self.client.get_entity(chat_id), timeout=15)
                    
                    from telethon.tl.functions.channels import LeaveChannelRequest
                    await asyncio.wait_for(self.client(LeaveChannelRequest(entity)), timeout=15)
                    logger.info(f"⚙️ SYSTEM: Auto-left channel: {display_name}")
                    leave_status = "left and stopped monitoring"
                    
                    # Remove from monitored entities
                    entity_id_to_remove = None
                    for entity_id, info in self.monitored_entities.items():
                        if info['chat_id'] == chat_id:
                            entity_id_to_remove = entity_id
                            break
                    
                    if entity_id_to_remove:
                        del self.monitored_entities[entity_id_to_remove]
                        
                except asyncio.TimeoutError:
                    logger.warning(f"⚙️ SYSTEM: Timeout leaving {display_name}")
                    leave_status = "stopped monitoring (leave timed out)"
                except Exception as leave_error:
                    logger.warning(f"⚙️ SYSTEM: Could not leave {display_name}: {leave_error}")
                    leave_status = "stopped monitoring (could not leave channel)"
            
            # Remove from database
            success = await self.data_manager.remove_channel_simple(chat_id, 'user')
            if not success:
                return False, "Failed to remove channel from database"
            
            # Export config
            await self._export_config_safe()
            
            logger.info(f"⚙️ SYSTEM: Removed user channel: {display_name}")
            return True, f"✅ Successfully {leave_status}: {display_name}"
            
        except Exception as e:
            logger.error(f"⚙️ SYSTEM: Failed to remove channel {chat_id}: {e}")
            return False, f"❌ Error removing channel: {str(e)}"
    
    async def get_monitored_channels(self):
        """Get list of currently monitored channels"""
        try:
            channels = await self.data_manager.get_simple_user_channels()
            return channels
        except Exception as e:
            logger.error(f"Error getting monitored channels: {e}")
            return []
    
    async def _export_config_safe(self):
        """Export current database state to config files with error handling"""
        try:
            # Get channels from database
            bot_channels, user_channels = await self.data_manager.export_all_channels_for_config()
            
            # Export to config file
            self.config_manager.export_channels_config(bot_channels, user_channels)
            
            logger.info("⚙️ SYSTEM: Exported channels to config files")
            
        except Exception as e:
            logger.error(f"⚙️ SYSTEM: Failed to export config: {e}")
    
    async def process_channel_message(self, event):
        """Process new message from user-monitored channels with error handling"""
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
            
            # Get display name for logging
            display_name = channel_info.get('identifier', f"Channel {chat_id}")
            logger.info(f"📨 EVENT: Processing message from {display_name}")
            
            # Get users and process keywords with timeout
            try:
                all_users = await asyncio.wait_for(
                    self.data_manager.get_all_users_with_keywords(), 
                    timeout=10
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout getting users for message processing")
                return
            
            forwarded_count = 0
            
            for user_chat_id, keywords in all_users.items():
                if user_chat_id <= 0:
                    continue
                
                try:
                    if not await asyncio.wait_for(
                        self.data_manager.check_user_limit(user_chat_id), 
                        timeout=5
                    ):
                        continue
                    
                    if not self.keyword_matcher.matches_user_keywords(message_text, keywords):
                        continue
                    
                    ignore_keywords = await asyncio.wait_for(
                        self.data_manager.get_user_ignore_keywords(user_chat_id),
                        timeout=5
                    )
                    if self.keyword_matcher.matches_ignore_keywords(message_text, ignore_keywords):
                        continue
                    
                    if self.bot_instance:
                        try:
                            await asyncio.wait_for(
                                self.forward_message_via_bot(user_chat_id, event.message, chat_id),
                                timeout=10
                            )
                            forwarded_count += 1
                            await asyncio.sleep(0.5)
                        except asyncio.TimeoutError:
                            logger.warning(f"📤 FORWARD: Timeout forwarding to user {user_chat_id}")
                        except Exception as e:
                            logger.error(f"📤 FORWARD: Failed to forward to user {user_chat_id}: {e}")
                
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout processing user {user_chat_id}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing user {user_chat_id}: {e}")
                    continue
            
            if forwarded_count > 0:
                logger.info(f"📤 FORWARD: User monitor forwarded message to {forwarded_count} users")
                
        except Exception as e:
            logger.error(f"Error in process_channel_message: {e}")
            # Don't let message processing errors crash the monitor
    
    async def forward_message_via_bot(self, user_chat_id, message, source_chat_id):
        """Forward message to user via bot with error handling"""
        if not self.bot_instance:
            return
        
        try:
            # Get display name for the message
            display_name = await asyncio.wait_for(
                self.data_manager.get_channel_display_name(source_chat_id),
                timeout=5
            )
            
            formatted_message = f"📋 Job from {display_name}:\n\n{message.text}"
            
            await self.bot_instance.send_message(
                chat_id=user_chat_id,
                text=formatted_message
            )
            
            await self.data_manager.log_message_forward(
                user_chat_id, source_chat_id, message.id
            )
            
        except asyncio.TimeoutError:
            logger.warning("Timeout in forward_message_via_bot")
            raise
        except Exception as e:
            logger.error(f"📤 FORWARD: Error forwarding via bot: {e}")
            raise
    
    async def run_forever(self):
        """Keep the client running with error handling and reconnection"""
        if not self.enabled or not self.client:
            logger.info("User monitor not running (disabled)")
            return
            
        logger.info("⚙️ SYSTEM: User monitor client running...")
        
        max_reconnect_attempts = 5
        reconnect_delay = 30  # seconds
        
        for attempt in range(max_reconnect_attempts):
            try:
                await self.client.run_until_disconnected()
                # If we get here, it was a clean disconnect
                logger.info("⚙️ SYSTEM: User monitor disconnected cleanly")
                break
                
            except ConnectionError as e:
                logger.warning(f"User monitor connection error (attempt {attempt + 1}/{max_reconnect_attempts}): {e}")
                if attempt < max_reconnect_attempts - 1:
                    logger.info(f"Reconnecting in {reconnect_delay} seconds...")
                    await asyncio.sleep(reconnect_delay)
                    try:
                        await self.client.connect()
                    except Exception as reconnect_e:
                        logger.error(f"Reconnection failed: {reconnect_e}")
                else:
                    logger.error("Max reconnection attempts reached")
                    
            except Exception as e:
                logger.error(f"User monitor error: {e}")
                if attempt < max_reconnect_attempts - 1:
                    logger.info(f"Retrying in {reconnect_delay} seconds...")
                    await asyncio.sleep(reconnect_delay)
                else:
                    logger.error("Max retry attempts reached, stopping user monitor")
                    break
        
        self.enabled = False
        await self._notify_admin_safe("⚠️ **User Monitor Stopped**\n\nUser account monitoring has stopped after connection issues.")
    
    async def stop(self):
        """Stop the client with proper cleanup"""
        try:
            if self.client and self.client.is_connected():
                await asyncio.wait_for(self.client.disconnect(), timeout=10)
                logger.info("⚙️ SYSTEM: User account monitor stopped")
        except asyncio.TimeoutError:
            logger.warning("Timeout stopping user monitor")
        except Exception as e:
            logger.error(f"Error stopping user monitor: {e}")
        finally:
            self.enabled = False