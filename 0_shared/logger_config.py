"""
FILE: 0_shared/logger_config.py
PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Shared Logging Module
DESCRIPTION:
  Centralized logging configuration module for the entire IoT system.
  Provides:
    - Structured JSON logging
    - File and console handlers
    - Log rotation and archiving
    - Error tracking integration
    - Performance metrics logging
    - Centralized configuration

USAGE:
  from logger_config import setup_logger, get_logger
  
  # Setup logger once at app startup
  setup_logger(app_name="api_server", log_level="INFO")
  
  # Get logger in any module
  logger = get_logger(__name__)
  logger.info("Message", extra={"user_id": 123})
"""

import os
import sys
import json
import logging
import logging.handlers
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def __init__(self, app_name: str):
        super().__init__()
        self.app_name = app_name
    
    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON format."""
        log_obj = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "app": self.app_name,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }
        
        # Add extra fields
        if hasattr(record, "extra_data"):
            log_obj["extra"] = record.extra_data
        
        # Add performance metrics if available
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms
        
        return json.dumps(log_obj, ensure_ascii=False)


class StructuredLogger(logging.Logger):
    """Extended logger with structured logging support."""
    
    def info_structured(self, message: str, **kwargs):
        """Log info with structured extra data."""
        record = self.makeRecord(
            self.name, logging.INFO, "", 0, message, (), None
        )
        record.extra_data = kwargs
        self.handle(record)
    
    def error_structured(self, message: str, error_code: str = None, **kwargs):
        """Log error with structured data."""
        record = self.makeRecord(
            self.name, logging.ERROR, "", 0, message, (), None
        )
        record.extra_data = {**kwargs, "error_code": error_code}
        self.handle(record)
    
    def warning_structured(self, message: str, **kwargs):
        """Log warning with structured data."""
        record = self.makeRecord(
            self.name, logging.WARNING, "", 0, message, (), None
        )
        record.extra_data = kwargs
        self.handle(record)
    
    def debug_structured(self, message: str, **kwargs):
        """Log debug with structured data."""
        record = self.makeRecord(
            self.name, logging.DEBUG, "", 0, message, (), None
        )
        record.extra_data = kwargs
        self.handle(record)


# Override logger class
logging.setLoggerClass(StructuredLogger)


class LoggerConfig:
    """Centralized logger configuration."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.app_name = "IoTSystem"
            self.log_dir = Path("logs")
            self.log_level = logging.INFO
            self._initialized = True
    
    def setup(
        self,
        app_name: str,
        log_level: str = "INFO",
        log_dir: str = "logs",
        enable_file: bool = True,
        enable_console: bool = True,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 10,
    ) -> None:
        """
        Initialize centralized logging.
        
        Args:
            app_name: Application/service name
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_dir: Directory for log files
            enable_file: Enable file logging
            enable_console: Enable console logging
            max_bytes: Max size for log file before rotation
            backup_count: Number of backup log files to keep
        """
        self.app_name = app_name
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log_dir = Path(log_dir)
        
        # Create log directory if needed
        if enable_file:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # JSON formatter
        json_formatter = JSONFormatter(app_name)
        
        # Console handler
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            console_handler.setFormatter(json_formatter)
            root_logger.addHandler(console_handler)
        
        # File handler with rotation
        if enable_file:
            log_file = self.log_dir / f"{app_name}.log"
            file_handler = logging.handlers.RotatingFileHandler(
                str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
            )
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(json_formatter)
            root_logger.addHandler(file_handler)
    
    def get_logger(self, name: str) -> StructuredLogger:
        """Get logger instance."""
        return logging.getLogger(name)


# Singleton instance
_config = LoggerConfig()


def setup_logger(
    app_name: str,
    log_level: str = "INFO",
    log_dir: str = "logs",
    enable_file: bool = True,
    enable_console: bool = True,
) -> None:
    """
    Setup centralized logging system.
    Call this once at application startup.
    """
    _config.setup(
        app_name=app_name,
        log_level=log_level,
        log_dir=log_dir,
        enable_file=enable_file,
        enable_console=enable_console,
    )


def get_logger(name: str) -> StructuredLogger:
    """Get logger instance by name."""
    return _config.get_logger(name)
