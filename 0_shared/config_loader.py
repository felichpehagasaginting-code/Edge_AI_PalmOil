"""
FILE: 0_shared/config_loader.py
PROJECT: Error Tracking and Logging System — Configuration Loader
DESCRIPTION:
  Load and parse YAML configuration for the logging system.
  Provides configuration objects for all system components.

USAGE:
  from config_loader import load_logging_config
  config = load_logging_config()
  
  # Access configuration
  log_level = config.logging.log_level
  db_host = config.database.host
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class LoggingConfig:
    """Logging configuration."""
    enabled: bool = True
    log_level: str = "INFO"
    file_enabled: bool = True
    file_directory: str = "logs"
    file_max_size_mb: int = 10
    file_backup_count: int = 10
    console_enabled: bool = True
    structured_enabled: bool = True


@dataclass
class ErrorTrackingConfig:
    """Error tracking configuration."""
    enabled: bool = True
    error_spike_count: int = 10
    error_spike_window_seconds: int = 60
    repeated_error_count: int = 5
    repeated_error_window_seconds: int = 300
    persistence_enabled: bool = True
    retention_days: int = 30


@dataclass
class PerformanceConfig:
    """Performance monitoring configuration."""
    enabled: bool = True
    retention_hours: int = 24
    db_query_sla_ms: float = 100
    api_response_sla_ms: float = 200
    mqtt_message_sla_ms: float = 500
    min_success_rate: float = 0.99


@dataclass
class DatabaseConfig:
    """Database configuration."""
    enabled: bool = True
    host: str = "timescaledb"
    port: int = 5432
    name: str = "grading_db"
    user: str = "tbs_user"
    password: str = "secure_db_pass_123"
    pool_min_size: int = 2
    pool_max_size: int = 10


@dataclass
class AlertingConfig:
    """Alerting configuration."""
    enabled: bool = True
    channels: Dict[str, Any] = None
    routing: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.channels is None:
            self.channels = {
                "log": {"enabled": True},
                "database": {"enabled": True},
            }
        if self.routing is None:
            self.routing = {
                "critical": {"delay_seconds": 0},
                "error": {"delay_seconds": 5},
                "warning": {"delay_seconds": 30},
            }


@dataclass
class SystemConfig:
    """Complete system configuration."""
    logging: LoggingConfig
    error_tracking: ErrorTrackingConfig
    performance: PerformanceConfig
    database: DatabaseConfig
    alerting: AlertingConfig
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "SystemConfig":
        """Create config from dictionary."""
        return cls(
            logging=LoggingConfig(
                enabled=config_dict.get("logging", {}).get("enabled", True),
                log_level=config_dict.get("logging", {}).get("log_level", "INFO"),
                file_enabled=config_dict.get("logging", {}).get("file", {}).get("enabled", True),
                file_directory=config_dict.get("logging", {}).get("file", {}).get("directory", "logs"),
                file_max_size_mb=config_dict.get("logging", {}).get("file", {}).get("max_size_mb", 10),
                file_backup_count=config_dict.get("logging", {}).get("file", {}).get("backup_count", 10),
                console_enabled=config_dict.get("logging", {}).get("console", {}).get("enabled", True),
                structured_enabled=config_dict.get("logging", {}).get("structured", {}).get("enabled", True),
            ),
            error_tracking=ErrorTrackingConfig(
                enabled=config_dict.get("error_tracking", {}).get("enabled", True),
                error_spike_count=config_dict.get("error_tracking", {}).get("alerts", {}).get("error_spike_count", 10),
                error_spike_window_seconds=config_dict.get("error_tracking", {}).get("alerts", {}).get("error_spike_window_seconds", 60),
                repeated_error_count=config_dict.get("error_tracking", {}).get("alerts", {}).get("repeated_error_count", 5),
                repeated_error_window_seconds=config_dict.get("error_tracking", {}).get("alerts", {}).get("repeated_error_window_seconds", 300),
                persistence_enabled=config_dict.get("error_tracking", {}).get("persistence", {}).get("enabled", True),
                retention_days=config_dict.get("error_tracking", {}).get("retention", {}).get("days", 30),
            ),
            performance=PerformanceConfig(
                enabled=config_dict.get("performance", {}).get("enabled", True),
                retention_hours=config_dict.get("performance", {}).get("collection", {}).get("retention_hours", 24),
                db_query_sla_ms=config_dict.get("performance", {}).get("collection", {}).get("sla", {}).get("database_query_latency_ms", 100),
                api_response_sla_ms=config_dict.get("performance", {}).get("collection", {}).get("sla", {}).get("api_response_latency_ms", 200),
                mqtt_message_sla_ms=config_dict.get("performance", {}).get("collection", {}).get("sla", {}).get("mqtt_message_latency_ms", 500),
                min_success_rate=config_dict.get("performance", {}).get("collection", {}).get("sla", {}).get("min_success_rate", 0.99),
            ),
            database=DatabaseConfig(
                enabled=config_dict.get("database", {}).get("enabled", True),
                host=config_dict.get("database", {}).get("host", "timescaledb"),
                port=config_dict.get("database", {}).get("port", 5432),
                name=config_dict.get("database", {}).get("name", "grading_db"),
                user=config_dict.get("database", {}).get("user", "tbs_user"),
                password=config_dict.get("database", {}).get("password", "secure_db_pass_123"),
                pool_min_size=config_dict.get("database", {}).get("pool", {}).get("min_size", 2),
                pool_max_size=config_dict.get("database", {}).get("pool", {}).get("max_size", 10),
            ),
            alerting=AlertingConfig(
                enabled=config_dict.get("alerting", {}).get("enabled", True),
            ),
        )


def load_logging_config(config_path: Optional[str] = None) -> SystemConfig:
    """
    Load logging configuration from YAML file.
    
    Args:
        config_path: Path to YAML config file. If None, uses default search paths.
    
    Returns:
        SystemConfig: Configuration object
    
    Raises:
        FileNotFoundError: If config file not found
    """
    # Try to find config file
    if config_path is None:
        search_paths = [
            Path("0_shared/logging_config.yaml"),
            Path("logging_config.yaml"),
            Path("/etc/iot_grad_scanner/logging_config.yaml"),
            Path(os.path.expanduser("~/.iot_grad_scanner/logging_config.yaml")),
        ]
        
        for path in search_paths:
            if path.exists():
                config_path = path
                break
        else:
            # Use default config
            return SystemConfig(
                logging=LoggingConfig(),
                error_tracking=ErrorTrackingConfig(),
                performance=PerformanceConfig(),
                database=DatabaseConfig(),
                alerting=AlertingConfig(),
            )
    
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    # Load YAML
    try:
        import yaml
        with open(config_path, 'r') as f:
            config_dict = yaml.safe_load(f) or {}
    except ImportError:
        # YAML not available, use defaults
        return SystemConfig(
            logging=LoggingConfig(),
            error_tracking=ErrorTrackingConfig(),
            performance=PerformanceConfig(),
            database=DatabaseConfig(),
            alerting=AlertingConfig(),
        )
    
    return SystemConfig.from_dict(config_dict)


def get_config(config_path: Optional[str] = None) -> SystemConfig:
    """Get configuration (singleton-like behavior)."""
    return load_logging_config(config_path)
