#!/usr/bin/env python3
"""
Enhanced Telegram Job Collector Bot
Collects job postings from configured channels and reposts to user groups
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Set

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class JobCollectorBot:
    def __init__(self, token: str):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.user_keywords = {}  # {chat_id: [keywords]}
        self.user_ignore_keywords = {}  # {chat_id: [ignore_keywords]}
        self.channels_to_monitor = []
        
        # Load configuration
        self.load_config()
        self.load_user_data()
        
        # Register handlers
        self.register_handlers()
    
    def load_config(self):
        """Load channels to monitor from config file"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                old_channels = self.channels_to_monitor.copy()
                self.channels_to_monitor = config.get('channels', [])
                
                if old_channels != self.channels_to_monitor:
                    logger.info(f"Updated channels: {len(self.channels_to_monitor)} channels to monitor")
                    
        except FileNotFoundError:
            logger.warning("config.json not found, using empty channel list")
            self.channels_to_monitor = []
    
    def load_user_data(self):
        """Load all user data from files"""
        # Load keywords
        try:
            with open('data/user_keywords.json', 'r') as f:
                self.user_keywords = json.load(f)
                self.user_keywords = {int(k): v for k, v in self.user_keywords.items()}
        except FileNotFoundError:
            logger.info("user_keywords.json not found, starting with empty user list")
            self.user_keywords = {}
        
        # Load ignore keywords
        try:
            with open('data/user_ignore_keywords.json', 'r') as f:
                self.user_ignore_keywords = json.load(f)
                self.user_ignore_keywords = {int(k): v for k, v in self.user_ignore_keywords.items()}
        except FileNotFoundError:
            logger.info("user_ignore_keywords.json not found, starting with empty ignore list")
            self.user_ignore_keywords = {}
    
    def save_user_data(self):
        """Save all user data to files"""
        try:
            os.makedirs('data', exist_ok=True)
            
            # Save keywords
            with open('data/user_keywords.json', 'w') as f:
                json.dump(self.user_keywords, f, indent=2)
            
            # Save ignore keywords
            with open('data/user_ignore_keywords.json', 'w') as f:
                json.dump(self.user_ignore_keywords, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save user data: {e}")
    
    async def start_config_reload_task(self):
        """Start the config reload background task"""
        async def reload_task():
            while True:
                await asyncio.sleep(3600)  # 1 hour
                logger.info("Reloading configuration...")
                self.load_config()
        
        # Start the task
        asyncio.create_task(reload_task())
        logger.info("Config reload task started")
        
        # Clear any old bot menu commands and set up new ones
        await self.setup_bot_menu()
    
    async def setup_bot_menu(self):
        """Set up the bot menu commands (without purge_list)"""
        from telegram import BotCommand
        
        commands = [
            BotCommand("start", "🚀 Start the bot and see welcome message"),
            BotCommand("menu", "📋 Show interactive menu"),
            BotCommand("keywords", "🎯 Set your search keywords"),
            BotCommand("ignore_keywords", "🚫 Set ignore keywords"),
            BotCommand("my_keywords", "📝 Show your current keywords"),
            BotCommand("my_ignore", "📋 Show your ignore keywords"),
            BotCommand("add_keyword_to_list", "➕ Add a keyword"),
            BotCommand("add_ignore_keyword", "➕ Add ignore keyword"),
            BotCommand("delete_keyword_from_list", "➖ Remove a keyword"),
            BotCommand("delete_ignore_keyword", "➖ Remove ignore keyword"),
            BotCommand("purge_ignore", "🗑️ Clear all ignore keywords"),
            BotCommand("help", "❓ Show help and examples")
        ]
        
        try:
            await self.app.bot.set_my_commands(commands)
            logger.info("Bot menu commands set successfully (without purge_list)")
        except Exception as e:
            logger.warning(f"Could not set bot menu commands: {e}")
    
    async def clear_bot_menu(self):
        """Clear the bot menu commands"""
        try:
            # Set empty commands list to clear the menu
            await self.app.bot.set_my_commands([])
            logger.info("Bot menu commands cleared successfully")
        except Exception as e:
            logger.warning(f"Could not clear bot menu commands: {e}")
        
        # Clear any old bot menu commands
        await self.clear_bot_menu()
    
    def is_private_chat(self, update: Update) -> bool:
        """Check if message is from private chat"""
        return update.effective_chat.type == 'private'
    
    def check_user_limit(self, chat_id: int) -> bool:
        """Check if user has reached daily limit"""
        # All users are premium now
        return True
    
    def increment_user_usage(self, chat_id: int):
        """Increment user's daily usage count"""
        # No usage tracking needed since all users are premium
        pass
    
    def create_main_menu(self):
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
    
    def register_handlers(self):
        """Register command handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("menu", self.menu_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("keywords", self.set_keywords_command))
        self.app.add_handler(CommandHandler("ignore_keywords", self.set_ignore_keywords_command))
        self.app.add_handler(CommandHandler("add_keyword_to_list", self.add_keyword_command))
        self.app.add_handler(CommandHandler("delete_keyword_from_list", self.delete_keyword_command))
        self.app.add_handler(CommandHandler("add_ignore_keyword", self.add_ignore_keyword_command))
        self.app.add_handler(CommandHandler("delete_ignore_keyword", self.delete_ignore_keyword_command))
        self.app.add_handler(CommandHandler("purge_ignore", self.purge_ignore_keywords_command))
        self.app.add_handler(CommandHandler("my_keywords", self.show_keywords_command))
        self.app.add_handler(CommandHandler("my_ignore", self.show_ignore_keywords_command))
        
        # Callback query handler for menu buttons
        self.app.add_handler(CallbackQueryHandler(self.handle_callback_query))
        logger.info("Callback query handler registered")
        
        # Add message handler to process channel messages in real-time
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_channel_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self.is_private_chat(update):
            logger.info("Start command ignored - not a private chat")
            return
        
        logger.info(f"Start command from user {update.effective_user.id}")
        
        welcome_msg = (
            "🤖 Welcome to Job Collector Bot!\n\n"
            "I help you collect job postings from configured channels based on your keywords.\n\n"
            "✅ All users get unlimited job forwards\n"
            "✅ Advanced keyword filtering with ignore list\n\n"
            "Use the menu below to get started:"
        )
        
        menu_markup = self.create_main_menu()
        logger.info(f"Sending welcome with menu to user {update.effective_user.id}")
        
        await update.message.reply_text(welcome_msg, reply_markup=menu_markup)
        logger.info("Welcome message sent successfully")
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command"""
        if not self.is_private_chat(update):
            logger.info("Menu command ignored - not a private chat")
            return
        
        logger.info(f"Sending menu to user {update.effective_user.id}")
        menu_markup = self.create_main_menu()
        logger.info(f"Created menu with {len(menu_markup.inline_keyboard)} rows of buttons")
        
        await update.message.reply_text("📋 Main Menu:", reply_markup=menu_markup)
        logger.info("Menu sent successfully")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self.is_private_chat(update):
            return
        
        help_msg = (
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
            "• Single: python, javascript, remote\n"
            "• AND: python+junior+remote (all 3 must be present)\n"
            "• Exact: \"project manager\" (exact order)\n"
            "• Wildcard: manag* (matches manager, managing, management)\n"
            "• Mixed: python+\"project manag*\"+remote\n"
            "• Ignore keywords help filter out unwanted messages\n\n"
            "🎯 The bot forwards ALL messages that match your keywords!"
        )
        await update.message.reply_text(help_msg)
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons"""
        logger.info(f"Received callback query: {update.callback_query.data if update.callback_query else 'None'}")
        
        query = update.callback_query
        if not query:
            logger.error("No callback query found in update")
            return
            
        try:
            await query.answer()
            logger.info(f"Processing callback: {query.data}")
            
            if query.data == "menu_keywords":
                msg = "🎯 To set keywords, use:\n/keywords python, \"project manag*\", python+\"data scientist\"\n\nTypes:\n• Single: python\n• AND: python+junior\n• Exact: \"project manager\"\n• Wildcard: manag*\n• Mixed: python+\"data manag*\"\n\n💡 /keywords overwrites your current list"
                await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
                logger.info("Sent keywords help")
            
            elif query.data == "menu_ignore":
                msg = "🚫 To set ignore keywords, use:\n/ignore_keywords java, php, senior\n\n💡 /ignore_keywords overwrites your current list\n🗑️ Use /purge_ignore to clear all ignore keywords"
                await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
                logger.info("Sent ignore keywords help")
            
            elif query.data == "menu_show_keywords":
                chat_id = query.from_user.id
                if chat_id in self.user_keywords and self.user_keywords[chat_id]:
                    keywords_str = ', '.join(self.user_keywords[chat_id])
                    msg = f"📝 Your keywords: {keywords_str}"
                else:
                    msg = "You haven't set any keywords yet!"
                await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
                logger.info("Sent user keywords")
            
            elif query.data == "menu_show_ignore":
                chat_id = query.from_user.id
                if chat_id in self.user_ignore_keywords and self.user_ignore_keywords[chat_id]:
                    ignore_str = ', '.join(self.user_ignore_keywords[chat_id])
                    msg = f"🚫 Your ignore keywords: {ignore_str}"
                else:
                    msg = "You haven't set any ignore keywords yet!"
                await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
                logger.info("Sent user ignore keywords")
            
            elif query.data == "menu_contact":
                await self.show_contact_info(query)
                logger.info("Sent contact info")
            
            elif query.data == "menu_help":
                help_msg = (
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
                    "💡 Keyword Types:\n"
                    "• Single: python, javascript, remote\n"
                    "• AND: python+junior+remote (all 3 must be present)\n"
                    "• Exact: \"project manager\" (exact order)\n"
                    "• Wildcard: manag* (matches manager, managing, management)\n"
                    "• Multi-wildcard: \"support* engineer*\" (support + engineering)\n"
                    "• Mixed: python+\"project manag*\"+remote"
                )
                await query.edit_message_text(help_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
                logger.info("Sent help content")
            
            elif query.data == "menu_back":
                await query.edit_message_text("📋 Main Menu:", reply_markup=self.create_main_menu())
                logger.info("Sent main menu")
            
            else:
                logger.warning(f"Unknown callback data: {query.data}")
                await query.edit_message_text(f"❌ Unknown action: {query.data}\n\nUse /menu to start over.")
                
        except Exception as e:
            logger.error(f"Error handling callback query {query.data}: {e}")
            try:
                await query.edit_message_text("❌ Something went wrong. Please try /menu again.")
            except:
                logger.error("Failed to send error message")
    
    async def show_contact_info(self, query):
        """Show contact information"""
        msg = (
            "💬 Need Help?\n\n"
            "For support, questions, or feedback:\n\n"
            "👤 Contact the admin mentioned in the bot description\n\n"
            "We're here to help! 😊"
        )
        
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu_back")]]))
    
    async def set_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /keywords command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text(
                "Please provide keywords:\n"
                "/keywords python, \"project manag*\", remote\n"
                "/keywords python+\"data scientist\", react+senior\n\n"
                "• Use + for AND logic (all parts must be present)\n"
                "• Use \"quotes\" for exact phrases in order\n"
                "• Use * for wildcards at word endings\n"
                "• Mix them: python+\"machine learn*\"+remote"
            )
            return
        
        keywords_text = ' '.join(context.args)
        keywords = [k.strip().lower() for k in keywords_text.split(',') if k.strip()]
        
        if not keywords:
            await update.message.reply_text("No valid keywords provided!")
            return
        
        self.user_keywords[chat_id] = keywords
        self.save_user_data()
        
        keywords_str = ', '.join(keywords)
        await update.message.reply_text(f"✅ Keywords set: {keywords_str}")
    
    async def set_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ignore_keywords command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide ignore keywords: /ignore_keywords java, senior, manager")
            return
        
        keywords_text = ' '.join(context.args)
        keywords = [k.strip().lower() for k in keywords_text.split(',') if k.strip()]
        
        if not keywords:
            await update.message.reply_text("No valid ignore keywords provided!")
            return
        
        self.user_ignore_keywords[chat_id] = keywords
        self.save_user_data()
        
        keywords_str = ', '.join(keywords)
        await update.message.reply_text(f"✅ Ignore keywords set: {keywords_str}")
    
    async def add_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_keyword_to_list command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text(
                "Please provide a keyword:\n"
                "/add_keyword_to_list python\n"
                "/add_keyword_to_list python+junior+remote\n"
                "/add_keyword_to_list \"project manag*\"\n"
                "/add_keyword_to_list develop*"
            )
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if chat_id not in self.user_keywords:
            self.user_keywords[chat_id] = []
        
        if keyword not in self.user_keywords[chat_id]:
            self.user_keywords[chat_id].append(keyword)
            self.save_user_data()
            await update.message.reply_text(f"✅ Added keyword: {keyword}")
        else:
            await update.message.reply_text(f"Keyword '{keyword}' already in your list!")
    
    async def add_ignore_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_ignore_keyword command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide an ignore keyword: /add_ignore_keyword java")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if chat_id not in self.user_ignore_keywords:
            self.user_ignore_keywords[chat_id] = []
        
        if keyword not in self.user_ignore_keywords[chat_id]:
            self.user_ignore_keywords[chat_id].append(keyword)
            self.save_user_data()
            await update.message.reply_text(f"✅ Added ignore keyword: {keyword}")
        else:
            await update.message.reply_text(f"Ignore keyword '{keyword}' already in your list!")
    
    async def delete_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_keyword_from_list command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide a keyword: /delete_keyword_from_list python")
            return
        
        keyword_to_delete = ' '.join(context.args).strip().lower()
        
        if chat_id not in self.user_keywords:
            await update.message.reply_text("You don't have any keywords set!")
            return
        
        # First try exact match
        if keyword_to_delete in self.user_keywords[chat_id]:
            self.user_keywords[chat_id].remove(keyword_to_delete)
            self.save_user_data()
            await update.message.reply_text(f"✅ Removed keyword: {keyword_to_delete}")
            return
        
        # If no exact match, look for patterns containing this keyword
        matching_patterns = []
        for pattern in self.user_keywords[chat_id]:
            # Check if the keyword appears in a complex pattern
            if '+' in pattern and keyword_to_delete in pattern:
                matching_patterns.append(pattern)
            elif pattern.startswith('"') and pattern.endswith('"'):
                # Check if it matches a quoted phrase
                phrase = pattern[1:-1].strip()
                if phrase == keyword_to_delete.strip('"'):
                    matching_patterns.append(pattern)
        
        if matching_patterns:
            # Remove all matching patterns
            for pattern in matching_patterns:
                self.user_keywords[chat_id].remove(pattern)
            
            self.save_user_data()
            
            if len(matching_patterns) == 1:
                await update.message.reply_text(f"✅ Removed pattern: {matching_patterns[0]}")
            else:
                patterns_str = ', '.join(matching_patterns)
                await update.message.reply_text(f"✅ Removed {len(matching_patterns)} patterns: {patterns_str}")
        else:
            # Show current keywords to help user
            current = ', '.join(self.user_keywords[chat_id])
            await update.message.reply_text(
                f"❌ Keyword '{keyword_to_delete}' not found!\n\n"
                f"Your current keywords: {current}\n\n"
                f"💡 Use the exact pattern to delete, e.g.:\n"
                f"/delete_keyword_from_list python+\"project manager\""
            )
    
    async def delete_ignore_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delete_ignore_keyword command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if not context.args:
            await update.message.reply_text("Please provide an ignore keyword: /delete_ignore_keyword java")
            return
        
        keyword = ' '.join(context.args).strip().lower()
        
        if chat_id in self.user_ignore_keywords and keyword in self.user_ignore_keywords[chat_id]:
            self.user_ignore_keywords[chat_id].remove(keyword)
            self.save_user_data()
            await update.message.reply_text(f"✅ Removed ignore keyword: {keyword}")
        else:
            await update.message.reply_text(f"Ignore keyword '{keyword}' not found in your list!")
    
    async def purge_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /purge_ignore command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if chat_id in self.user_ignore_keywords:
            del self.user_ignore_keywords[chat_id]
            self.save_user_data()
            await update.message.reply_text("✅ All ignore keywords cleared!")
        else:
            await update.message.reply_text("You don't have any ignore keywords set!")
    
    async def show_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_keywords command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if chat_id in self.user_keywords and self.user_keywords[chat_id]:
            keywords_str = ', '.join(self.user_keywords[chat_id])
            await update.message.reply_text(f"📝 Your keywords: {keywords_str}")
        else:
            await update.message.reply_text("You haven't set any keywords yet!")
    
    async def show_ignore_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /my_ignore command"""
        if not self.is_private_chat(update):
            return
        
        chat_id = update.effective_chat.id
        
        if chat_id in self.user_ignore_keywords and self.user_ignore_keywords[chat_id]:
            ignore_str = ', '.join(self.user_ignore_keywords[chat_id])
            await update.message.reply_text(f"🚫 Your ignore keywords: {ignore_str}")
        else:
            await update.message.reply_text("You haven't set any ignore keywords yet!")
    
    def matches_with_wildcard(self, text: str, pattern: str) -> bool:
        """Check if text matches pattern with wildcard support (* at word endings only)"""
        if '*' not in pattern:
            # No wildcard, simple substring match
            return pattern in text
        
        # Handle patterns with wildcards
        if pattern.endswith('*'):
            # Single wildcard at the end
            prefix = pattern[:-1]
            if not prefix:  # Just "*" is not valid
                return False
            
            # Split text into words and check if any word starts with the prefix
            words = re.findall(r'\b\w+', text)
            return any(word.startswith(prefix) for word in words)
        
        elif ' ' in pattern and '*' in pattern:
            # Multiple words with wildcards (e.g., "support* engineer*")
            pattern_words = pattern.split()
            text_words = re.findall(r'\b\w+', text.lower())
            
            # Try to find the pattern sequence in text
            for i in range(len(text_words) - len(pattern_words) + 1):
                match_found = True
                for j, pattern_word in enumerate(pattern_words):
                    text_word = text_words[i + j]
                    
                    if pattern_word.endswith('*'):
                        # Wildcard match
                        prefix = pattern_word[:-1]
                        if prefix and not text_word.startswith(prefix):
                            match_found = False
                            break
                    else:
                        # Exact word match
                        if pattern_word != text_word:
                            match_found = False
                            break
                
                if match_found:
                    return True
            
            return False
        
        else:
            # Wildcard in middle of single word or other cases
            if '*' in pattern:
                # For now, treat as literal (could be enhanced later)
                return pattern.replace('*', '') in text
            return pattern in text
    
    def matches_user_keywords(self, message_text: str, user_keywords: List[str]) -> bool:
        """Check if message matches user's keywords with AND logic, exact phrase support, and wildcards"""
        text_lower = message_text.lower()
        
        for keyword_pattern in user_keywords:
            # Check if this is an exact phrase (wrapped in quotes)
            if keyword_pattern.startswith('"') and keyword_pattern.endswith('"'):
                # Extract the phrase without quotes
                exact_phrase = keyword_pattern[1:-1].strip()
                if self.matches_with_wildcard(text_lower, exact_phrase):
                    return True
            
            # Check if this is an AND pattern (contains +)
            elif '+' in keyword_pattern:
                # Split by + and process each part
                required_parts = [part.strip() for part in keyword_pattern.split('+') if part.strip()]
                all_parts_match = True
                
                for part in required_parts:
                    # Check if this part is an exact phrase
                    if part.startswith('"') and part.endswith('"'):
                        exact_phrase = part[1:-1].strip()
                        if not self.matches_with_wildcard(text_lower, exact_phrase):
                            all_parts_match = False
                            break
                    else:
                        # Regular word match with wildcard support
                        if not self.matches_with_wildcard(text_lower, part):
                            all_parts_match = False
                            break
                
                if all_parts_match:
                    return True
            else:
                # Simple single keyword match with wildcard support
                if self.matches_with_wildcard(text_lower, keyword_pattern):
                    return True
        
        return False
    
    def matches_ignore_keywords(self, message_text: str, ignore_keywords: List[str]) -> bool:
        """Check if message matches ignore keywords with AND logic, exact phrase support, and wildcards"""
        if not ignore_keywords:
            return False
        
        text_lower = message_text.lower()
        
        for keyword_pattern in ignore_keywords:
            # Check if this is an exact phrase (wrapped in quotes)
            if keyword_pattern.startswith('"') and keyword_pattern.endswith('"'):
                # Extract the phrase without quotes
                exact_phrase = keyword_pattern[1:-1].strip()
                if self.matches_with_wildcard(text_lower, exact_phrase):
                    return True
            
            # Check if this is an AND pattern (contains +)
            elif '+' in keyword_pattern:
                # Split by + and process each part
                required_parts = [part.strip() for part in keyword_pattern.split('+') if part.strip()]
                all_parts_match = True
                
                for part in required_parts:
                    # Check if this part is an exact phrase
                    if part.startswith('"') and part.endswith('"'):
                        exact_phrase = part[1:-1].strip()
                        if not self.matches_with_wildcard(text_lower, exact_phrase):
                            all_parts_match = False
                            break
                    else:
                        # Regular word match with wildcard support
                        if not self.matches_with_wildcard(text_lower, part):
                            all_parts_match = False
                            break
                
                if all_parts_match:
                    return True
            else:
                # Simple single keyword match with wildcard support
                if self.matches_with_wildcard(text_lower, keyword_pattern):
                    return True
        
        return False
    
    async def handle_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages from monitored channels"""
        message = update.message
        if not message or not message.text:
            return
        
        # Ignore messages from private chats (user commands)
        if message.chat.type == 'private':
            return
        
        # Check if message is from a monitored channel
        chat_id = message.chat.id
        channel_username = f"@{message.chat.username}" if message.chat.username else str(chat_id)
        
        if channel_username not in self.channels_to_monitor and str(chat_id) not in self.channels_to_monitor:
            return
        
        logger.info(f"Processing message from channel: {channel_username}")
        
        # Check against each user's keywords and forward if matches
        for user_chat_id, keywords in self.user_keywords.items():
            # IMPORTANT: Only forward to private chats (positive user IDs)
            # Skip if this is a group/channel ID (negative numbers or same as source)
            if user_chat_id <= 0 or user_chat_id == chat_id:
                logger.info(f"Skipping forward to {user_chat_id} - not a private chat or same as source")
                continue
            
            # Check user's daily limit
            if not self.check_user_limit(user_chat_id):
                logger.info(f"User {user_chat_id} has reached daily limit")
                continue
            
            # Check if message matches user keywords
            if not self.matches_user_keywords(message.text, keywords):
                continue
            
            # Check if message matches ignore keywords
            ignore_keywords = self.user_ignore_keywords.get(user_chat_id, [])
            if self.matches_ignore_keywords(message.text, ignore_keywords):
                logger.info(f"Message filtered out by ignore keywords for user {user_chat_id}")
                continue
            
            try:
                # Forward the message directly to the user's private chat ONLY
                await context.bot.forward_message(
                    chat_id=user_chat_id,
                    from_chat_id=chat_id,
                    message_id=message.message_id
                )
                
                logger.info(f"Forwarded job to private user {user_chat_id}")
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)
                
            except TelegramError as e:
                logger.error(f"Failed to forward to user {user_chat_id}: {e}")
    
    async def collect_and_repost_jobs(self):
        """Manual job collection function for scheduled runs"""
        logger.info("Starting manual job collection...")
        
        if not self.channels_to_monitor:
            logger.warning("No channels configured to monitor")
            return
        
        if not self.user_keywords:
            logger.info("No users have set keywords yet")
            return
        
        # Get messages from the last 12 hours
        since_time = datetime.now() - timedelta(hours=12)
        
        for channel in self.channels_to_monitor:
            try:
                logger.info(f"Checking channel: {channel}")
                
                # Get recent messages from channel using get_chat_history
                try:
                    messages = []
                    async for message in self.app.bot.get_chat_history(
                        chat_id=channel,
                        limit=50
                    ):
                        if message.date > since_time and message.text:
                            messages.append(message)
                    
                    for message in messages:
                        # Check against each user's keywords
                        for user_chat_id, keywords in self.user_keywords.items():
                            # IMPORTANT: Only forward to private chats (positive user IDs)
                            # Skip if this is a group/channel ID (negative numbers or same as source)
                            if user_chat_id <= 0:
                                continue
                            
                            # Check user's daily limit
                            if not self.check_user_limit(user_chat_id):
                                continue
                            
                            # Check if message matches user keywords
                            if not self.matches_user_keywords(message.text, keywords):
                                continue
                            
                            # Check if message matches ignore keywords
                            ignore_keywords = self.user_ignore_keywords.get(user_chat_id, [])
                            if self.matches_ignore_keywords(message.text, ignore_keywords):
                                continue
                            
                            try:
                                # Forward the message directly to the user's private chat ONLY
                                await self.app.bot.forward_message(
                                    chat_id=user_chat_id,
                                    from_chat_id=channel,
                                    message_id=message.message_id
                                )
                                
                                logger.info(f"Forwarded job to private user {user_chat_id}")
                                
                                # Small delay to avoid rate limiting
                                await asyncio.sleep(0.5)
                                
                            except TelegramError as e:
                                logger.error(f"Failed to forward to user {user_chat_id}: {e}")
                
                except Exception as e:
                    logger.error(f"Failed to get messages from {channel}: {e}")
                
            except Exception as e:
                logger.error(f"Error processing channel {channel}: {e}")
        
        logger.info("Manual job collection completed")
    
    async def run_scheduled_job(self):
        """Run the scheduled job collection"""
        try:
            await self.app.initialize()
            await self.collect_and_repost_jobs()
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")
        finally:
            await self.app.shutdown()

def main():
    """Main function"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    bot = JobCollectorBot(token)
    
    # Check if we should run the scheduled job
    run_mode = os.getenv('RUN_MODE', 'webhook')
    
    if run_mode == 'scheduled':
        # Run job collection once and exit
        asyncio.run(bot.run_scheduled_job())
    else:
        # Run as webhook bot
        logger.info("Starting bot in webhook mode...")
        
        # Set up post_init callback to start background tasks
        async def post_init(application):
            await bot.start_config_reload_task()
        
        bot.app.post_init = post_init
        bot.app.run_polling()

if __name__ == '__main__':
    main()