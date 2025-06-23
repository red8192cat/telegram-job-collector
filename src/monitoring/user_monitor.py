"""
SECURE User Account Monitor with Admin-Only Authentication
Production version with dynamic channel management
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
        self.expected_user_id = None
        self.event_handler_registered = False
        
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
        """Initialize the user client and set up monitoring"""
        if not self.enabled or not self.client:
            logger.info("User monitor not enabled - skipping initialization")
            return False
        
        try:
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.info("User account not authorized - starting authentication process")
                await self._start_auth_process()
                return False
            else:
                logger.info("User account already authorized")
                me = await self.client.get_me()
                self.expected_user_id = me.id
                logger.info(f"Authorized as: {me.first_name} {me.last_name or ''} (ID: {me.id})")
                
                # Initialize database and load channels
                await self._init_channels_database()
                await self.update_monitored_entities()
                await self._register_event_handler()
                
                # Notify admin
                await self._notify_admin(
                    f"✅ **User Account Monitoring Active**\n\n"
                    f"👤 Authenticated as: {me.first_name} {me.last_name or ''}\n"
                    f"📊 Monitoring {len(self.monitored_entities)} channels"
                )
                
                logger.info(f"⚙️ SYSTEM: User monitor active for {len(self.monitored_entities)} channels")
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize user monitor: {e}")
            await self._notify_admin(f"❌ **Authentication Failed**\n\nError: {str(e)}")
            try:
                await self._start_auth_process()
            except:
                logger.error("Could not start authentication process")
            return False
    
    async def _init_channels_database(self):
        """Initialize channels database from config.json"""
        await self.data_manager.init_channels_table()
        
        # Import from config.json if database is empty
        existing_channels = await self.data_manager.get_user_monitored_channels_db()
        if not existing_channels:
            config_channels = self.config_manager.get_user_monitored_channels()
            for channel in config_channels:
                await self.data_manager.add_channel_db(channel, 'user')
            logger.info(f"⚙️ SYSTEM: Imported {len(config_channels)} channels from config.json")
    
    async def _register_event_handler(self):
        """Register event handler AFTER authentication is complete"""
        if self.event_handler_registered:
            return
        
        try:
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                await self.process_channel_message(event)
            
            self.event_handler_registered = True
            logger.info("📨 EVENT: Message event handler registered successfully")
            
        except Exception as e:
            logger.error(f"Failed to register event handler: {e}")
            await self._notify_admin(f"❌ **Event Handler Error**: {str(e)}")
    
    async def _start_auth_process(self):
        """Start authentication and notify admin"""
        try:
            result = await self.client.send_code_request(self.auth_phone)
            self.auth_phone_hash = result.phone_code_hash
            self.waiting_for_code = True
            
            logger.info(f"🔐 AUTH: Authentication code sent to {self.auth_phone}")
            
            await self._notify_admin(
                f"🔐 **Authentication Required**\n\n"
                f"📱 SMS code sent to: {self.auth_phone}\n"
                f"📨 Please send the verification code to this chat\n\n"
                f"Commands: `/auth_status` `/auth_restart`"
            )
                    
        except PhoneNumberInvalidError:
            logger.error(f"🔐 AUTH: Invalid phone number: {self.auth_phone}")
            await self._notify_admin(f"❌ **Invalid Phone Number**\n\n{self.auth_phone}")
        except Exception as e:
            logger.error(f"🔐 AUTH: Authentication error: {e}")
            await self._notify_admin(f"❌ **Authentication Error**\n\n{str(e)}")
    
    async def _notify_admin(self, message: str):
        """Send notification to authorized admin"""
        if self.authorized_admin_id and self.bot_instance:
            try:
                await self.bot_instance.send_message(
                    chat_id=self.authorized_admin_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")
    
    async def handle_auth_message(self, user_id: int, message_text: str):
        """Handle authentication messages - ADMIN ONLY"""
        if not self.is_authorized_admin(user_id):
            return False
        
        try:
            if self.waiting_for_code:
                code = message_text.strip()
                if not code.isdigit() or len(code) < 4:
                    await self._send_auth_message(user_id, "❌ Please send only the numeric verification code")
                    return True
                
                try:
                    result = await self.client.sign_in(phone=self.auth_phone, code=code, phone_code_hash=self.auth_phone_hash)
                    
                    self.waiting_for_code = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message(
                        user_id, 
                        f"✅ **Authentication Successful!**\n\n"
                        f"👤 Authenticated as: {result.first_name} {result.last_name or ''}\n"
                        f"🎯 User account monitoring is now active!"
                    )
                    
                    logger.info(f"🔐 AUTH: User authentication successful for {result.first_name} {result.last_name or ''}")
                    await self._complete_initialization()
                    return True
                    
                except SessionPasswordNeededError:
                    self.waiting_for_code = False
                    self.waiting_for_2fa = True
                    await self._send_auth_message(user_id, "🔐 **Two-Factor Authentication Required**\n\nPlease send your 2FA password:")
                    return True
                    
                except PhoneCodeInvalidError:
                    await self._send_auth_message(user_id, "❌ **Invalid Code**\n\nPlease try again:")
                    return True
                    
            elif self.waiting_for_2fa:
                password = message_text.strip()
                
                try:
                    result = await self.client.sign_in(password=password)
                    
                    self.waiting_for_2fa = False
                    self.expected_user_id = result.id
                    
                    await self._send_auth_message(
                        user_id,
                        f"✅ **2FA Authentication Successful!**\n\n"
                        f"👤 Authenticated as: {result.first_name} {result.last_name or ''}\n"
                        f"🎯 User account monitoring is now active!"
                    )
                    
                    logger.info(f"🔐 AUTH: User 2FA authentication successful")
                    await self._complete_initialization()
                    return True
                    
                except Exception:
                    await self._send_auth_message(user_id, "❌ **Invalid 2FA Password**\n\nPlease try again:")
                    return True
            
        except Exception as e:
            logger.error(f"🔐 AUTH: Authentication error: {e}")
            await self._send_auth_message(user_id, f"❌ **Authentication Error**\n\n{str(e)}")
            return True
        
        return False
    
    async def _complete_initialization(self):
        """Complete initialization after successful authentication"""
        try:
            await self._init_channels_database()
            await self.update_monitored_entities()
            await self._register_event_handler()
            
            channel_count = len(self.monitored_entities)
            await self._notify_admin(
                f"🎉 **Setup Complete!**\n\n"
                f"📊 Monitoring {channel_count} channels\n"
                f"🚀 User account monitoring is active!"
            )
            
            logger.info(f"⚙️ SYSTEM: User monitor initialization completed - monitoring {channel_count} channels")
            
        except Exception as e:
            logger.error(f"Failed to complete initialization: {e}")
            await self._notify_admin(f"❌ **Setup Error**\n\n{str(e)}")
    
    async def _send_auth_message(self, user_id: int, message: str):
        """Send authentication message to admin"""
        if self.bot_instance:
            try:
                await self.bot_instance.send_message(
                    chat_id=user_id, 
                    text=message,
                    parse_mode='Markdown'
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
        """Restart authentication - ADMIN ONLY"""
        if not self.is_authorized_admin(user_id):
            return False
        
        self.waiting_for_code = False
        self.waiting_for_2fa = False
        self.auth_phone_hash = None
        
        await self._start_auth_process()
        return True
    
    async def update_monitored_entities(self):
        """Update the list of entities to monitor from database"""
        if not self.enabled or not await self.client.is_user_authorized():
            return
            
        channels = await self.data_manager.get_user_monitored_channels_db()
        self.monitored_entities = {}
        
        if not channels:
            logger.info("⚙️ SYSTEM: No user-monitored channels in database")
            return
        
        for channel_identifier in channels:
            try:
                if channel_identifier.startswith('@'):
                    entity = await self.client.get_entity(channel_identifier)
                elif channel_identifier.startswith('-'):
                    entity = await self.client.get_entity(int(channel_identifier))
                else:
                    entity = await self.client.get_entity(channel_identifier)
                
                self.monitored_entities[entity.id] = {
                    'entity': entity,
                    'identifier': channel_identifier
                }
                logger.info(f"⚙️ SYSTEM: User monitor added: {channel_identifier}")
                
            except Exception as e:
                logger.error(f"⚙️ SYSTEM: Failed to get entity for {channel_identifier}: {e}")
    
    async def add_channel(self, channel_identifier: str):
        """Add new channel to monitoring with auto-join"""
        if not self.enabled or not await self.client.is_user_authorized():
            return False, "User monitor not authenticated"
        
        try:
            # Validate and get channel entity
            if channel_identifier.startswith('@'):
                entity = await self.client.get_entity(channel_identifier)
            elif channel_identifier.startswith('-'):
                entity = await self.client.get_entity(int(channel_identifier))
            else:
                entity = await self.client.get_entity(channel_identifier)
            
            # Check if already in database
            existing_channels = await self.data_manager.get_user_monitored_channels_db()
            if channel_identifier in existing_channels:
                return False, "Channel already exists in monitoring list"
            
            # Check if already joined
            try:
                # Try to get participants to check membership
                participants = await self.client.get_participants(entity, limit=1)
                me = await self.client.get_me()
                is_already_joined = any(p.id == me.id for p in participants)
                
                if not is_already_joined:
                    # Auto-join the channel
                    from telethon.tl.functions.channels import JoinChannelRequest
                    await self.client(JoinChannelRequest(entity))
                    logger.info(f"⚙️ SYSTEM: Auto-joined channel: {channel_identifier}")
                    join_status = "joined and monitoring"
                else:
                    logger.info(f"⚙️ SYSTEM: Already member of: {channel_identifier}")
                    join_status = "already joined, now monitoring"
                    
            except Exception as join_error:
                # If we can't join, fail completely
                logger.error(f"⚙️ SYSTEM: Failed to join {channel_identifier}: {join_error}")
                return False, f"❌ Cannot join channel: {str(join_error)}"
            
            # Add to database
            success = await self.data_manager.add_channel_db(channel_identifier, 'user')
            if not success:
                return False, "Failed to add channel to database"
            
            # Add to monitored entities
            self.monitored_entities[entity.id] = {
                'entity': entity,
                'identifier': channel_identifier
            }
            
            # Update config.json
            await self._export_config()
            
            logger.info(f"⚙️ SYSTEM: Added user channel: {channel_identifier}")
            return True, f"✅ Successfully {join_status}: {channel_identifier}"
            
        except Exception as e:
            logger.error(f"⚙️ SYSTEM: Failed to add channel {channel_identifier}: {e}")
            return False, f"❌ Cannot access channel: {str(e)}"
    
    async def remove_channel(self, channel_identifier: str):
        """Remove channel from monitoring with auto-leave"""
        try:
            # Check if in database
            existing_channels = await self.data_manager.get_user_monitored_channels_db()
            if channel_identifier not in existing_channels:
                return False, "Channel not found in monitoring list"
            
            # Get entity and leave channel
            leave_status = "stopped monitoring"
            if self.enabled and await self.client.is_user_authorized():
                try:
                    if channel_identifier.startswith('@'):
                        entity = await self.client.get_entity(channel_identifier)
                    elif channel_identifier.startswith('-'):
                        entity = await self.client.get_entity(int(channel_identifier))
                    else:
                        entity = await self.client.get_entity(channel_identifier)
                    
                    # Auto-leave the channel
                    from telethon.tl.functions.channels import LeaveChannelRequest
                    await self.client(LeaveChannelRequest(entity))
                    logger.info(f"⚙️ SYSTEM: Auto-left channel: {channel_identifier}")
                    leave_status = "left and stopped monitoring"
                    
                    # Remove from monitored entities
                    entity_id_to_remove = None
                    for entity_id, info in self.monitored_entities.items():
                        if info['identifier'] == channel_identifier:
                            entity_id_to_remove = entity_id
                            break
                    
                    if entity_id_to_remove:
                        del self.monitored_entities[entity_id_to_remove]
                        
                except Exception as leave_error:
                    logger.warning(f"⚙️ SYSTEM: Could not leave {channel_identifier}: {leave_error}")
                    leave_status = "stopped monitoring (could not leave channel)"
            
            # Remove from database
            success = await self.data_manager.remove_channel_db(channel_identifier, 'user')
            if not success:
                return False, "Failed to remove channel from database"
            
            # Update config.json
            await self._export_config()
            
            logger.info(f"⚙️ SYSTEM: Removed user channel: {channel_identifier}")
            return True, f"✅ Successfully {leave_status}: {channel_identifier}"
            
        except Exception as e:
            logger.error(f"⚙️ SYSTEM: Failed to remove channel {channel_identifier}: {e}")
            return False, f"❌ Error removing channel: {str(e)}"
    
    async def get_monitored_channels(self):
        """Get list of currently monitored channels"""
        channels = await self.data_manager.get_user_monitored_channels_db()
        return channels
    
    async def _export_config(self):
        """Export current database state to config.json"""
        try:
            # Get channels from database
            bot_channels = await self.data_manager.get_bot_monitored_channels_db()
            user_channels = await self.data_manager.get_user_monitored_channels_db()
            
            # Create config structure
            config = {
                "channels": bot_channels,
                "user_monitored_channels": user_channels,
                "last_exported": datetime.now().isoformat()
            }
            
            # Write to config.json
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info("⚙️ SYSTEM: Exported channels to config.json")
            
        except Exception as e:
            logger.error(f"⚙️ SYSTEM: Failed to export config: {e}")
    
    async def process_channel_message(self, event):
        """Process new message from user-monitored channels"""
        if not self.enabled or not event.message or not event.message.text:
            return
        
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
        
        logger.info(f"📨 EVENT: Processing message from {channel_info['identifier']}")
        
        # Get users and process keywords
        all_users = await self.data_manager.get_all_users_with_keywords()
        forwarded_count = 0
        
        for user_chat_id, keywords in all_users.items():
            if user_chat_id <= 0:
                continue
            
            if not await self.data_manager.check_user_limit(user_chat_id):
                continue
            
            if not self.keyword_matcher.matches_user_keywords(message_text, keywords):
                continue
            
            ignore_keywords = await self.data_manager.get_user_ignore_keywords(user_chat_id)
            if self.keyword_matcher.matches_ignore_keywords(message_text, ignore_keywords):
                continue
            
            if self.bot_instance:
                try:
                    await self.forward_message_via_bot(user_chat_id, event.message, chat_id)
                    forwarded_count += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"📤 FORWARD: Failed to forward to user {user_chat_id}: {e}")
        
        if forwarded_count > 0:
            logger.info(f"📤 FORWARD: User monitor forwarded message to {forwarded_count} users")
    
    async def forward_message_via_bot(self, user_chat_id, message, source_chat_id):
        """Forward message to user via bot"""
        if not self.bot_instance:
            return
        
        try:
            # Convert chat_id to entity_id for lookup
            entity_id = None
            if source_chat_id < 0 and str(source_chat_id).startswith('-100'):
                entity_id = int(str(source_chat_id)[4:])
            else:
                entity_id = abs(source_chat_id) if source_chat_id < 0 else source_chat_id
            
            # Get channel name
            source_info = self.monitored_entities.get(entity_id) or self.monitored_entities.get(source_chat_id, {})
            source_name = source_info.get('identifier', f'Channel {source_chat_id}')
            
            formatted_message = f"📋 Job from {source_name}:\n\n{message.text}"
            
            await self.bot_instance.send_message(
                chat_id=user_chat_id,
                text=formatted_message
            )
            
            await self.data_manager.log_message_forward(
                user_chat_id, source_chat_id, message.id
            )
            
        except Exception as e:
            logger.error(f"📤 FORWARD: Error forwarding via bot: {e}")
            raise
    
    async def run_forever(self):
        """Keep the client running"""
        if not self.enabled or not self.client:
            logger.info("User monitor not running (disabled)")
            return
            
        logger.info("⚙️ SYSTEM: User monitor client running...")
        try:
            await self.client.run_until_disconnected()
        except Exception as e:
            logger.error(f"User monitor disconnected: {e}")
            self.enabled = False
    
    async def stop(self):
        """Stop the client"""
        if self.client:
            await self.client.disconnect()
            logger.info("⚙️ SYSTEM: User account monitor stopped")