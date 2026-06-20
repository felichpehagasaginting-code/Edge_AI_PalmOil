"""
0_shared package - Error tracking and logging system for IoT Grad Scanner
"""

from .logger_config import setup_logger, get_logger
from .error_tracker import (
    ErrorTracker,
    ErrorCategory,
    ErrorSeverity,
    ErrorEvent,
    Alert,
    AlertType,
)
from .performance_monitor import PerformanceMonitor
from .db_logging import DatabaseLogger

__all__ = [
    "setup_logger",
    "get_logger",
    "ErrorTracker",
    "ErrorCategory",
    "ErrorSeverity",
    "ErrorEvent",
    "Alert",
    "AlertType",
    "PerformanceMonitor",
    "DatabaseLogger",
]

__version__ = "1.0.0"
