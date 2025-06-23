"""
Helper utilities - Enhanced with command pre-fill functionality
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

def create_main_menu():
    """Create simplified main menu keyboard with merged settings"""
    keyboard = [
        [InlineKeyboardButton("🎯 Set Keywords", callback_data="menu_keywords")],
        [InlineKeyboardButton("🚫 Set Ignore Keywords", callback_data="menu_ignore")],
        [InlineKeyboardButton("⚙️ My Settings", callback_data="menu_show_settings")],
        [InlineKeyboardButton("❓ Help & Contact", callback_data="menu_help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_back_menu():
    """Create back button menu"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]])

def create_keywords_menu_with_prefill():
    """Create keywords help menu with pre-fill buttons"""
    keyboard = [
        [InlineKeyboardButton("📝 Try Basic Keywords", 
                            switch_inline_query_current_chat="/keywords python, remote, developer")],
        [InlineKeyboardButton("🎯 Try Advanced Keywords", 
                            switch_inline_query_current_chat="/keywords [remote*], python, develop*")],
        [InlineKeyboardButton("💼 Try Job-Specific", 
                            switch_inline_query_current_chat="/keywords [remote*], react, frontend")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_ignore_menu_with_prefill():
    """Create ignore keywords help menu with pre-fill buttons"""
    keyboard = [
        [InlineKeyboardButton("🚫 Try Common Blocks", 
                            switch_inline_query_current_chat="/ignore_keywords manager, senior, lead")],
        [InlineKeyboardButton("💼 Try Tech Blocks", 
                            switch_inline_query_current_chat="/ignore_keywords java*, php*, .net*")],
        [InlineKeyboardButton("🏢 Try Role Blocks", 
                            switch_inline_query_current_chat="/ignore_keywords director*, vp*, chief*")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def is_private_chat(update: Update) -> bool:
    """Check if message is from private chat"""
    return update.effective_chat.type == 'private'

def get_help_text():
    """Get comprehensive help text with contact info included"""
    return (
        "📋 Job Collector Bot Help\n\n"
        "🎯 Main Commands:\n"
        "• /start - Show main menu and welcome message\n"
        "• /keywords <list> - Set your search keywords (overwrites)\n"
        "• /ignore_keywords <list> - Set ignore keywords (overwrites)\n"
        "• /my_settings - Show your current keywords and ignore list\n"
        "• /purge_ignore - Clear all ignore keywords\n"
        "• /help - Show this help message\n\n"
        "💡 Keyword Types:\n"
        "• Required: [remote*], [remote*|online*] (MUST be in every message)\n"
        "• Exact: python, java, linux (exact words only)\n"
        "• Wildcard: develop*, engineer* (word variations)\n"
        "• Phrases: support* engineer*, senior* develop* (adjacent words)\n"
        "• AND: python+django (both required - advanced)\n\n"
        "📝 Examples:\n"
        "• /keywords [remote*|online*], python, develop*, support* engineer*\n"
        "• /ignore_keywords javascript*, manage*, senior*\n\n"
        "🎯 Logic: (ALL required) AND (at least one optional)\n"
        "✨ Tip: Use * for wildcards, exact words for precision (java vs javascript)\n\n"
        "💬 Need Help?\n"
        "For support, questions, or feedback, contact the admin mentioned in the bot description. We're here to help! 😊\n\n"
        "🚀 How it works:\n"
        "1. Set your keywords with the types you want\n"
        "2. Bot monitors configured channels for job posts\n"
        "3. Matching jobs are forwarded to you instantly\n"
        "4. Use ignore keywords to filter out unwanted posts"
    )

def get_keywords_help():
    """Get keywords help text for menu"""
    return (
        "🎯 Set Keywords\n\n"
        "Use commas to separate keywords:\n\n"
        "Types:\n"
        "• Required: [remote*] (MUST be in every message)\n"
        "• Required OR: [remote*|online*] (either must be present)\n"
        "• Exact: python, java, linux\n"
        "• Wildcard: develop*, engineer* (matches variations)\n"
        "• Phrases: support* engineer* (adjacent words)\n"
        "• AND: python+django (advanced - both required)\n\n"
        "💡 Logic: (ALL required) AND (at least one optional)\n"
        "✨ No quotes needed - just use commas!\n\n"
        "👇 Tap a button below to try examples:"
    )

def get_ignore_help():
    """Get ignore keywords help text for menu"""
    return (
        "🚫 Set Ignore Keywords\n\n"
        "Use commas to separate ignore keywords:\n\n"
        "Same rules as regular keywords:\n"
        "• Exact: java, php, manager\n"
        "• Wildcard: manage*, senior*, lead*\n"
        "• Phrases: team* lead*, project* manager*\n\n"
        "These will block job posts even if they match your keywords.\n\n"
        "🗑️ Use /purge_ignore to clear all ignore keywords\n\n"
        "👇 Tap a button below to try examples:"
    )

def get_set_keywords_help():
    """Get set keywords help text for command"""
    return (
        "Please provide keywords separated by commas:\n\n"
        "💡 **Quick Start Examples** (tap to use):\n"
        "`/keywords python, remote, developer`\n"
        "`/keywords [remote*], react, frontend`\n"
        "`/keywords java, backend, api`\n\n"
        "• Use commas to separate keywords\n"
        "• Use [brackets] for REQUIRED keywords\n"
        "• Use asterisk for wildcards (develop* = developer, development)\n"
        "• Use spaces for phrases (support* engineer*)\n"
        "• No quotes needed!\n\n"
        "Advanced Examples:\n"
        "• /keywords [remote*], senior* develop*, react\n"
        "• /keywords support* engineer*, linux*, python"
    )