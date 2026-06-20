"""
FILE: 0_shared/error_tracker.py
PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Error Tracking Module
DESCRIPTION:
  Comprehensive error tracking and alerting system for the IoT ecosystem.
  Features:
    - Error categorization and severity levels
    - Error counting and rate tracking
    - Automatic alerts for critical errors
    - Error context preservation
    - Performance impact tracking
    - Database persistence integration

USAGE:
  from error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity
  
  tracker = ErrorTracker(db_pool=pool)
  tracker.track_error(
      category=ErrorCategory.DATABASE,
      severity=ErrorSeverity.CRITICAL,
      message="Connection timeout",
      context={"host": "db.example.com"}
  )
"""

import json
import time
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Any, Callable
from dataclasses import dataclass, asdict
from collections import defaultdict
import asyncio


class ErrorCategory(str, Enum):
    """Error categories for classification."""
    DATABASE = "database"
    MQTT = "mqtt"
    DEVICE_COMM = "device_communication"
    DATA_PROCESSING = "data_processing"
    API = "api"
    AUTHENTICATION = "authentication"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of alerts."""
    ERROR_SPIKE = "error_spike"
    REPEATED_ERROR = "repeated_error"
    CRITICAL_ERROR = "critical_error"
    THRESHOLD_BREACH = "threshold_breach"


@dataclass
class ErrorEvent:
    """Represents a single error event."""
    timestamp: datetime
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    context: Dict[str, Any]
    error_code: Optional[str] = None
    traceback: Optional[str] = None
    component: str = "unknown"
    resolved: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["category"] = self.category.value
        data["severity"] = self.severity.value
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class Alert:
    """Represents an alert."""
    timestamp: datetime
    alert_type: AlertType
    message: str
    severity: ErrorSeverity
    related_errors: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "alert_type": self.alert_type.value,
            "message": self.message,
            "severity": self.severity.value,
            "related_errors": self.related_errors,
        }


class ErrorTracker:
    """Central error tracking system."""
    
    def __init__(
        self,
        db_pool=None,
        logger=None,
        alert_callback: Optional[Callable] = None,
        alert_thresholds: Optional[Dict[str, int]] = None,
    ):
        """
        Initialize error tracker.
        
        Args:
            db_pool: Database connection pool for persistence
            logger: Logger instance
            alert_callback: Async callback for alerts
            alert_thresholds: Thresholds for triggering alerts
        """
        self.db_pool = db_pool
        self.logger = logger
        self.alert_callback = alert_callback
        
        # Default thresholds
        self.alert_thresholds = alert_thresholds or {
            "error_spike_count": 10,  # Errors in 1 minute window
            "error_spike_window_seconds": 60,
            "repeated_error_count": 5,  # Same error repeated
            "repeated_error_window_seconds": 300,  # In 5 minutes
        }
        
        # In-memory tracking
        self.error_history: List[ErrorEvent] = []
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.last_errors: Dict[str, ErrorEvent] = {}
        self.alerts: List[Alert] = []
        self.error_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "first_seen": None,
                "last_seen": None,
                "severity_counts": defaultdict(int),
            }
        )
    
    def track_error(
        self,
        category: ErrorCategory,
        severity: ErrorSeverity,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        traceback: Optional[str] = None,
        component: str = "unknown",
    ) -> ErrorEvent:
        """
        Track an error event.
        
        Args:
            category: Error category
            severity: Error severity
            message: Error message
            context: Additional context data
            error_code: Error code for tracking
            traceback: Exception traceback
            component: Component/service name
        
        Returns:
            ErrorEvent: The created error event
        """
        now = datetime.now(timezone.utc)
        
        error_event = ErrorEvent(
            timestamp=now,
            category=category,
            severity=severity,
            message=message,
            context=context or {},
            error_code=error_code,
            traceback=traceback,
            component=component,
        )
        
        # Add to history
        self.error_history.append(error_event)
        
        # Keep only last 1000 errors in memory
        if len(self.error_history) > 1000:
            self.error_history = self.error_history[-1000:]
        
        # Update statistics
        error_key = f"{category.value}:{error_code or message}"
        stats = self.error_stats[error_key]
        stats["count"] += 1
        stats["last_seen"] = now
        if stats["first_seen"] is None:
            stats["first_seen"] = now
        stats["severity_counts"][severity.value] += 1
        
        # Track for alert detection
        self.error_counts[error_key] += 1
        self.last_errors[error_key] = error_event
        
        # Check for alerts
        asyncio.create_task(self._check_and_trigger_alerts(error_event))
        
        # Log the error
        if self.logger:
            self.logger.error_structured(
                message,
                error_code=error_code,
                category=category.value,
                severity=severity.value,
                component=component,
                context=context,
                traceback=traceback,
            )
        
        return error_event
    
    async def _check_and_trigger_alerts(self, error_event: ErrorEvent) -> None:
        """Check if error triggers alerts."""
        alerts = self._generate_alerts(error_event)
        
        for alert in alerts:
            self.alerts.append(alert)
            if self.logger:
                self.logger.warning_structured(
                    f"Alert: {alert.message}",
                    alert_type=alert.alert_type.value,
                    severity=alert.severity.value,
                )
            
            if self.alert_callback:
                try:
                    await self.alert_callback(alert)
                except Exception as e:
                    if self.logger:
                        self.logger.error_structured(
                            f"Alert callback failed: {e}",
                            error_code="ALERT_CALLBACK_ERROR",
                        )
    
    def _generate_alerts(self, error_event: ErrorEvent) -> List[Alert]:
        """Generate alerts based on error event."""
        alerts = []
        now = datetime.now(timezone.utc)
        
        # Critical error alert
        if error_event.severity == ErrorSeverity.CRITICAL:
            alerts.append(Alert(
                timestamp=now,
                alert_type=AlertType.CRITICAL_ERROR,
                message=f"Critical error in {error_event.component}: {error_event.message}",
                severity=ErrorSeverity.CRITICAL,
                related_errors=[error_event.to_dict()],
            ))
        
        # Error spike detection
        error_key = f"{error_event.category.value}:{error_event.error_code or error_event.message}"
        window_start = now - timedelta(
            seconds=self.alert_thresholds["error_spike_window_seconds"]
        )
        
        recent_errors = [
            e for e in self.error_history
            if e.timestamp > window_start
            and f"{e.category.value}:{e.error_code or e.message}" == error_key
        ]
        
        if len(recent_errors) >= self.alert_thresholds["error_spike_count"]:
            alerts.append(Alert(
                timestamp=now,
                alert_type=AlertType.ERROR_SPIKE,
                message=f"Error spike detected: {len(recent_errors)} errors in {error_key}",
                severity=ErrorSeverity.WARNING,
                related_errors=[e.to_dict() for e in recent_errors[-5:]],
            ))
        
        # Repeated error detection
        if len(recent_errors) >= self.alert_thresholds["repeated_error_count"]:
            alerts.append(Alert(
                timestamp=now,
                alert_type=AlertType.REPEATED_ERROR,
                message=f"Repeated error: {error_key} (count: {len(recent_errors)})",
                severity=ErrorSeverity.WARNING,
                related_errors=[e.to_dict() for e in recent_errors[-3:]],
            ))
        
        return alerts
    
    def get_error_stats(
        self,
        category: Optional[ErrorCategory] = None,
        minutes: int = 60,
    ) -> Dict[str, Any]:
        """Get error statistics."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=minutes)
        
        recent_errors = [
            e for e in self.error_history
            if e.timestamp > window_start
            and (category is None or e.category == category)
        ]
        
        stats_by_category = defaultdict(lambda: {"count": 0, "by_severity": defaultdict(int)})
        
        for error in recent_errors:
            category_key = error.category.value
            stats_by_category[category_key]["count"] += 1
            stats_by_category[category_key]["by_severity"][error.severity.value] += 1
        
        return {
            "total_errors": len(recent_errors),
            "by_category": dict(stats_by_category),
            "time_window_minutes": minutes,
        }
    
    def get_recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent errors."""
        return [e.to_dict() for e in self.error_history[-limit:]]
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts."""
        # Keep only last 100 alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
        
        return [a.to_dict() for a in self.alerts[-10:]]
    
    def get_component_health(self, component: str) -> Dict[str, Any]:
        """Get health status of a component."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=60)
        
        component_errors = [
            e for e in self.error_history
            if e.component == component and e.timestamp > window_start
        ]
        
        critical_count = sum(1 for e in component_errors if e.severity == ErrorSeverity.CRITICAL)
        error_count = sum(1 for e in component_errors if e.severity == ErrorSeverity.ERROR)
        warning_count = sum(1 for e in component_errors if e.severity == ErrorSeverity.WARNING)
        
        # Determine health status
        if critical_count > 0:
            health_status = "critical"
        elif error_count > 5:
            health_status = "degraded"
        elif error_count > 0:
            health_status = "unhealthy"
        elif warning_count > 10:
            health_status = "warning"
        else:
            health_status = "healthy"
        
        return {
            "component": component,
            "status": health_status,
            "critical_errors": critical_count,
            "errors": error_count,
            "warnings": warning_count,
            "last_hour_error_count": len(component_errors),
        }
    
    async def persist_to_database(self, error_event: ErrorEvent) -> bool:
        """Persist error event to database."""
        if not self.db_pool:
            return False
        
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO error_events (
                        timestamp, category, severity, message,
                        error_code, component, context, traceback
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """, 
                    error_event.timestamp,
                    error_event.category.value,
                    error_event.severity.value,
                    error_event.message,
                    error_event.error_code,
                    error_event.component,
                    json.dumps(error_event.context),
                    error_event.traceback,
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to persist error to database: {e}",
                    error_code="DB_PERSIST_FAILED",
                )
            return False
    
    def clear_old_errors(self, days: int = 7) -> int:
        """Clear errors older than specified days."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        
        original_count = len(self.error_history)
        self.error_history = [
            e for e in self.error_history if e.timestamp > cutoff
        ]
        
        return original_count - len(self.error_history)
