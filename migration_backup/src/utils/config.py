"""
Configuration Manager - Handles config file loading and channel management
"""

import json
import logging
from typing import List

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        self.channels_to_monitor = []
        self.load_config()
    
    def load_config(self):
        """Load channels to monitor from config file"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                old_channels = self.channels_to_monitor.copy()
                self.channels_to_monitor = config.get('channels', [])
                
                if old_channels != self.channels_to_monitor:
                    logger.info(f"Updated channels: {len(self.channels_to_monitor)} channels to monitor")
                    
        except FileNotFoundError:
            logger.warning("config.json not found, using empty channel list")
            self.channels_to_monitor = []
    
    def get_channels_to_monitor(self) -> List[str]:
        """Get list of channels to monitor"""
        return self.channels_to_monitor.copy()
    
    def is_monitored_channel(self, chat_id: int, username: str = None) -> bool:
        """Check if a channel is being monitored"""
        channel_username = f"@{username}" if username else str(chat_id)
        return channel_username in self.channels_to_monitor or str(chat_id) in self.channels_to_monitor
