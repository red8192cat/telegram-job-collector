"""
Error Monitoring System - Captures and notifies admin of errors
"""

import logging
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Optional
import traceback

class ErrorCollector:
    def __init__(self, bot_instance=None, admin_id=None):
        self.bot_instance = bot_instance
        self.admin_id = admin_id
        self.errors = []  # Store last 24h of errors
        self.error_counts = defaultdict(int)  # Count similar errors
        self.last_notification = None
        self.notification_sent = False  # Track if first error was sent
        self.batch_task = None
        
    def add_error(self, record: logging.LogRecord):
        """Add error to collection and handle notifications"""
        now = datetime.now()
        
        # Clean old errors (keep last 24h)
        self.cleanup_old_errors()
        
        # Extract meaningful error info
        error_info = {
            'timestamp': now,
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'filename': record.filename,
            'lineno': record.lineno,
            'funcName': record.funcName
        }
        
        self.errors.append(error_info)
        
        # Create short description for notifications
        short_desc = self._create_short_description(error_info)
        self.error_counts[short_desc] += 1
        
        # Handle notifications
        asyncio.create_task(self._handle_notification(error_info, short_desc))
    
    def _create_short_description(self, error_info: dict) -> str:
        """Create short but meaningful error description"""
        message = error_info['message']
        module = error_info['module']
        
        # Truncate long messages
        if len(message) > 100:
            message = message[:97] + "..."
        
        return f"{module}: {message}"
    
    async def _handle_notification(self, error_info: dict, short_desc: str):
        """Handle error notifications with smart batching"""
        if not self.bot_instance or not self.admin_id:
            return
        
        is_critical = error_info['level'] == 'CRITICAL'
        is_first_error = not self.notification_sent
        
        # Send immediately for first error or critical errors
        if is_first_error or is_critical:
            await self._send_immediate_notification(error_info, short_desc, is_critical)
            self.notification_sent = True
            self.last_notification = datetime.now()
            
            # Start batch timer if this was the first error
            if is_first_error and not is_critical:
                self._start_batch_timer()
        else:
            # For subsequent non-critical errors, batch them
            self._start_batch_timer()
    
    async def _send_immediate_notification(self, error_info: dict, short_desc: str, is_critical: bool):
        """Send immediate error notification"""
        try:
            emoji = "🚨" if is_critical else "⚠️"
            level = "CRITICAL" if is_critical else "ERROR"
            timestamp = error_info['timestamp'].strftime("%H:%M:%S")
            
            message = (
                f"{emoji} **{level} Alert**\n\n"
                f"🕐 {timestamp}\n"
                f"📍 {error_info['module']}.py:{error_info['lineno']}\n"
                f"📝 {error_info['message'][:200]}\n\n"
                f"Use `/admin errors` for details"
            )
            
            await self.bot_instance.send_message(
                chat_id=self.admin_id,
                text=message,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Failed to send error notification: {e}")
    
    def _start_batch_timer(self):
        """Start or restart the batch notification timer"""
        if self.batch_task and not self.batch_task.done():
            return  # Timer already running
        
        self.batch_task = asyncio.create_task(self._batch_notification_timer())
    
    async def _batch_notification_timer(self):
        """Wait 1 hour then send batched error notification"""
        await asyncio.sleep(3600)  # 1 hour
        
        # Count errors in the last hour
        hour_ago = datetime.now() - timedelta(hours=1)
        recent_errors = [e for e in self.errors if e['timestamp'] > hour_ago]
        
        if len(recent_errors) > 1:  # Only send if there are additional errors
            await self._send_batch_notification(recent_errors)
    
    async def _send_batch_notification(self, recent_errors: List[dict]):
        """Send batched error notification"""
        try:
            if not self.bot_instance or not self.admin_id:
                return
            
            # Count error types
            error_summary = defaultdict(int)
            critical_count = 0
            
            for error in recent_errors:
                short_desc = self._create_short_description(error)
                error_summary[short_desc] += 1
                if error['level'] == 'CRITICAL':
                    critical_count += 1
            
            # Create summary message
            start_time = min(e['timestamp'] for e in recent_errors).strftime("%H:%M")
            end_time = max(e['timestamp'] for e in recent_errors).strftime("%H:%M")
            
            message = f"📊 **Error Summary** ({start_time}-{end_time})\n\n"
            message += f"Total: {len(recent_errors)} errors"
            
            if critical_count > 0:
                message += f" ({critical_count} critical)"
            
            message += "\n\n"
            
            # List top error types (max 5)
            for desc, count in list(error_summary.items())[:5]:
                message += f"❌ {desc}"
                if count > 1:
                    message += f" ({count}x)"
                message += "\n"
            
            if len(error_summary) > 5:
                message += f"... and {len(error_summary) - 5} more\n"
            
            message += "\nUse `/admin errors` for full details"
            
            await self.bot_instance.send_message(
                chat_id=self.admin_id,
                text=message,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            print(f"Failed to send batch notification: {e}")
    
    def cleanup_old_errors(self):
        """Remove errors older than 24 hours"""
        cutoff = datetime.now() - timedelta(hours=24)
        self.errors = [e for e in self.errors if e['timestamp'] > cutoff]
    
    def get_recent_errors(self, hours: int = 24) -> List[dict]:
        """Get errors from the last N hours"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [e for e in self.errors if e['timestamp'] > cutoff]
    
    def get_error_stats(self) -> dict:
        """Get error statistics"""
        recent = self.get_recent_errors()
        critical_count = sum(1 for e in recent if e['level'] == 'CRITICAL')
        error_count = len(recent) - critical_count
        
        return {
            'total': len(recent),
            'critical': critical_count,
            'errors': error_count,
            'oldest': min((e['timestamp'] for e in recent), default=datetime.now())
        }


class ErrorHandler(logging.Handler):
    """Custom logging handler to capture errors"""
    
    def __init__(self, error_collector: ErrorCollector):
        super().__init__()
        self.error_collector = error_collector
        self.setLevel(logging.ERROR)  # Only capture ERROR and CRITICAL
    
    def emit(self, record):
        """Called when an error is logged"""
        try:
            # Skip if it's our own error notification code to avoid loops
            if 'error_monitor' in record.pathname or 'Failed to send' in record.getMessage():
                return
            
            self.error_collector.add_error(record)
        except Exception:
            # Don't let error handling break the application
            pass


# Global error collector instance
error_collector = None

def setup_error_monitoring(bot_instance, admin_id):
    """Setup error monitoring system"""
    global error_collector
    
    error_collector = ErrorCollector(bot_instance, admin_id)
    
    # Add our custom handler to the root logger
    error_handler = ErrorHandler(error_collector)
    logging.getLogger().addHandler(error_handler)
    
    return error_collector

def get_error_collector():
    """Get the global error collector instance"""
    return error_collector
