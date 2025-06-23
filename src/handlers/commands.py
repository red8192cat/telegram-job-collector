"""
Command Handlers - DEBUG VERSION - Minimal test
"""

import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from storage.sqlite_manager import SQLiteManager

logger = logging.getLogger(__name__)

class CommandHandlers:
    def __init__(self, data_manager: SQLiteManager):
        self.data_manager = data_manager
        logger.info("CommandHandlers initialized")
    
    def register(self, app):
        """Register minimal command handlers for testing"""
        logger.info("Starting to register command handlers...")
        
        # Register just one simple command first
        app.add_handler(CommandHandler("start", self.start_command))
        logger.info("✅ /start handler registered")
        
        app.add_handler(CommandHandler("test", self.test_command))
        logger.info("✅ /test handler registered")
        
        logger.info("✅ Command handlers registration completed")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - DEBUG VERSION"""
        logger.info(f"🔥 START COMMAND RECEIVED from user {update.effective_user.id}")
        logger.info(f"🔥 Chat type: {update.effective_chat.type}")
        logger.info(f"🔥 Message text: {update.message.text}")
        
        try:
            await update.message.reply_text("🔥 DEBUG: /start command working!")
            logger.info("✅ START COMMAND RESPONSE SENT")
        except Exception as e:
            logger.error(f"❌ START COMMAND ERROR: {e}")
    
    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /test command - DEBUG VERSION"""
        logger.info(f"🔥 TEST COMMAND RECEIVED from user {update.effective_user.id}")
        
        try:
            await update.message.reply_text("🔥 DEBUG: /test command working!")
            logger.info("✅ TEST COMMAND RESPONSE SENT")
        except Exception as e:
            logger.error(f"❌ TEST COMMAND ERROR: {e}")
