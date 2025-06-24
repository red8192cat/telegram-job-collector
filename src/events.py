"""
Event System for Decoupled Communication
Production-ready event bus with error handling and logging
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Callable, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class EventType(Enum):
    """Predefined event types for type safety"""
    
    # Job processing events
    JOB_MESSAGE_RECEIVED = "job_message_received"
    JOB_MESSAGE_PROCESSED = "job_message_processed"
    JOB_MESSAGE_FORWARDED = "job_message_forwarded"
    
    # User events
    USER_KEYWORDS_UPDATED = "user_keywords_updated"
    USER_LANGUAGE_CHANGED = "user_language_changed"
    USER_REGISTERED = "user_registered"
    
    # Channel events
    CHANNEL_ADDED = "channel_added"
    CHANNEL_REMOVED = "channel_removed"
    CHANNEL_VALIDATED = "channel_validated"
    CHANNEL_ACCESS_LOST = "channel_access_lost"
    
    # User monitor events
    USER_MONITOR_CONNECTED = "user_monitor_connected"
    USER_MONITOR_DISCONNECTED = "user_monitor_disconnected"
    USER_MONITOR_AUTH_REQUIRED = "user_monitor_auth_required"
    USER_MONITOR_AUTH_SUCCESS = "user_monitor_auth_success"
    USER_MONITOR_ERROR = "user_monitor_error"
    
    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_HEALTH_CHECK = "system_health_check"
    SYSTEM_ERROR = "system_error"
    SYSTEM_DEGRADED = "system_degraded"
    
    # Admin events
    ADMIN_COMMAND_EXECUTED = "admin_command_executed"
    CONFIG_UPDATED = "config_updated"
    BACKUP_CREATED = "backup_created"

@dataclass
class Event:
    """Event data structure"""
    type: EventType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "unknown"
    correlation_id: Optional[str] = None  # For tracking related events
    
    def __str__(self) -> str:
        return f"Event({self.type.value}, source={self.source}, data_keys={list(self.data.keys())})"

class EventBus:
    """
    Asynchronous event bus for decoupled communication between modules
    """
    
    def __init__(self, max_concurrent_handlers: int = 10):
        self._handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._event_history: List[Event] = []
        self._max_history = 1000  # Keep last 1000 events
        self._semaphore = asyncio.Semaphore(max_concurrent_handlers)
        self._stats = {
            'events_emitted': 0,
            'events_processed': 0,
            'handler_errors': 0
        }
    
    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """
        Subscribe to events of a specific type
        
        Args:
            event_type: Type of event to subscribe to
            handler: Async function to handle the event (takes Event as parameter)
        """
        self._handlers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type.value}: {handler.__name__}")
    
    def unsubscribe(self, event_type: EventType, handler: Callable) -> bool:
        """
        Unsubscribe handler from event type
        
        Returns:
            True if handler was found and removed, False otherwise
        """
        try:
            self._handlers[event_type].remove(handler)
            logger.debug(f"Handler unsubscribed from {event_type.value}: {handler.__name__}")
            return True
        except ValueError:
            return False
    
    async def emit(self, 
                   event_type: EventType, 
                   data: Dict[str, Any], 
                   source: str = "unknown",
                   correlation_id: Optional[str] = None) -> None:
        """
        Emit an event to all subscribers
        
        Args:
            event_type: Type of event
            data: Event data
            source: Source module/component that emitted the event
            correlation_id: Optional ID to correlate related events
        """
        event = Event(
            type=event_type,
            data=data.copy(),  # Copy to prevent mutation
            source=source,
            correlation_id=correlation_id
        )
        
        self._stats['events_emitted'] += 1
        self._add_to_history(event)
        
        logger.debug(f"Emitting event: {event}")
        
        # Get handlers for this event type
        handlers = self._handlers[event_type].copy()  # Copy to prevent modification during iteration
        
        if not handlers:
            logger.debug(f"No handlers for event type: {event_type.value}")
            return
        
        # Execute all handlers concurrently but with semaphore limit
        tasks = []
        for handler in handlers:
            task = asyncio.create_task(self._execute_handler(handler, event))
            tasks.append(task)
        
        if tasks:
            # Wait for all handlers to complete
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _execute_handler(self, handler: Callable, event: Event) -> None:
        """Execute a single event handler with error handling"""
        async with self._semaphore:
            try:
                handler_name = getattr(handler, '__name__', str(handler))
                logger.debug(f"Executing handler {handler_name} for event {event.type.value}")
                
                # Execute handler
                await handler(event)
                
                self._stats['events_processed'] += 1
                logger.debug(f"Handler {handler_name} completed successfully")
                
            except Exception as e:
                self._stats['handler_errors'] += 1
                logger.error(f"Error in event handler {handler_name} for event {event.type.value}: {e}")
                
                # Emit error event (but don't create infinite loops)
                if event.type != EventType.SYSTEM_ERROR:
                    try:
                        await self.emit(EventType.SYSTEM_ERROR, {
                            'error': str(e),
                            'handler': handler_name,
                            'original_event': event.type.value,
                            'source_event_data': event.data
                        }, source='event_bus')
                    except Exception:
                        # If we can't even emit error events, just log
                        logger.critical(f"Failed to emit error event for handler failure: {e}")
    
    def _add_to_history(self, event: Event) -> None:
        """Add event to history, maintaining size limit"""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)  # Remove oldest
    
    def get_recent_events(self, event_type: Optional[EventType] = None, 
                         limit: int = 100) -> List[Event]:
        """
        Get recent events, optionally filtered by type
        
        Args:
            event_type: Optional filter by event type
            limit: Maximum number of events to return
            
        Returns:
            List of recent events (newest first)
        """
        events = self._event_history[-limit:] if limit else self._event_history
        
        if event_type:
            events = [e for e in events if e.type == event_type]
        
        return list(reversed(events))  # Newest first
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        handler_count = sum(len(handlers) for handlers in self._handlers.values())
        
        return {
            **self._stats,
            'total_handlers': handler_count,
            'event_types_with_handlers': len(self._handlers),
            'event_history_size': len(self._event_history),
            'handlers_by_type': {
                event_type.value: len(handlers) 
                for event_type, handlers in self._handlers.items()
            }
        }
    
    def clear_history(self) -> None:
        """Clear event history (useful for memory management)"""
        self._event_history.clear()
        logger.info("Event history cleared")
    
    def get_handlers(self, event_type: EventType) -> List[Callable]:
        """Get list of handlers for an event type (for debugging)"""
        return self._handlers[event_type].copy()


# Global event bus instance
_event_bus: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    """Get the global event bus instance"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus

def set_event_bus(event_bus: EventBus) -> None:
    """Set the global event bus instance (useful for testing)"""
    global _event_bus
    _event_bus = event_bus


# Convenience functions for common event patterns

async def emit_job_received(message_text: str, channel_id: int, message_id: int, 
                           source: str, correlation_id: Optional[str] = None) -> None:
    """Emit job message received event"""
    await get_event_bus().emit(EventType.JOB_MESSAGE_RECEIVED, {
        'message_text': message_text,
        'channel_id': channel_id,
        'message_id': message_id,
        'timestamp': datetime.now().isoformat()
    }, source=source, correlation_id=correlation_id)

async def emit_job_forwarded(user_id: int, channel_id: int, message_id: int,
                            keywords_matched: List[str], source: str,
                            correlation_id: Optional[str] = None) -> None:
    """Emit job forwarded event"""
    await get_event_bus().emit(EventType.JOB_MESSAGE_FORWARDED, {
        'user_id': user_id,
        'channel_id': channel_id,
        'message_id': message_id,
        'keywords_matched': keywords_matched,
        'timestamp': datetime.now().isoformat()
    }, source=source, correlation_id=correlation_id)

async def emit_user_monitor_status(status: str, details: str = "", 
                                  error: Optional[str] = None) -> None:
    """Emit user monitor status change"""
    if status == "connected":
        event_type = EventType.USER_MONITOR_CONNECTED
    elif status == "disconnected":
        event_type = EventType.USER_MONITOR_DISCONNECTED
    elif status == "auth_required":
        event_type = EventType.USER_MONITOR_AUTH_REQUIRED
    elif status == "auth_success":
        event_type = EventType.USER_MONITOR_AUTH_SUCCESS
    else:
        event_type = EventType.USER_MONITOR_ERROR
    
    await get_event_bus().emit(event_type, {
        'status': status,
        'details': details,
        'error': error,
        'timestamp': datetime.now().isoformat()
    }, source='user_monitor')

async def emit_system_status(status: str, details: str = "", 
                            component: str = "system") -> None:
    """Emit system status change"""
    if status == "startup":
        event_type = EventType.SYSTEM_STARTUP
    elif status == "shutdown":
        event_type = EventType.SYSTEM_SHUTDOWN
    elif status == "degraded":
        event_type = EventType.SYSTEM_DEGRADED
    elif status == "error":
        event_type = EventType.SYSTEM_ERROR
    else:
        event_type = EventType.SYSTEM_HEALTH_CHECK
    
    await get_event_bus().emit(event_type, {
        'status': status,
        'details': details,
        'component': component,
        'timestamp': datetime.now().isoformat()
    }, source=component)