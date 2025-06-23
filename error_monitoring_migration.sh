#!/bin/bash

# Telegram Job Collector Bot - Error Monitoring Migration Script
# Adds comprehensive error monitoring with admin notifications

set -e  # Exit on any error

echo "🚨 Starting Error Monitoring Migration..."
echo "📊 Adding admin error monitoring and notification system"
echo ""

# Create backup
#echo "📦 Creating backup of current files..."
#mkdir -p migration_backup_errors
#cp -r src/ migration_backup_errors/ 2>/dev/null || true
#echo "✅ Backup created in migration_backup_errors/"
#echo ""

# Create error monitoring utility
echo "🔧 Creating error monitoring system..."
mkdir -p src/utils
cat > src/utils/error_monitor.py << 'EOF'
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
EOF
echo "✅ Error monitoring system created"

# Update commands.py to add admin commands
echo "🔧 Adding admin commands to command handlers..."

# Backup current commands.py
cp src/handlers/commands.py src/handlers/commands.py.backup

# Add admin command handler to commands.py
cat >> src/handlers/commands.py << 'EOF'

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command with subcommands - ADMIN ONLY"""
        if not is_private_chat(update):
            return
        
        # Security check - only authorized admin
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📋 **Admin Commands**\n\n"
                "• `/admin errors` - Show recent errors\n"
                "• `/admin stats` - Bot statistics (coming soon)\n",
                parse_mode='Markdown'
            )
            return
        
        subcommand = context.args[0].lower()
        
        if subcommand == "errors":
            await self.admin_errors_command(update, context)
        else:
            await update.message.reply_text(f"❓ Unknown admin command: {subcommand}")

    async def admin_errors_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin errors command - ADMIN ONLY"""
        if not is_private_chat(update):
            return
        
        # Security check - only authorized admin
        if not self._is_authorized_admin(update, context):
            await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
        
        from utils.error_monitor import get_error_collector
        
        collector = get_error_collector()
        if not collector:
            await update.message.reply_text("❌ Error monitoring not initialized.")
            return
        
        # Get recent errors
        recent_errors = collector.get_recent_errors(24)
        stats = collector.get_error_stats()
        
        if not recent_errors:
            await update.message.reply_text("✅ **No errors in last 24 hours**\n\nBot is running smoothly!")
            return
        
        # Format error list
        message = f"📋 **Recent Errors** (Last 24h)\n\n"
        message += f"📊 Total: {stats['total']} ({stats['critical']} critical)\n\n"
        
        # Show last 10 errors
        for error in recent_errors[-10:]:
            timestamp = error['timestamp'].strftime("%H:%M:%S")
            level_emoji = "🚨" if error['level'] == 'CRITICAL' else "❌"
            
            message += f"{level_emoji} {timestamp} - {error['level']}\n"
            message += f"📍 {error['module']}.py:{error['lineno']} in {error['funcName']}\n"
            message += f"📝 {error['message'][:150]}\n\n"
            
            # Telegram message limit
            if len(message) > 3500:
                message += f"... and {len(recent_errors) - len(recent_errors[-10:])} more errors\n"
                break
        
        if len(recent_errors) > 10:
            message += f"Showing last 10 of {len(recent_errors)} errors"
        
        await update.message.reply_text(message, parse_mode='Markdown')
EOF

# Add admin command registration to the register method
sed -i '/app.add_handler(CommandHandler("auth_restart", self.auth_restart_command))/a\        \n        # Admin commands\n        app.add_handler(CommandHandler("admin", self.admin_command))' src/handlers/commands.py

echo "✅ Admin commands added to command handlers"

# Update bot.py to initialize error monitoring
echo "🔧 Updating main bot to initialize error monitoring..."

# Backup current bot.py
cp src/bot.py src/bot.py.backup

# Add error monitoring initialization to bot.py
sed -i '/logger.info("Core bot functionality ready")/a\        \n        # Initialize error monitoring\n        if self.user_monitor and hasattr(self.user_monitor, "authorized_admin_id") and self.user_monitor.authorized_admin_id:\n            from utils.error_monitor import setup_error_monitoring\n            setup_error_monitoring(self.app.bot, self.user_monitor.authorized_admin_id)\n            logger.info("Error monitoring initialized")' src/bot.py

echo "✅ Error monitoring initialization added to bot"

# Update .env.example to document admin ID requirement
echo "📝 Updating .env.example..."
if ! grep -q "AUTHORIZED_ADMIN_ID" .env.example 2>/dev/null; then
    cat >> .env.example << 'EOF'

# SECURITY: Your Telegram User ID (for admin commands and error notifications)
# Get your ID by messaging @userinfobot on Telegram
# AUTHORIZED_ADMIN_ID=7896390402
EOF
fi
echo "✅ .env.example updated"

echo ""
echo "🎉 Error Monitoring Migration completed successfully!"
echo ""
echo "📋 Summary of changes:"
echo "   ✅ Added error monitoring system (src/utils/error_monitor.py)"
echo "   ✅ Added /admin and /admin errors commands"
echo "   ✅ Smart error notifications (immediate first/critical, hourly batches)"
echo "   ✅ 24-hour in-memory error storage"
echo "   ✅ Admin-only security for error commands"
echo ""
echo "🔧 Error Notification Strategy:"
echo "   📱 First error → Immediate notification"
echo "   🚨 Critical errors → Always immediate"
echo "   📊 Other errors → Batched every hour"
echo "   🧠 Memory → Last 24h only (auto-cleanup)"
echo ""
echo "📱 New Admin Commands:"
echo "   • /admin - Show admin commands"
echo "   • /admin errors - View recent errors"
echo ""
echo "⚠️  IMPORTANT Setup Required:"
echo "   1. Get your Telegram User ID from @userinfobot"
echo "   2. Add AUTHORIZED_ADMIN_ID=your_id to .env"
echo "   3. Deploy the bot"
echo "   4. You'll get notified of any errors automatically!"
echo ""
echo "🚀 Next steps:"
echo "   1. Add AUTHORIZED_ADMIN_ID to your .env"
echo "   2. git add . && git commit -m 'Add error monitoring system'"
echo "   3. git push"
echo "   4. Deploy: docker-compose down && git pull && docker-compose build && docker-compose up -d"
echo ""
echo "✨ You'll now get instant error alerts and can check /admin errors anytime!"
