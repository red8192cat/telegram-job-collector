"""
Helper utilities - Menu creation and validation functions
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
    """Get comprehensive help text"""
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
        "• Required: [remote], [remote|online] (MUST be in every message)\n"
        "• Single: python, javascript, linux\n"
        "• AND: python+junior+remote (all 3 must be present)\n"
        "• Exact: \"project manager\" (exact order)\n"
        "• Wildcard: manag* (matches manager, managing, management)\n"
        "• Mixed: [remote|online], python+\"project manag*\", linux\n"
        "• Ignore keywords help filter out unwanted messages\n\n"
        "🎯 Logic: (ALL required) AND (at least one optional)\n"
        "📝 Required OR: [remote|online] = 'remote' OR 'online' must be present\n"
        "Example: [remote|online], linux, python → needs ('remote' OR 'online') AND ('linux' OR 'python')"
    )

def get_keywords_help():
    """Get keywords help text"""
    return (
        "🎯 To set keywords, use:\n"
        "/keywords [remote|online], python, \"project manag*\"\n"
        "/keywords [remote], [senior|lead], python+\"data scientist\"\n\n"
        "Types:\n"
        "• Required: [remote] (MUST be in every message)\n"
        "• Required OR: [remote|online] (either must be present)\n"
        "• Single: python\n"
        "• AND: python+junior\n"
        "• Exact: \"project manager\"\n"
        "• Wildcard: manag*\n"
        "• Mixed: [remote|online], python+\"data manag*\"\n\n"
        "💡 Logic: (ALL required) AND (at least one optional)"
    )

def get_ignore_help():
    """Get ignore keywords help text"""
    return (
        "🚫 To set ignore keywords, use:\n"
        "/ignore_keywords java, php, senior\n\n"
        "💡 /ignore_keywords overwrites your current list\n"
        "🗑️ Use /purge_ignore to clear all ignore keywords"
    )

def get_add_keyword_help():
    """Get add keyword help text"""
    return (
        "Please provide a keyword:\n"
        "/add_keyword_to_list [remote|online]\n"
        "/add_keyword_to_list python+junior+remote\n"
        "/add_keyword_to_list \"project manag*\"\n"
        "/add_keyword_to_list develop*"
    )

def get_set_keywords_help():
    """Get set keywords help text"""
    return (
        "Please provide keywords:\n"
        "/keywords [remote|online], python, \"project manag*\"\n"
        "/keywords [remote], [senior|lead], python+\"data scientist\"\n\n"
        "• Use [brackets] for REQUIRED keywords (must be in every message)\n"
        "• Use [word1|word2] for required OR (either word1 OR word2 must be present)\n"
        "• Use + for AND logic (all parts must be present)\n"
        "• Use \"quotes\" for exact phrases in order\n"
        "• Use * for wildcards at word endings\n"
        "• Logic: (ALL required) AND (at least one optional)"
    )

def get_contact_info():
    """Get contact information text"""
    return (
        "💬 Need Help?\n\n"
        "For support, questions, or feedback:\n\n"
        "👤 Contact the admin mentioned in the bot description\n\n"
        "We're here to help! 😊"
    )
