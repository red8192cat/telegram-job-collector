"""
Fixed User Account Monitor - Channel Management
The issue is in _check_channel_membership and add_channel methods
"""

async def _check_channel_membership(self, entity, channel_identifier):
    """Check if user account is a member of the channel - FIXED VERSION"""
    try:
        # Get current user
        me = await self.client.get_me()
        
        # For channels, try a simpler approach first
        if hasattr(entity, 'broadcast') and entity.broadcast:
            # This is a channel - try to get entity again to check access
            try:
                # If we can get the entity, we likely have access
                await self.client.get_entity(entity.id)
                return True
            except Exception:
                return False
        
        # For groups, try the participants approach with error handling
        try:
            # Try to get a small number of participants
            participants = await self.client.get_participants(entity, limit=1)
            
            # If we got here, we have access - now check if we're a member
            async for participant in self.client.iter_participants(entity, limit=10):
                if participant.id == me.id:
                    return True
            
            # We can see participants but we're not in the list
            return False
            
        except Exception as e:
            # If we can't get participants, we're probably not a member
            logger.debug(f"Cannot access participants for {channel_identifier}: {e}")
            return False
            
    except Exception as e:
        logger.error(f"⚙️ SYSTEM: Error checking membership for {channel_identifier}: {e}")
        return False

async def add_channel(self, channel_identifier: str):
    """Add new channel to monitoring with auto-join - FIXED VERSION"""
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

        # Try to join the channel FIRST (don't check membership beforehand)
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            await self.client(JoinChannelRequest(entity))
            logger.info(f"⚙️ SYSTEM: Successfully joined channel: {channel_identifier}")
            join_status = "joined and monitoring"
            
        except Exception as join_error:
            # Check if the error is because we're already a member
            error_msg = str(join_error).lower()
            if any(phrase in error_msg for phrase in ["already", "participant", "member"]):
                logger.info(f"⚙️ SYSTEM: Already member of: {channel_identifier}")
                join_status = "already joined, now monitoring"
            else:
                # Real join failure
                logger.error(f"⚙️ SYSTEM: Failed to join {channel_identifier}: {join_error}")
                return False, f"❌ Cannot join channel: {str(join_error)}"

        # If we got here, we successfully joined or were already a member
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

async def update_monitored_entities(self):
    """Update the list of entities to monitor from database - SIMPLIFIED VERSION"""
    if not self.enabled or not await self.client.is_user_authorized():
        return
        
    channels = await self.data_manager.get_user_monitored_channels_db()
    self.monitored_entities = {}
    
    if not channels:
        logger.info("⚙️ SYSTEM: No user-monitored channels in database")
        return
    
    valid_channels = []
    invalid_channels = []
    
    for channel_identifier in channels:
        try:
            if channel_identifier.startswith('@'):
                entity = await self.client.get_entity(channel_identifier)
            elif channel_identifier.startswith('-'):
                entity = await self.client.get_entity(int(channel_identifier))
            else:
                entity = await self.client.get_entity(channel_identifier)
            
            # If we can get the entity, assume we have access
            # Don't do expensive membership checks on startup
            self.monitored_entities[entity.id] = {
                'entity': entity,
                'identifier': channel_identifier
            }
            valid_channels.append(channel_identifier)
            logger.info(f"✅ STARTUP: User monitor loaded: {channel_identifier}")
            
        except Exception as e:
            invalid_channels.append(channel_identifier)
            logger.error(f"❌ STARTUP: Failed to load user channel {channel_identifier}: {e}")
    
    # Only notify about issues if there are any
    if invalid_channels:
        await self._notify_admin(
            f"⚠️ **Channel Loading Issues**\n\n"
            f"✅ Loaded channels: {len(valid_channels)}\n"
            f"❌ Failed to load: {len(invalid_channels)}\n\n"
            f"**Issues found:**\n" + 
            "\n".join([f"• {ch}" for ch in invalid_channels]) +
            f"\n\nUse `/admin channels` to review"
        )
    else:
        logger.info(f"⚙️ SYSTEM: All {len(valid_channels)} user channels loaded successfully")