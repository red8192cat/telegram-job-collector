"""
Message Handlers - COMPLETELY EMPTY FOR DEBUGGING
"""

import logging
from storage.sqlite_manager import SQLiteManager
from utils.config import ConfigManager

logger = logging.getLogger(__name__)

class MessageHandlers:
    def __init__(self, data_manager: SQLiteManager, config_manager: ConfigManager):
        self.data_manager = data_manager
        self.config_manager = config_manager
        logger.info("MessageHandlers initialized (EMPTY VERSION)")
    
    def register(self, app):
        """Register NO message handlers - for debugging"""
        logger.info("MessageHandlers: NO handlers registered (debug mode)")
    
    async def collect_and_repost_jobs(self, bot):
        """Empty function for compatibility"""
        logger.info("collect_and_repost_jobs: Empty function (debug mode)")
        pass
