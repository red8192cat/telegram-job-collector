#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot - PRODUCTION VERSION
Clean architecture with event system, configuration management, and graceful degradation
"""

import asyncio
import logging
import sys
import signal
from telegram.ext import Application

from config import BotConfig
from events import get_event_bus, EventType, emit_system_status
from handlers.commands import CommandHandlers
from handlers.callbacks import CallbackHandlers
from handlers.messages import MessageHandlers
from storage.sqlite_manager import SQLiteManager

logger = logging.getLogger(__name__)

class JobCollectorBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
        self.event_bus = get_event_bus()
        
        # Core components
        self.data_manager = SQLiteManager(config)
        self.command_handlers = CommandHandlers(config, self.data_manager)
        self.callback_handlers = CallbackHandlers(config, self.data_manager)
        self.message_handlers = MessageHandlers(config, self.data_manager)
        
        # User monitor (optional)
        self.user_monitor = None
        self._user_monitor_task = None
        self.mode = "initializing"  # "full", "bot-only", "degraded"
        
        # Background tasks
        self._background_tasks = []
        self._shutdown_event = asyncio.Event()
        
        # Register handlers
        self.register_handlers()
        
        # Subscribe to events
        self.subscribe_to_events()
        
    def register_handlers(self):
        """Register all command and message handlers"""
        self.command_handlers.register(self.app)
        self.callback_handlers.register(self.app)
        self.message_handlers.register(self.app)
        logger.info("✅ All core handlers registered successfully")
    
    def subscribe_to_events(self):
        """Subscribe to relevant events"""
        # System events
        self.event_bus.subscribe(EventType.SYSTEM_ERROR, self.handle_system_error)
        self.event_bus.subscribe(EventType.USER_MONITOR_ERROR, self.handle_user_monitor_error)
        self.event_bus.subscribe(EventType.USER_MONITOR_DISCONNECTED, self.handle_user_monitor_disconnected)