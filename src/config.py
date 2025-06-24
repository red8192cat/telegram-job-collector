"""
Centralized Configuration Management
Production-ready configuration with environment variable support
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class BotConfig:
    """Centralized configuration for the Job Collector Bot"""
    
    # ===== CORE CREDENTIALS =====
    TELEGRAM_BOT_TOKEN: str = ""
    AUTHORIZED_ADMIN_ID: Optional[int] = None
    
    # ===== USER MONITOR CREDENTIALS =====
    API_ID: Optional[str] = None
    API_HASH: Optional[str] = None
    PHONE_NUMBER: Optional[str] = None
    SESSION_NAME: str = "user_monitor"
    
    # ===== DATABASE SETTINGS =====
    DATABASE_PATH: str = "data/bot.db"
    DB_POOL_SIZE: int = 5
    DB_TIMEOUT: int = 30
    DB_BUSY_TIMEOUT: int = 30000  # milliseconds
    
    # ===== TIMEOUT SETTINGS =====
    TELEGRAM_API_TIMEOUT: int = 15
    USER_MONITOR_TIMEOUT: int = 25
    CHANNEL_VALIDATION_TIMEOUT: int = 10
    AUTH_TIMEOUT: int = 60
    WEBHOOK_TIMEOUT: int = 10
    
    # ===== RATE LIMITING =====
    MESSAGE_FORWARD_DELAY: float = 0.5  # Seconds between forwards
    MAX_FORWARDS_PER_MINUTE: int = 100   # Telegram rate limit safety
    RECONNECT_DELAY: int = 30            # User monitor reconnect delay
    BATCH_PROCESSING_SIZE: int = 50      # Messages per batch
    
    # ===== USER LIMITS =====
    MAX_KEYWORDS_PER_USER: int = 50      # Prevent keyword spam
    MAX_IGNORE_KEYWORDS: int = 20        # Reasonable ignore limit
    MAX_KEYWORD_LENGTH: int = 100        # Prevent long keywords
    MAX_DAILY_FORWARDS_PER_USER: int = 500  # Prevent abuse
    
    # ===== RECONNECTION SETTINGS =====
    MAX_RECONNECT_ATTEMPTS: int = 3      # Before giving up
    RECONNECT_BACKOFF_MULTIPLIER: float = 2.0  # Exponential backoff
    MAX_RECONNECT_DELAY: int = 300       # Max 5 minutes between attempts
    KEEP_ALIVE_INTERVAL: int = 600       # 10 minutes
    
    # ===== MONITORING & HEALTH =====
    HEALTH_CHECK_INTERVAL: int = 300     # 5 minutes
    ERROR_NOTIFICATION_COOLDOWN: int = 3600  # 1 hour between error notifications
    BACKUP_RETENTION_DAYS: int = 30      # How long to keep backups
    STATS_UPDATE_INTERVAL: int = 1800    # 30 minutes
    
    # ===== FEATURE FLAGS =====
    ENABLE_USER_MONITOR: bool = True
    ENABLE_ERROR_MONITORING: bool = True
    ENABLE_AUTO_BACKUPS: bool = True
    ENABLE_METRICS_COLLECTION: bool = False
    ENABLE_WEBHOOK_MODE: bool = False    # vs polling mode
    
    # ===== UI SETTINGS =====
    DEFAULT_LANGUAGE: str = "en"
    SHOW_ADVANCED_FEATURES: bool = True
    MENU_TIMEOUT: int = 300              # Seconds before menu expires
    MAX_INLINE_RESULTS: int = 20         # For inline queries
    
    # ===== LOGGING =====
    LOG_LEVEL: str = "INFO"              # DEBUG, INFO, WARNING, ERROR
    LOG_TO_FILE: bool = True
    LOG_FILE_PATH: str = "data/bot.log"
    MAX_LOG_FILE_SIZE: int = 10_000_000  # 10MB
    LOG_ROTATION_COUNT: int = 5          # Keep 5 log files
    
    # ===== BACKUP SETTINGS =====
    BACKUP_DIRECTORY: str = "data/backups"
    AUTO_BACKUP_INTERVAL: int = 86400    # Daily
    MANUAL_BACKUP_RETENTION: int = 0     # Keep forever (0 = no limit)
    AUTO_BACKUP_RETENTION: int = 7       # Keep 7 auto backups
    
    # ===== PERFORMANCE TUNING =====
    CACHE_SIZE: int = 1000               # In-memory cache for frequent queries
    BATCH_INSERT_SIZE: int = 100         # Database batch operations
    CONNECTION_POOL_TIMEOUT: int = 30    # Seconds to wait for DB connection
    
    @classmethod
    def from_env_file(cls, env_file: str = "data/config/bot-secrets.env") -> 'BotConfig':
        """Load configuration from bot-secrets.env file with fallbacks"""
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=True)
        except ImportError:
            logger.warning("python-dotenv not installed, loading from environment only")
        except FileNotFoundError:
            logger.info(f"No {env_file} file found, using environment variables and defaults")
        
        return cls._load_from_environment()
    
    @classmethod
    def _load_from_environment(cls) -> 'BotConfig':
        """Load configuration from environment variables"""
        
        # Helper function for safe type conversion
        def get_env(key: str, default, converter=str):
            value = os.getenv(key)
            if value is None:
                return default
            try:
                if converter == bool:
                    return value.lower() not in ('false', '0', 'no', 'off', 'disabled')
                return converter(value)
            except (ValueError, TypeError):
                logger.warning(f"Invalid value for {key}: {value}, using default: {default}")
                return default
        
        # Parse admin ID safely
        admin_id = get_env('AUTHORIZED_ADMIN_ID', None)
        admin_id = int(admin_id) if admin_id and admin_id.isdigit() else None
        
        return cls(
            # Credentials
            TELEGRAM_BOT_TOKEN=get_env('TELEGRAM_BOT_TOKEN', ""),
            AUTHORIZED_ADMIN_ID=admin_id,
            API_ID=get_env('API_ID', None),
            API_HASH=get_env('API_HASH', None),
            PHONE_NUMBER=get_env('PHONE_NUMBER', None),
            SESSION_NAME=get_env('SESSION_NAME', cls.SESSION_NAME),
            
            # Database
            DATABASE_PATH=get_env('DATABASE_PATH', cls.DATABASE_PATH),
            DB_POOL_SIZE=get_env('DB_POOL_SIZE', cls.DB_POOL_SIZE, int),
            DB_TIMEOUT=get_env('DB_TIMEOUT', cls.DB_TIMEOUT, int),
            DB_BUSY_TIMEOUT=get_env('DB_BUSY_TIMEOUT', cls.DB_BUSY_TIMEOUT, int),
            
            # Timeouts
            TELEGRAM_API_TIMEOUT=get_env('TELEGRAM_API_TIMEOUT', cls.TELEGRAM_API_TIMEOUT, int),
            USER_MONITOR_TIMEOUT=get_env('USER_MONITOR_TIMEOUT', cls.USER_MONITOR_TIMEOUT, int),
            CHANNEL_VALIDATION_TIMEOUT=get_env('CHANNEL_VALIDATION_TIMEOUT', cls.CHANNEL_VALIDATION_TIMEOUT, int),
            AUTH_TIMEOUT=get_env('AUTH_TIMEOUT', cls.AUTH_TIMEOUT, int),
            
            # Rate limiting
            MESSAGE_FORWARD_DELAY=get_env('MESSAGE_FORWARD_DELAY', cls.MESSAGE_FORWARD_DELAY, float),
            MAX_FORWARDS_PER_MINUTE=get_env('MAX_FORWARDS_PER_MINUTE', cls.MAX_FORWARDS_PER_MINUTE, int),
            RECONNECT_DELAY=get_env('RECONNECT_DELAY', cls.RECONNECT_DELAY, int),
            
            # User limits
            MAX_KEYWORDS_PER_USER=get_env('MAX_KEYWORDS_PER_USER', cls.MAX_KEYWORDS_PER_USER, int),
            MAX_IGNORE_KEYWORDS=get_env('MAX_IGNORE_KEYWORDS', cls.MAX_IGNORE_KEYWORDS, int),
            MAX_KEYWORD_LENGTH=get_env('MAX_KEYWORD_LENGTH', cls.MAX_KEYWORD_LENGTH, int),
            MAX_DAILY_FORWARDS_PER_USER=get_env('MAX_DAILY_FORWARDS_PER_USER', cls.MAX_DAILY_FORWARDS_PER_USER, int),
            
            # Reconnection
            MAX_RECONNECT_ATTEMPTS=get_env('MAX_RECONNECT_ATTEMPTS', cls.MAX_RECONNECT_ATTEMPTS, int),
            RECONNECT_BACKOFF_MULTIPLIER=get_env('RECONNECT_BACKOFF_MULTIPLIER', cls.RECONNECT_BACKOFF_MULTIPLIER, float),
            MAX_RECONNECT_DELAY=get_env('MAX_RECONNECT_DELAY', cls.MAX_RECONNECT_DELAY, int),
            KEEP_ALIVE_INTERVAL=get_env('KEEP_ALIVE_INTERVAL', cls.KEEP_ALIVE_INTERVAL, int),
            
            # Monitoring
            HEALTH_CHECK_INTERVAL=get_env('HEALTH_CHECK_INTERVAL', cls.HEALTH_CHECK_INTERVAL, int),
            ERROR_NOTIFICATION_COOLDOWN=get_env('ERROR_NOTIFICATION_COOLDOWN', cls.ERROR_NOTIFICATION_COOLDOWN, int),
            BACKUP_RETENTION_DAYS=get_env('BACKUP_RETENTION_DAYS', cls.BACKUP_RETENTION_DAYS, int),
            
            # Feature flags
            ENABLE_USER_MONITOR=get_env('ENABLE_USER_MONITOR', cls.ENABLE_USER_MONITOR, bool),
            ENABLE_ERROR_MONITORING=get_env('ENABLE_ERROR_MONITORING', cls.ENABLE_ERROR_MONITORING, bool),
            ENABLE_AUTO_BACKUPS=get_env('ENABLE_AUTO_BACKUPS', cls.ENABLE_AUTO_BACKUPS, bool),
            ENABLE_METRICS_COLLECTION=get_env('ENABLE_METRICS_COLLECTION', cls.ENABLE_METRICS_COLLECTION, bool),
            ENABLE_WEBHOOK_MODE=get_env('ENABLE_WEBHOOK_MODE', cls.ENABLE_WEBHOOK_MODE, bool),
            
            # UI
            DEFAULT_LANGUAGE=get_env('DEFAULT_LANGUAGE', cls.DEFAULT_LANGUAGE),
            SHOW_ADVANCED_FEATURES=get_env('SHOW_ADVANCED_FEATURES', cls.SHOW_ADVANCED_FEATURES, bool),
            
            # Logging
            LOG_LEVEL=get_env('LOG_LEVEL', cls.LOG_LEVEL).upper(),
            LOG_TO_FILE=get_env('LOG_TO_FILE', cls.LOG_TO_FILE, bool),
            LOG_FILE_PATH=get_env('LOG_FILE_PATH', cls.LOG_FILE_PATH),
            MAX_LOG_FILE_SIZE=get_env('MAX_LOG_FILE_SIZE', cls.MAX_LOG_FILE_SIZE, int),
            
            # Backup
            BACKUP_DIRECTORY=get_env('BACKUP_DIRECTORY', cls.BACKUP_DIRECTORY),
            AUTO_BACKUP_INTERVAL=get_env('AUTO_BACKUP_INTERVAL', cls.AUTO_BACKUP_INTERVAL, int),
            AUTO_BACKUP_RETENTION=get_env('AUTO_BACKUP_RETENTION', cls.AUTO_BACKUP_RETENTION, int),
        )
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        # Required credentials
        if not self.TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN is required")
            
        # User monitor validation
        if self.ENABLE_USER_MONITOR:
            if not all([self.API_ID, self.API_HASH, self.PHONE_NUMBER]):
                errors.append("User monitor enabled but missing API_ID, API_HASH, or PHONE_NUMBER")
        
        # Numeric validations
        if self.DB_POOL_SIZE < 1:
            errors.append("DB_POOL_SIZE must be at least 1")
            
        if self.MESSAGE_FORWARD_DELAY < 0:
            errors.append("MESSAGE_FORWARD_DELAY cannot be negative")
            
        if self.MAX_KEYWORDS_PER_USER < 1:
            errors.append("MAX_KEYWORDS_PER_USER must be at least 1")
            
        if self.MAX_RECONNECT_ATTEMPTS < 1:
            errors.append("MAX_RECONNECT_ATTEMPTS must be at least 1")
        
        # Path validations
        if self.LOG_TO_FILE:
            log_dir = Path(self.LOG_FILE_PATH).parent
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                errors.append(f"Cannot create log directory: {log_dir}")
        
        # Database path validation
        db_dir = Path(self.DATABASE_PATH).parent
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            errors.append(f"Cannot create database directory: {db_dir}")
            
        return errors
    
    def setup_logging(self):
        """Configure logging based on config settings"""
        # Create log directory if needed
        if self.LOG_TO_FILE:
            log_dir = Path(self.LOG_FILE_PATH).parent
            log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure logging
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        handlers = []
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(console_handler)
        
        # File handler with rotation
        if self.LOG_TO_FILE:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                self.LOG_FILE_PATH,
                maxBytes=self.MAX_LOG_FILE_SIZE,
                backupCount=self.LOG_ROTATION_COUNT
            )
            file_handler.setFormatter(logging.Formatter(log_format))
            handlers.append(file_handler)
        
        # Configure root logger
        logging.basicConfig(
            level=getattr(logging, self.LOG_LEVEL, logging.INFO),
            handlers=handlers,
            force=True  # Override any existing configuration
        )
        
        logger.info(f"Logging configured: level={self.LOG_LEVEL}, file={self.LOG_TO_FILE}")
    
    def get_user_monitor_credentials(self) -> Optional[dict]:
        """Get user monitor credentials if available and enabled"""
        if not self.ENABLE_USER_MONITOR:
            return None
            
        if not all([self.API_ID, self.API_HASH, self.PHONE_NUMBER]):
            return None
            
        return {
            'api_id': int(self.API_ID),
            'api_hash': self.API_HASH,
            'phone': self.PHONE_NUMBER,
            'session_name': self.SESSION_NAME
        }
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user ID is authorized admin"""
        return self.AUTHORIZED_ADMIN_ID is not None and user_id == self.AUTHORIZED_ADMIN_ID
    
    def __post_init__(self):
        """Post-initialization validation and setup"""
        # Ensure directories exist
        Path(self.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(self.BACKUP_DIRECTORY).mkdir(parents=True, exist_ok=True)
        
        if self.LOG_TO_FILE:
            Path(self.LOG_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)