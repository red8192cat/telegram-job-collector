"""
Translation Manager - Multi-language support system
Handles loading and retrieving translations from languages.json
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class TranslationManager:
    def __init__(self, languages_file: str = "data/config/languages.json"):
        self.languages_file = Path(languages_file)
        self.translations = {}
        self.supported_languages = {}
        self.default_language = "en"
        self._load_translations()
    
    def _load_translations(self):
        """Load translations from JSON file"""
        try:
            if not self.languages_file.exists():
                logger.warning(f"Languages file not found: {self.languages_file}")
                self._create_default_file()
                return
            
            with open(self.languages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.default_language = data.get("default_language", "en")
            self.supported_languages = data.get("supported_languages", {})
            self.translations = data.get("translations", {})
            
            logger.info(f"Loaded translations for {len(self.supported_languages)} languages")
            
        except Exception as e:
            logger.error(f"Failed to load translations: {e}")
            self._create_default_file()
    
    def _create_default_file(self):
        """Create default languages.json file"""
        default_data = {
            "default_language": "en",
            "supported_languages": {
                "en": {"name": "English", "flag": "🇺🇸"},
                "ru": {"name": "Русский", "flag": "🇷🇺"}
            },
            "translations": {
                "welcome_message": {
                    "en": "🤖 Welcome to JobFinderBot!",
                    "ru": "🤖 Добро пожаловать в JobFinderBot!"
                }
            }
        }
        
        try:
            self.languages_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.languages_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)
            
            self.default_language = default_data["default_language"]
            self.supported_languages = default_data["supported_languages"]
            self.translations = default_data["translations"]
            
            logger.info("Created default languages.json file")
            
        except Exception as e:
            logger.error(f"Failed to create default languages file: {e}")
    
    def get_text(self, key: str, language: str = None, **kwargs) -> str:
        """
        Get translated text for a key in specified language
        
        Args:
            key: Translation key
            language: Language code (defaults to default_language)
            **kwargs: Format arguments for string formatting
            
        Returns:
            Translated and formatted text
        """
        if language is None:
            language = self.default_language
        
        # Get translation or fallback
        text = self._get_translation(key, language)
        
        # Format with provided arguments
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError) as e:
                logger.warning(f"Translation formatting error for key '{key}': {e}")
                # Return unformatted text if formatting fails
        
        return text
    
    def _get_translation(self, key: str, language: str) -> str:
        """Get translation with fallback logic"""
        # Check if key exists
        if key not in self.translations:
            logger.warning(f"Translation key not found: '{key}'")
            return f"[{key}]"  # Return key as fallback
        
        translation_set = self.translations[key]
        
        # Try requested language
        if language in translation_set:
            return translation_set[language]
        
        # Fallback to default language
        if self.default_language in translation_set:
            logger.debug(f"Using default language for key '{key}' (requested: {language})")
            return translation_set[self.default_language]
        
        # Fallback to any available language
        if translation_set:
            fallback_lang = next(iter(translation_set.keys()))
            logger.warning(f"Using fallback language '{fallback_lang}' for key '{key}'")
            return translation_set[fallback_lang]
        
        # Final fallback
        logger.error(f"No translation found for key '{key}'")
        return f"[{key}]"
    
    def get_supported_languages(self) -> Dict[str, Dict[str, str]]:
        """Get list of supported languages with their metadata"""
        return self.supported_languages.copy()
    
    def is_supported_language(self, language: str) -> bool:
        """Check if language is supported"""
        return language in self.supported_languages
    
    def get_default_language(self) -> str:
        """Get default language code"""
        return self.default_language
    
    def get_language_name(self, language: str) -> str:
        """Get human-readable language name"""
        if language in self.supported_languages:
            return self.supported_languages[language].get("name", language)
        return language
    
    def get_language_flag(self, language: str) -> str:
        """Get language flag emoji"""
        if language in self.supported_languages:
            return self.supported_languages[language].get("flag", "🌐")
        return "🌐"
    
    def reload_translations(self):
        """Reload translations from file"""
        logger.info("Reloading translations...")
        self._load_translations()
    
    def get_missing_translations(self) -> Dict[str, List[str]]:
        """Get list of missing translations for debugging"""
        missing = {}
        
        for key, translations in self.translations.items():
            missing_langs = []
            for lang_code in self.supported_languages.keys():
                if lang_code not in translations:
                    missing_langs.append(lang_code)
            
            if missing_langs:
                missing[key] = missing_langs
        
        return missing
    
    def validate_translations(self) -> bool:
        """Validate that all translations are present"""
        missing = self.get_missing_translations()
        
        if missing:
            logger.warning(f"Missing translations found: {len(missing)} keys")
            for key, langs in missing.items():
                logger.warning(f"Key '{key}' missing in languages: {langs}")
            return False
        
        logger.info("All translations are complete")
        return True


# Global translation manager instance
_translation_manager = None

def get_translation_manager() -> TranslationManager:
    """Get global translation manager instance"""
    global _translation_manager
    if _translation_manager is None:
        _translation_manager = TranslationManager()
    return _translation_manager

def get_text(key: str, language: str = None, **kwargs) -> str:
    """Convenience function to get translated text"""
    return get_translation_manager().get_text(key, language, **kwargs)

def get_supported_languages() -> Dict[str, Dict[str, str]]:
    """Convenience function to get supported languages"""
    return get_translation_manager().get_supported_languages()

def is_supported_language(language: str) -> bool:
    """Convenience function to check if language is supported"""
    return get_translation_manager().is_supported_language(language)
