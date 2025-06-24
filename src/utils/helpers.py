"""
Helper utilities - Updated with new manage_keywords flow
All user-facing text is now translated
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from utils.translations import get_text, get_supported_languages

def create_language_selection_keyboard():
    """Create language selection keyboard"""
    keyboard = []
    languages = get_supported_languages()
    
    for lang_code, lang_info in languages.items():
        button_text = f"{lang_info['flag']} {lang_info['name']}"
        callback_data = f"lang_{lang_code}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    return InlineKeyboardMarkup(keyboard)

def create_main_menu(language: str = 'en'):
    """Create main menu with translated buttons - UPDATED with manage_keywords"""
    keyboard = [
        [InlineKeyboardButton(
            get_text("button_manage_keywords", language), 
            callback_data="menu_manage_keywords"
        )],
        [InlineKeyboardButton(
            get_text("button_my_settings", language), 
            callback_data="menu_show_settings"
        )],
        [InlineKeyboardButton(
            get_text("button_help", language), 
            callback_data="menu_help"
        )],
        [InlineKeyboardButton(
            get_text("button_language", language), 
            callback_data="menu_language"
        )]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_back_menu(language: str = 'en'):
    """Create back button menu"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            get_text("button_back", language), 
            callback_data="menu_back"
        )
    ]])

def create_manage_keywords_keyboard(has_keywords: bool, has_ignore: bool, language: str = 'en'):
    """Create keyboard for manage keywords with conditional buttons"""
    keyboard = []
    
    # Always show set keywords button
    keyboard.append([InlineKeyboardButton(
        get_text("button_set_keywords", language),
        callback_data="manage_set_keywords"
    )])
    
    # Show ignore buttons if user has keywords
    if has_keywords:
        keyboard.append([InlineKeyboardButton(
            get_text("button_set_ignore", language),
            callback_data="manage_set_ignore"
        )])
        
        # Show clear ignore only if user has ignore keywords
        if has_ignore:
            keyboard.append([InlineKeyboardButton(
                get_text("button_clear_ignore", language),
                callback_data="manage_clear_ignore"
            )])
        
        # Show stop monitoring if user has keywords
        keyboard.append([InlineKeyboardButton(
            get_text("button_stop_monitoring", language),
            callback_data="manage_stop_monitoring"
        )])
    
    # Always show back button
    keyboard.append([InlineKeyboardButton(
        get_text("button_back", language),
        callback_data="menu_back"
    )])
    
    return InlineKeyboardMarkup(keyboard)

def create_stop_monitoring_keyboard(language: str = 'en'):
    """Create confirmation keyboard for stop monitoring"""
    keyboard = [
        [InlineKeyboardButton(
            get_text("button_confirm_stop", language),
            callback_data="confirm_stop_monitoring"
        )],
        [InlineKeyboardButton(
            get_text("button_cancel", language),
            callback_data="menu_manage_keywords"
        )]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_resume_monitoring_keyboard(language: str = 'en'):
    """Create keyboard for resuming monitoring"""
    keyboard = [
        [InlineKeyboardButton(
            get_text("button_resume_monitoring", language),
            callback_data="menu_manage_keywords"
        )],
        [InlineKeyboardButton(
            get_text("button_back", language),
            callback_data="menu_back"
        )]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_keywords_help_keyboard(language: str = 'en'):
    """Create keyboard for keywords help with pre-fill button and back button"""
    keyboard = [
        [InlineKeyboardButton(
            get_text("button_fill_keywords", language),
            switch_inline_query_current_chat="/keywords "
        )],
        [InlineKeyboardButton(
            get_text("button_back", language), 
            callback_data="menu_manage_keywords"
        )]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_ignore_keywords_help_keyboard(language: str = 'en'):
    """Create keyboard for ignore keywords help with pre-fill and back buttons"""
    keyboard = [
        [InlineKeyboardButton(
            get_text("button_fill_ignore", language),
            switch_inline_query_current_chat="/ignore_keywords "
        )],
        [InlineKeyboardButton(
            get_text("button_back", language),
            callback_data="menu_manage_keywords"
        )]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_settings_keyboard(has_keywords: bool, language: str = 'en'):
    """Create keyboard for settings view"""
    keyboard = []
    
    if has_keywords:
        keyboard.append([InlineKeyboardButton(
            get_text("button_manage_keywords", language),
            callback_data="menu_manage_keywords"
        )])
    else:
        keyboard.append([InlineKeyboardButton(
            get_text("button_start_monitoring", language),
            callback_data="menu_manage_keywords"
        )])
    
    keyboard.append([InlineKeyboardButton(
        get_text("button_back", language),
        callback_data="menu_back"
    )])
    
    return InlineKeyboardMarkup(keyboard)

def is_private_chat(update: Update) -> bool:
    """Check if message is from private chat"""
    return update.effective_chat.type == 'private'

def get_help_text(language: str = 'en'):
    """Get comprehensive help text with contact info included"""
    return get_text("help_text", language)

def format_manage_keywords_message(keywords, ignore_keywords, language: str = 'en'):
    """Format manage keywords message with current status"""
    if keywords:
        keywords_str = ', '.join(keywords)
        ignore_str = ', '.join(ignore_keywords) if ignore_keywords else 'None'
        return get_text("manage_keywords_with_data", language, 
                       keywords=keywords_str, ignore=ignore_str)
    else:
        return get_text("manage_keywords_no_data", language)

def format_settings_message(keywords, ignore_keywords, language: str = 'en'):
    """Format settings message with translations"""
    msg = get_text("settings_title", language) + "\n\n"
    
    if keywords:
        keywords_str = ', '.join(keywords)
        msg += get_text("settings_keywords", language, keywords=keywords_str) + "\n"
    else:
        msg += get_text("settings_keywords_none", language) + "\n"
    
    if ignore_keywords:
        ignore_str = ', '.join(ignore_keywords)
        msg += get_text("settings_ignore_keywords", language, keywords=ignore_str) + "\n\n"
    else:
        msg += get_text("settings_ignore_keywords_none", language) + "\n\n"
    
    # Add status information
    if keywords:
        msg += get_text("settings_status_monitoring", language) + "\n\n"
    else:
        msg += get_text("settings_status_not_monitoring", language) + "\n\n"
    
    msg += get_text("settings_quick_commands", language)
    
    return msg