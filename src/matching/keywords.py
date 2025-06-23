"""
Keyword Matching Engine - Updated with simplified wildcard logic
No quotes, natural comma separation, automatic wildcards
"""

import logging
import re
from typing import List

logger = logging.getLogger(__name__)

class KeywordMatcher:
    
    def matches_with_wildcard(self, text: str, pattern: str) -> bool:
        """Check if text matches pattern with wildcard support"""
        if '*' not in pattern:
            # Exact matching - look for whole word
            text_lower = text.lower()
            pattern_lower = pattern.lower()
            # Use word boundary matching for exact terms
            word_pattern = r'\b' + re.escape(pattern_lower) + r'\b'
            return bool(re.search(word_pattern, text_lower))
        
        text_lower = text.lower()
        pattern_lower = pattern.lower()
        
        # Handle space-separated words with wildcards (adjacent matching)
        if ' ' in pattern_lower:
            return self._match_adjacent_wildcard_phrase(text_lower, pattern_lower)
        
        # Single word with wildcard
        if pattern_lower.endswith('*'):
            prefix = pattern_lower[:-1]
            if not prefix:
                return False
            # Match word that starts with prefix
            word_pattern = r'\b' + re.escape(prefix) + r'\w*'
            return bool(re.search(word_pattern, text_lower))
        
        return False
    
    def _match_adjacent_wildcard_phrase(self, text: str, pattern: str) -> bool:
        """Match adjacent words with wildcards (e.g., 'support* engineer*')"""
        pattern_words = pattern.split()
        text_words = re.findall(r'\b\w+', text)
        
        # Look for adjacent sequence matching the pattern
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
                    # Exact word match
                    if pattern_word != text_word:
                        match_found = False
                        break
            
            if match_found:
                return True
        
        return False
    
    def parse_keywords(self, keywords_text: str) -> List[str]:
        """Parse comma-separated keywords, removing quotes entirely"""
        # Split by comma and clean up
        keywords = []
        for keyword in keywords_text.split(','):
            keyword = keyword.strip()
            if keyword:
                # Remove any quotes that users might still try to use
                keyword = keyword.strip('"\'')
                keywords.append(keyword)
        return keywords
    
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
        """Helper method to match a single keyword pattern - UPDATED LOGIC"""
        
        # Handle AND logic with + (keep this for power users)
        if '+' in keyword_pattern:
            required_parts = [part.strip() for part in keyword_pattern.split('+') if part.strip()]
            
            for part in required_parts:
                if not self.matches_with_wildcard(text_lower, part):
                    return False
            
            return True
        else:
            # Simple wildcard or exact matching
            return self.matches_with_wildcard(text_lower, keyword_pattern)
    
    def matches_ignore_keywords(self, message_text: str, ignore_keywords: List[str]) -> bool:
        """Check if message matches ignore keywords - same logic as regular keywords"""
        if not ignore_keywords:
            return False
        
        text_lower = message_text.lower()
        
        for keyword_pattern in ignore_keywords:
            if self._matches_single_pattern(text_lower, keyword_pattern):
                return True
        
        return False