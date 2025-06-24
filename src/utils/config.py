"""
Enhanced Configuration Manager - CLEANED VERSION
Supports current enhanced format only - migration complexity removed
Handles @username, t.me/channel, and chat IDs with automatic parsing
"""

import json
import logging
import shutil
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        self.config_dir = Path('data/config')
        self.backup_dir = self.config_dir / 'backups'
        self.channels_file = self.config_dir / 'channels.json'
        self.users_file = self.config_dir / 'users.json'
        
        # Configuration
        self.backup_retention = int(os.getenv('BACKUP_RETENTION_COUNT', '5'))
        self.backup_frequency = os.getenv('BACKUP_FREQUENCY', 'daily')
        
        # Channel data
        self.channels_to_monitor = []
        self.user_monitored_channels = []
        
        # Create directories
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Load configuration
        self.load_channels_config()
    
    def parse_channel_input(self, input_str: str) -> Optional[str]:
        """
        Parse channel input and return username (or None for private channels)
        
        Supports:
        - @channelname → @channelname
        - t.me/channelname → @channelname  
        - https://t.me/channelname → @channelname
        - t.me/joinchat/xyz → None (private)
        - -1001234567890 → None (chat ID only)
        """
        input_str = input_str.strip()
        
        # Handle @username format
        if input_str.startswith('@'):
            return input_str
        
        # Handle t.me/username (with or without https)
        tme_pattern = r'(?:https?://)?t\.me/([^/\s]+)'
        match = re.match(tme_pattern, input_str)
        if match:
            channel_part = match.group(1)
            
            # Skip joinchat links (private channels)
            if channel_part.startswith('joinchat/'):
                return None
            else:
                # Public channel
                return f"@{channel_part}"
        
        # Handle raw chat ID or unknown format
        return None
    
    def load_channels_config(self):
        """Load channels configuration - current enhanced format only"""
        try:
            if self.channels_file.exists():
                with open(self.channels_file, 'r') as f:
                    config = json.load(f)
                    
                    # Extract chat_ids from current enhanced format
                    bot_channels = config.get('channels', [])
                    user_channels = config.get('user_monitored_channels', [])
                    
                    # Only handle current enhanced format (dict with chat_id)
                    self.channels_to_monitor = []
                    for ch in bot_channels:
                        if isinstance(ch, dict) and 'chat_id' in ch:
                            self.channels_to_monitor.append(ch['chat_id'])
                    
                    self.user_monitored_channels = []
                    for ch in user_channels:
                        if isinstance(ch, dict) and 'chat_id' in ch:
                            self.user_monitored_channels.append(ch['chat_id'])
                    
                    logger.info(f"Loaded {len(self.channels_to_monitor)} bot channels, {len(self.user_monitored_channels)} user channels")
            else:
                logger.info("No channels.json found - using empty channel lists")
                self.channels_to_monitor = []
                self.user_monitored_channels = []
        except Exception as e:
            logger.error(f"Error loading channels config: {e}")
            self.channels_to_monitor = []
            self.user_monitored_channels = []
    
    def export_channels_config(self, bot_channels: List[Dict], user_channels: List[Dict]):
        """Export channels configuration with backup - enhanced format"""
        try:
            # Create backup if file exists
            if self.channels_file.exists():
                self._create_backup('channels')
            
            # Export enhanced config
            config = {
                "channels": bot_channels,
                "user_monitored_channels": user_channels,
                "export_timestamp": datetime.now().isoformat(),
                "total_bot_channels": len(bot_channels),
                "total_user_channels": len(user_channels),
                "format_version": "2.0"  # Mark as enhanced format
            }
            
            with open(self.channels_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Exported enhanced channels config: {len(bot_channels)} bot, {len(user_channels)} user")
            
            # Update internal state
            self.channels_to_monitor = [ch['chat_id'] for ch in bot_channels if 'chat_id' in ch]
            self.user_monitored_channels = [ch['chat_id'] for ch in user_channels if 'chat_id' in ch]
            
        except Exception as e:
            logger.error(f"Failed to export channels config: {e}")
    
    def export_users_config(self, users_data: List[Dict[str, Any]]):
        """Export users configuration with backup"""
        try:
            # Create backup if file exists
            if self.users_file.exists():
                self._create_backup('users')
            
            # Export current config
            config = {
                "users": users_data,
                "export_timestamp": datetime.now().isoformat(),
                "total_users": len(users_data),
                "total_keywords": sum(len(user.get('keywords', [])) for user in users_data)
            }
            
            with open(self.users_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Exported users config: {len(users_data)} users")
            
        except Exception as e:
            logger.error(f"Failed to export users config: {e}")
    
    def _create_backup(self, config_type: str):
        """Create timestamped backup"""
        try:
            if config_type == 'channels' and self.channels_file.exists():
                timestamp = datetime.now().strftime("%Y%m%d")
                backup_file = self.backup_dir / f"channels_auto_{timestamp}.json"
                shutil.copy2(self.channels_file, backup_file)
                
            elif config_type == 'users' and self.users_file.exists():
                timestamp = datetime.now().strftime("%Y%m%d") 
                backup_file = self.backup_dir / f"users_auto_{timestamp}.json"
                shutil.copy2(self.users_file, backup_file)
                
            # Cleanup old auto backups
            self._cleanup_auto_backups(config_type)
            
        except Exception as e:
            logger.error(f"Failed to create {config_type} backup: {e}")
    
    def _cleanup_auto_backups(self, config_type: str):
        """Clean up old automatic backups (keep manual backups)"""
        try:
            pattern = f"{config_type}_auto_*.json"
            backup_files = list(self.backup_dir.glob(pattern))
            
            if len(backup_files) <= self.backup_retention:
                return
            
            # Sort by modification time (newest first)
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove old auto backups
            for old_backup in backup_files[self.backup_retention:]:
                old_backup.unlink()
                logger.info(f"Cleaned old auto backup: {old_backup.name}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup {config_type} backups: {e}")
    
    def create_manual_backup(self):
        """Create manual backup (never auto-deleted)"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if self.channels_file.exists():
                backup_file = self.backup_dir / f"channels_manual_{timestamp}.json"
                shutil.copy2(self.channels_file, backup_file)
                
            if self.users_file.exists():
                backup_file = self.backup_dir / f"users_manual_{timestamp}.json"
                shutil.copy2(self.users_file, backup_file)
                
            logger.info(f"Created manual backup: {timestamp}")
            return timestamp
            
        except Exception as e:
            logger.error(f"Failed to create manual backup: {e}")
            return None
    
    def list_backups(self):
        """List all available backups"""
        try:
            backups = []
            for backup_file in self.backup_dir.glob("*.json"):
                stat = backup_file.stat()
                backups.append({
                    'filename': backup_file.name,
                    'type': 'manual' if 'manual' in backup_file.name else 'auto',
                    'created': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    'size': f"{stat.st_size} bytes"
                })
            
            return sorted(backups, key=lambda x: x['created'], reverse=True)
            
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []
    
    def load_users_config(self):
        """Load users configuration for import"""
        try:
            if self.users_file.exists():
                with open(self.users_file, 'r') as f:
                    config = json.load(f)
                    return config.get('users', [])
            return []
        except Exception as e:
            logger.error(f"Failed to load users config: {e}")
            return []
    
    # Public API methods for compatibility with existing code
    def get_channels_to_monitor(self) -> List[int]:
        """Get list of chat IDs for bot to monitor"""
        return self.channels_to_monitor.copy()
    
    def get_user_monitored_channels(self) -> List[int]:
        """Get list of chat IDs for user account to monitor"""
        return self.user_monitored_channels.copy()
    
    def is_monitored_channel(self, chat_id: int, username: str = None) -> bool:
        """Check if a channel is being monitored by BOT"""
        return chat_id in self.channels_to_monitor
    
    def is_user_monitored_channel(self, chat_id: int, username: str = None) -> bool:
        """Check if a channel is being monitored by USER ACCOUNT"""
        return chat_id in self.user_monitored_channels