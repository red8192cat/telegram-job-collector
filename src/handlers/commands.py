# ADMIN COMMANDS
async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command with subcommands - ADMIN ONLY"""
    if not is_private_chat(update) or not update.message:
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
    if not is_private_chat(update) or not update.message:
        return
    
    # Security check - only authorized admin
    if not self._is_authorized_admin(update, context):
        await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
        return
    
    try:
        from utils.error_monitor import get_error_collector
        
        collector = get_error_collector()
        if not collector:
            await update.message.reply_text("❌ Error monitoring not initialized.")
            return
        
        # Get recent errors
        recent_errors = collector.get_recent_errors(24)
        stats = collector.get_error_stats()
        
        if not recent_errors:
            await update.message.reply_text("✅ **No errors in last 24 hours**\n\nBot is running smoothly!", parse_mode='Markdown')
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
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error retrieving error logs: {str(e)}")

# SECURE Authentication commands - ADMIN ONLY  
async def auth_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /auth_status command - ADMIN ONLY"""
    if not is_private_chat(update) or not update.message:
        return
    
    # Security check - only authorized admin
    if not self._is_authorized_admin(update, context):
        await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
        return
    
    user_monitor = getattr(context.bot_data, 'user_monitor', None)
    if not user_monitor:
        await update.message.reply_text("❌ User account monitoring is not enabled.")
        return
    
    status = user_monitor.get_auth_status()
    
    if status == "disabled":
        await update.message.reply_text("ℹ️ User account monitoring is disabled (no credentials configured).")
    elif status == "not_initialized":
        await update.message.reply_text("❌ User account monitoring failed to initialize.")
    elif status == "waiting_for_code":
        await update.message.reply_text("📱 **Waiting for SMS verification code**\n\nPlease send the code you received.", parse_mode='Markdown')
    elif status == "waiting_for_2fa":
        await update.message.reply_text("🔐 **Waiting for 2FA password**\n\nPlease send your two-factor authentication password.", parse_mode='Markdown')
    elif status == "authenticated":
        await update.message.reply_text("✅ **User account authenticated!**\n\nMonitoring is active and working.", parse_mode='Markdown')
    else:
        await update.message.reply_text("❓ Unknown status. Use /auth_restart to restart authentication.")

async def auth_restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /auth_restart command - ADMIN ONLY"""
    if not is_private_chat(update) or not update.message:
        return
    
    # Security check - only authorized admin
    if not self._is_authorized_admin(update, context):
        await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
        return
    
    chat_id = update.effective_chat.id
    
    user_monitor = getattr(context.bot_data, 'user_monitor', None)
    if not user_monitor:
        await update.message.reply_text("❌ User account monitoring is not enabled.")
        return
    
    try:
        success = await user_monitor.restart_auth(chat_id)
        if success:
            await update.message.reply_text("🔄 **Authentication restarted**\n\nCheck your phone for the verification code.", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Failed to restart authentication.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error restarting authentication: {str(e)}")