"""
Helper utilities - Menu creation and validation functions
Updated with new keyword system (no quotes)
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

def create_main_menu():
    """Create main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("🎯 Set Keywords", callback_data="menu_keywords")],
        [InlineKeyboardButton("🚫 Set Ignore Keywords", callback_data="menu_ignore")],
        [InlineKeyboardButton("📝 My Keywords", callback_data="menu_show_keywords"),
         InlineKeyboardButton("📋 My Ignore List", callback_data="menu_show_ignore")],
        [InlineKeyboardButton("💬 Contact Admin", callback_data="menu_contact")],
        [InlineKeyboardButton("❓ Help", callback_data="menu_help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_back_menu():
    """Create back button menu"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]])

def is_private_chat(update: Update) -> bool:
    """Check if message is from private chat"""
    return update.effective_chat.type == 'private'

def get_help_text():
    """Get comprehensive help text - UPDATED for new system"""
    return (
        "📋 Available Commands:\n\n"
        "🎯 Keywords Management:\n"
        "/keywords <word1, word2, ...> - Set your keywords (overwrites)\n"
        "/add_keyword_to_list <keyword> - Add a keyword\n"
        "/delete_keyword_from_list <keyword> - Remove a keyword\n"
        "/my_keywords - Show your current keywords\n\n"
        "🚫 Ignore Keywords:\n"
        "/ignore_keywords <word1, word2, ...> - Set ignore keywords (overwrites)\n"
        "/add_ignore_keyword <keyword> - Add ignore keyword\n"
        "/delete_ignore_keyword <keyword> - Remove ignore keyword\n"
        "/my_ignore - Show ignore keywords\n"
        "/purge_ignore - Clear all ignore keywords\n\n"
        "📊 Other Commands:\n"
        "/menu - Show interactive menu\n"
        "/help - Show this help message\n\n"
        "💡 Keyword Types:\n"
        "• Required: [remote*], [remote*|online*] (MUST be in every message)\n"
        "• Single: python, java, linux (exact words)\n"
        "• Wildcard: develop*, engineer*, support* (word variations)\n"
        "• Phrases: support* engineer*, senior* develop* (adjacent words)\n"
        "• AND: python+django (both must be present - advanced)\n\n"
        "Examples:\n"
        "• /keywords [remote*|online*], python, develop*, support* engineer*\n"
        "• /ignore_keywords javascript*, manage*, senior*\n\n"
        "🎯 Logic: (ALL required) AND (at least one optional)\n"
        "📝 Use * for wildcards, exact words for precision (java vs javascript)"
    )

def get_keywords_help():
    """Get keywords help text - UPDATED for new system"""
    return (
        "🎯 To set keywords, use commas to separate them:\n"
        "/keywords [remote*|online*], python, develop*, support* engineer*\n\n"
        "Types:\n"
        "• Required: [remote*] (MUST be in every message)\n"
        "• Required OR: [remote*|online*] (either must be present)\n"
        "• Exact: python, java, linux\n"
        "• Wildcard: develop*, engineer* (matches variations)\n"
        "• Phrases: support* engineer* (adjacent words)\n"
        "• AND: python+django (advanced - both required)\n\n"
        "💡 Logic: (ALL required) AND (at least one optional)\n"
        "✨ No quotes needed - just use commas!"
    )

def get_ignore_help():
    """Get ignore keywords help text - UPDATED for new system"""
    return (
        "🚫 To set ignore keywords, use commas to separate them:\n"
        "/ignore_keywords javascript*, manage*, senior*\n\n"
        "💡 Same rules as regular keywords:\n"
        "• Exact: java, php, manager\n"
        "• Wildcard: manage*, senior*, lead*\n"
        "• Phrases: team* lead*, project* manager*\n\n"
        "🗑️ Use /purge_ignore to clear all ignore keywords"
    )

def get_add_keyword_help():
    """Get add keyword help text - UPDATED for new system"""
    return (
        "Please provide a keyword:\n"
        "/add_keyword_to_list [remote*|online*]\n"
        "/add_keyword_to_list python+django\n"
        "/add_keyword_to_list support* engineer*\n"
        "/add_keyword_to_list develop*\n\n"
        "💡 Use * for wildcards, commas not needed for single keywords"
    )

def get_set_keywords_help():
    """Get set keywords help text - UPDATED for new system"""
    return (
        "Please provide keywords separated by commas:\n"
        "/keywords [remote*|online*], python, develop*, support* engineer*\n\n"
        "• Use commas to separate keywords\n"
        "• Use [brackets] for REQUIRED keywords\n"
        "• Use * for wildcards (develop* = developer, development)\n"
        "• Use spaces for phrases (support* engineer*)\n"
        "• No quotes needed!\n\n"
        "Examples:\n"
        "• /keywords java, python, develop*\n"
        "• /keywords [remote*], senior* develop*, react\n"
        "• /keywords support* engineer*, linux*, python"
    )

def get_contact_info():
    """Get contact information text"""
    return (
        "💬 Need Help?\n\n"
        "For support, questions, or feedback:\n\n"
        "👤 Contact the admin mentioned in the bot description\n\n"
        "We're here to help! 😊"
    )