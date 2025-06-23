"""
Enhanced Configuration Manager - Supports both bot and user monitoring
"""

import json
import logging
from typing import List

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        self.channels_to_monitor = []           # Bot-monitored (existing)
        self.user_monitored_channels = []       # User-monitored (new)
        self.load_config()
    
    def load_config(self):
        """Load channels to monitor from config file"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                
                # Existing bot monitoring
                old_channels = self.channels_to_monitor.copy()
                self.channels_to_monitor = config.get('channels', [])
                
                # New user monitoring (optional)
                old_user_channels = self.user_monitored_channels.copy()
                self.user_monitored_channels = config.get('user_monitored_channels', [])
                
                if old_channels != self.channels_to_monitor:
                    logger.info(f"Updated bot channels: {len(self.channels_to_monitor)} channels")
                    
                if old_user_channels != self.user_monitored_channels:
                    logger.info(f"Updated user channels: {len(self.user_monitored_channels)} channels")
                    
        except FileNotFoundError:
            logger.warning("config.json not found, using empty channel lists")
            self.channels_to_monitor = []
            self.user_monitored_channels = []
    
    def get_channels_to_monitor(self) -> List[str]:
        """Get list of channels for bot to monitor (existing functionality)"""
        return self.channels_to_monitor.copy()
    
    def get_user_monitored_channels(self) -> List[str]:
        """Get list of channels for user account to monitor (new functionality)"""
        return self.user_monitored_channels.copy()
    
    def is_monitored_channel(self, chat_id: int, username: str = None) -> bool:
        """Check if a channel is being monitored by BOT (existing functionality)"""
        channel_username = f"@{username}" if username else str(chat_id)
        return channel_username in self.channels_to_monitor or str(chat_id) in self.channels_to_monitor
    
    def is_user_monitored_channel(self, chat_id: int, username: str = None) -> bool:
        """Check if a channel is being monitored by USER ACCOUNT (new functionality)"""
        channel_username = f"@{username}" if username else str(chat_id)
        return channel_username in self.user_monitored_channels or str(chat_id) in self.user_monitored_channels
