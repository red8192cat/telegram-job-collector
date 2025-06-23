"""
Keyword Matching Engine - Handles all keyword matching logic
"""

import logging
import re
from typing import List

logger = logging.getLogger(__name__)

class KeywordMatcher:
    
    def matches_with_wildcard(self, text: str, pattern: str) -> bool:
        """Check if text matches pattern with wildcard support (* at word endings only)"""
        if '*' not in pattern:
            return pattern in text
        
        text_lower = text.lower()
        pattern_lower = pattern.lower()
        
        if pattern_lower.endswith('*') and ' ' not in pattern_lower:
            prefix = pattern_lower[:-1]
            if not prefix:
                return False
            words = re.findall(r'\b\w+', text_lower)
            return any(word.startswith(prefix) for word in words)
        
        elif ' ' in pattern_lower and '*' in pattern_lower:
            pattern_words = pattern_lower.split()
            text_words = re.findall(r'\b\w+', text_lower)
            
            for i in range(len(text_words) - len(pattern_words) + 1):
                match_found = True
                
                for j, pattern_word in enumerate(pattern_words):
                    if i + j >= len(text_words):
                        match_found = False
                        break
                        
                    text_word = text_words[i + j]
                    
                    if pattern_word.endswith('*'):
                        prefix = pattern_word[:-1]
                        if prefix and not text_word.startswith(prefix):
                            match_found = False
                            break
                        elif not prefix:
                            match_found = False
                            break
                    else:
                        if pattern_word != text_word:
                            match_found = False
                            break
                
                if match_found:
                    return True
            
            return False
        
        else:
            if '*' in pattern_lower:
                parts = pattern_lower.split('*')
                if len(parts) == 2:
                    before, after = parts
                    if before and after:
                        words = re.findall(r'\b\w+', text_lower)
                        return any(word.startswith(before) and word.endswith(after) for word in words)
                    elif before and not after:
                        words = re.findall(r'\b\w+', text_lower)
                        return any(word.startswith(before) for word in words)
                
                return pattern_lower.replace('*', '') in text_lower
            
            return pattern_lower in text_lower
    
    def matches_user_keywords(self, message_text: str, user_keywords: List[str]) -> bool:
        """Check if message matches user's keywords with required and optional logic"""
        text_lower = message_text.lower()
        
        required_keywords = []
        optional_keywords = []
        
        for keyword_pattern in user_keywords:
            if keyword_pattern.startswith('[') and keyword_pattern.endswith(']'):
                required_keyword = keyword_pattern[1:-1].strip()
                if required_keyword:
                    required_keywords.append(required_keyword)
            else:
                optional_keywords.append(keyword_pattern)
        
        # Check ALL required keywords must be present
        for required_pattern in required_keywords:
            if not self._matches_required_pattern(text_lower, required_pattern):
                return False
        
        # If no optional keywords, just check required keywords
        if not optional_keywords:
            return len(required_keywords) > 0
        
        # Check if at least one optional keyword matches
        for keyword_pattern in optional_keywords:
            if self._matches_single_pattern(text_lower, keyword_pattern):
                return True
        
        return False
    
    def _matches_required_pattern(self, text_lower: str, required_pattern: str) -> bool:
        """Helper method to match a required keyword pattern (supports OR logic with |)"""
        if '|' in required_pattern:
            or_parts = [part.strip() for part in required_pattern.split('|') if part.strip()]
            
            for part in or_parts:
                if self._matches_single_pattern(text_lower, part):
                    return True
            
            return False
        else:
            return self._matches_single_pattern(text_lower, required_pattern)
    
    def _matches_single_pattern(self, text_lower: str, keyword_pattern: str) -> bool:
        """Helper method to match a single keyword pattern"""
        if keyword_pattern.startswith('"') and keyword_pattern.endswith('"'):
            exact_phrase = keyword_pattern[1:-1].strip()
            return self.matches_with_wildcard(text_lower, exact_phrase)
        
        elif '+' in keyword_pattern:
            required_parts = [part.strip() for part in keyword_pattern.split('+') if part.strip()]
            
            for part in required_parts:
                if part.startswith('"') and part.endswith('"'):
                    exact_phrase = part[1:-1].strip()
                    if not self.matches_with_wildcard(text_lower, exact_phrase):
                        return False
                else:
                    if not self.matches_with_wildcard(text_lower, part):
                        return False
            
            return True
        else:
            return self.matches_with_wildcard(text_lower, keyword_pattern)
    
    def matches_ignore_keywords(self, message_text: str, ignore_keywords: List[str]) -> bool:
        """Check if message matches ignore keywords"""
        if not ignore_keywords:
            return False
        
        text_lower = message_text.lower()
        
        for keyword_pattern in ignore_keywords:
            if self._matches_single_pattern(text_lower, keyword_pattern):
                return True
        
        return False
