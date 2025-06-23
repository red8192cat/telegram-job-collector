#!/bin/bash

# Fix Bot Menu Commands Script
# Adds multi-language support to the bot menu (commands next to send button)

set -e

echo "🤖 Fixing bot menu commands for multi-language support..."

# 1. Add menu command translations to languages.json
echo "📝 Adding menu command translations..."

# Create a backup
cp data/config/languages.json data/config/languages.json.bak
echo "📋 Created backup: languages.json.bak"

# Add menu command translations using Python to properly merge JSON
python3 << 'EOF'
import json

# Load current languages file
with open('data/config/languages.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Add menu command translations
menu_translations = {
    "menu_command_start": {
        "en": "🚀 Show main menu",
        "ru": "🚀 Показать главное меню"
    },
    "menu_command_keywords": {
        "en": "🎯 Set search keywords",
        "ru": "🎯 Установить ключевые слова"
    },
    "menu_command_ignore": {
        "en": "🚫 Set ignore keywords", 
        "ru": "🚫 Установить игнорируемые слова"
    },
    "menu_command_settings": {
        "en": "⚙️ Show current settings",
        "ru": "⚙️ Показать текущие настройки"
    },
    "menu_command_purge": {
        "en": "🗑️ Clear all ignore keywords",
        "ru": "🗑️ Очистить все игнорируемые слова"
    },
    "menu_command_help": {
        "en": "❓ Show help",
        "ru": "❓ Показать помощь"
    }
}

# Merge with existing translations
data['translations'].update(menu_translations)

# Save updated file
with open('data/config/languages.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("✅ Menu translations added to languages.json")
EOF

# 2. Update bot.py to use multi-language menu commands
echo "📝 Updating bot.py with multi-language menu commands..."

# Create backup
cp src/bot.py src/bot.py.bak
echo "📋 Created backup: src/bot.py.bak"

# Update the setup_bot_menu method
python3 << 'EOF'
import re

# Read current bot.py
with open('src/bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the setup_bot_menu method
old_method = r'async def setup_bot_menu\(self\):.*?logger\.info\("Bot menu commands set successfully"\)'
new_method = '''async def setup_bot_menu(self):
        """Set up the bot menu commands with multi-language support"""
        from telegram import BotCommand
        from utils.translations import get_text
        
        # Get language statistics to determine primary language
        try:
            lang_stats = await self.data_manager.get_language_statistics()
            # Use most common language or default to English
            primary_lang = max(lang_stats.items(), key=lambda x: x[1])[0] if lang_stats else 'en'
        except Exception:
            primary_lang = 'en'
        
        # PUBLIC commands only - auth commands are hidden
        commands = [
            BotCommand("start", get_text("menu_command_start", primary_lang)),
            BotCommand("keywords", get_text("menu_command_keywords", primary_lang)),
            BotCommand("ignore_keywords", get_text("menu_command_ignore", primary_lang)),
            BotCommand("my_settings", get_text("menu_command_settings", primary_lang)),
            BotCommand("purge_ignore", get_text("menu_command_purge", primary_lang)),
            BotCommand("help", get_text("menu_command_help", primary_lang)),
        ]
        
        try:
            await self.app.bot.set_my_commands(commands)
            logger.info(f"Bot menu commands set in {primary_lang}")
        except Exception as e:
            logger.warning(f"Could not set bot menu commands: {e}")'''

# Replace the method
content = re.sub(old_method, new_method, content, flags=re.DOTALL)

# Write updated content
with open('src/bot.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Bot menu method updated")
EOF

echo ""
echo "🎉 Bot menu commands fixed!"
echo ""
echo "📋 Changes made:"
echo "  ✅ Added menu command translations to languages.json"
echo "  ✅ Updated setup_bot_menu() method in bot.py"
echo "  ✅ Menu commands now use most common user language"
echo ""
echo "🔄 Next steps:"
echo "1. Rebuild and restart your bot:"
echo "   docker-compose build --no-cache"
echo "   docker-compose up -d"
echo ""
echo "2. Bot menu will show commands in the most popular language among your users"
echo "3. If most users use Russian, menu will be in Russian"
echo "4. If most users use English, menu will be in English"
echo ""
echo "💡 The menu adapts to your user base automatically!"
echo ""
echo "💾 Backups created:"
echo "  - data/config/languages.json.bak"
echo "  - src/bot.py.bak"
