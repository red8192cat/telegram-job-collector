"""
Data Manager - Handles all file I/O and data persistence
"""

import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

class DataManager:
    def __init__(self):
        self.user_keywords = {}
        self.user_ignore_keywords = {}
        self.load_user_data()
    
    def load_user_data(self):
        """Load all user data from files"""
        try:
            with open('data/user_keywords.json', 'r') as f:
                self.user_keywords = json.load(f)
                self.user_keywords = {int(k): v for k, v in self.user_keywords.items()}
        except FileNotFoundError:
            logger.info("user_keywords.json not found, starting with empty user list")
            self.user_keywords = {}
        
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
            
            with open('data/user_keywords.json', 'w') as f:
                json.dump(self.user_keywords, f, indent=2)
            
            with open('data/user_ignore_keywords.json', 'w') as f:
                json.dump(self.user_ignore_keywords, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save user data: {e}")
    
    def get_user_keywords(self, chat_id: int) -> List[str]:
        """Get keywords for a specific user"""
        return self.user_keywords.get(chat_id, [])
    
    def set_user_keywords(self, chat_id: int, keywords: List[str]):
        """Set keywords for a specific user"""
        self.user_keywords[chat_id] = keywords
        self.save_user_data()
    
    def add_user_keyword(self, chat_id: int, keyword: str) -> bool:
        """Add a keyword for a user. Returns True if added, False if already exists"""
        if chat_id not in self.user_keywords:
            self.user_keywords[chat_id] = []
        
        if keyword not in self.user_keywords[chat_id]:
            self.user_keywords[chat_id].append(keyword)
            self.save_user_data()
            return True
        return False
    
    def remove_user_keyword(self, chat_id: int, keyword: str) -> bool:
        """Remove a keyword for a user. Returns True if removed, False if not found"""
        if chat_id not in self.user_keywords:
            return False
        
        if keyword in self.user_keywords[chat_id]:
            self.user_keywords[chat_id].remove(keyword)
            self.save_user_data()
            return True
        return False
    
    def get_user_ignore_keywords(self, chat_id: int) -> List[str]:
        """Get ignore keywords for a specific user"""
        return self.user_ignore_keywords.get(chat_id, [])
    
    def set_user_ignore_keywords(self, chat_id: int, keywords: List[str]):
        """Set ignore keywords for a specific user"""
        self.user_ignore_keywords[chat_id] = keywords
        self.save_user_data()
    
    def add_user_ignore_keyword(self, chat_id: int, keyword: str) -> bool:
        """Add an ignore keyword for a user"""
        if chat_id not in self.user_ignore_keywords:
            self.user_ignore_keywords[chat_id] = []
        
        if keyword not in self.user_ignore_keywords[chat_id]:
            self.user_ignore_keywords[chat_id].append(keyword)
            self.save_user_data()
            return True
        return False
    
    def remove_user_ignore_keyword(self, chat_id: int, keyword: str) -> bool:
        """Remove an ignore keyword for a user"""
        if chat_id not in self.user_ignore_keywords:
            return False
        
        if keyword in self.user_ignore_keywords[chat_id]:
            self.user_ignore_keywords[chat_id].remove(keyword)
            self.save_user_data()
            return True
        return False
    
    def purge_user_ignore_keywords(self, chat_id: int) -> bool:
        """Remove all ignore keywords for a user"""
        if chat_id in self.user_ignore_keywords:
            del self.user_ignore_keywords[chat_id]
            self.save_user_data()
            return True
        return False
    
    def get_all_users_with_keywords(self) -> Dict[int, List[str]]:
        """Get all users who have keywords set"""
        return self.user_keywords.copy()
    
    def check_user_limit(self, chat_id: int) -> bool:
        """Check if user has reached daily limit"""
        return True
    
    def increment_user_usage(self, chat_id: int):
        """Increment user's daily usage count"""
        pass
