"""
FILE: 0_shared/db_logging.py
PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Database Logging Module
DESCRIPTION:
  Database operations for persisting logs, errors, and metrics to TimescaleDB.
  Provides async interfaces for:
    - Storing error events
    - Storing application logs
    - Storing performance metrics
    - Storing system alerts
    - Querying and aggregating data

USAGE:
  from db_logging import DatabaseLogger
  
  db_logger = DatabaseLogger(db_pool=pool)
  
  await db_logger.log_error_event(error_event)
  await db_logger.log_application_log(log_data)
  errors = await db_logger.get_recent_errors(hours=24)
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Any
from dataclasses import asdict


class DatabaseLogger:
    """Handles database operations for logging and error tracking."""
    
    def __init__(self, db_pool, logger=None):
        """
        Initialize database logger.
        
        Args:
            db_pool: asyncpg connection pool
            logger: Logger instance
        """
        self.db_pool = db_pool
        self.logger = logger
    
    async def log_error_event(
        self,
        error_event: 'ErrorEvent',
    ) -> bool:
        """
        Persist error event to database.
        
        Args:
            error_event: ErrorEvent object to log
        
        Returns:
            bool: Success status
        """
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
                    f"Failed to log error event: {e}",
                    error_code="DB_LOG_ERROR_FAILED",
                )
            return False
    
    async def log_application_log(
        self,
        app_name: str,
        logger_name: str,
        level: str,
        message: str,
        component: Optional[str] = None,
        module: Optional[str] = None,
        function_name: Optional[str] = None,
        line_number: Optional[int] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
    ) -> bool:
        """
        Persist application log to database.
        
        Args:
            app_name: Application name
            logger_name: Logger name
            level: Log level
            message: Log message
            component: Component name
            module: Module name
            function_name: Function name
            line_number: Line number
            extra_data: Additional data
            duration_ms: Operation duration
        
        Returns:
            bool: Success status
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO application_logs (
                        app_name, logger_name, level, message,
                        component, module, function_name, line_number,
                        extra_data, duration_ms
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                    app_name,
                    logger_name,
                    level,
                    message,
                    component,
                    module,
                    function_name,
                    line_number,
                    json.dumps(extra_data) if extra_data else None,
                    duration_ms,
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to log application log: {e}",
                    error_code="DB_LOG_APP_FAILED",
                )
            return False
    
    async def log_performance_metric(
        self,
        metric_name: str,
        metric_value: float,
        component: str,
        operation_name: Optional[str] = None,
        unit: str = "ms",
        tags: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Persist performance metric to database.
        
        Args:
            metric_name: Metric name
            metric_value: Metric value
            component: Component name
            operation_name: Operation name
            unit: Unit of measurement
            tags: Additional tags
        
        Returns:
            bool: Success status
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO performance_metrics (
                        metric_name, metric_value, component,
                        operation_name, unit, tags
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    metric_name,
                    metric_value,
                    component,
                    operation_name,
                    unit,
                    json.dumps(tags) if tags else None,
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to log performance metric: {e}",
                    error_code="DB_LOG_METRIC_FAILED",
                )
            return False
    
    async def log_system_alert(
        self,
        alert_type: str,
        message: str,
        severity: str,
        component: Optional[str] = None,
        related_errors: Optional[List[Dict]] = None,
    ) -> bool:
        """
        Persist system alert to database.
        
        Args:
            alert_type: Alert type
            message: Alert message
            severity: Alert severity
            component: Component name
            related_errors: Related error data
        
        Returns:
            bool: Success status
        """
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO system_alerts (
                        alert_type, message, severity, component,
                        related_errors
                    ) VALUES ($1, $2, $3, $4, $5)
                """,
                    alert_type,
                    message,
                    severity,
                    component,
                    json.dumps(related_errors) if related_errors else None,
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to log system alert: {e}",
                    error_code="DB_LOG_ALERT_FAILED",
                )
            return False
    
    async def get_recent_errors(
        self,
        hours: int = 24,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get recent errors from database."""
        try:
            async with self.db_pool.acquire() as conn:
                query = """
                    SELECT * FROM error_events
                    WHERE timestamp > NOW() - INTERVAL '%d hours'
                """ % hours
                
                params = []
                if category:
                    query += " AND category = $%d" % (len(params) + 1)
                    params.append(category)
                
                if severity:
                    query += " AND severity = $%d" % (len(params) + 1)
                    params.append(severity)
                
                query += " ORDER BY timestamp DESC LIMIT $%d" % (len(params) + 1)
                params.append(limit)
                
                rows = await conn.fetch(query, *params)
                
                return [dict(row) for row in rows]
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to query recent errors: {e}",
                    error_code="DB_QUERY_ERRORS_FAILED",
                )
            return []
    
    async def get_error_stats(
        self,
        hours: int = 24,
    ) -> Dict[str, Any]:
        """Get error statistics."""
        try:
            async with self.db_pool.acquire() as conn:
                query = """
                    SELECT
                        category,
                        severity,
                        COUNT(*) as count
                    FROM error_events
                    WHERE timestamp > NOW() - INTERVAL '%d hours'
                    GROUP BY category, severity
                    ORDER BY count DESC
                """ % hours
                
                rows = await conn.fetch(query)
                
                stats = {
                    "total_errors": sum(row["count"] for row in rows),
                    "by_category_severity": [dict(row) for row in rows],
                }
                
                return stats
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to query error stats: {e}",
                    error_code="DB_QUERY_STATS_FAILED",
                )
            return {}
    
    async def get_component_status(
        self,
        component: str,
        hours: int = 1,
    ) -> Dict[str, Any]:
        """Get component status and recent errors."""
        try:
            async with self.db_pool.acquire() as conn:
                # Get error counts
                error_counts = await conn.fetch("""
                    SELECT severity, COUNT(*) as count
                    FROM error_events
                    WHERE component = $1
                    AND timestamp > NOW() - INTERVAL '%d hours'
                    GROUP BY severity
                """ % hours, component)
                
                error_map = {row["severity"]: row["count"] for row in error_counts}
                
                # Get recent errors
                recent_errors = await conn.fetch("""
                    SELECT id, timestamp, severity, message, error_code
                    FROM error_events
                    WHERE component = $1
                    AND timestamp > NOW() - INTERVAL '%d hours'
                    ORDER BY timestamp DESC
                    LIMIT 10
                """ % hours, component)
                
                return {
                    "component": component,
                    "error_counts": error_map,
                    "critical_count": error_map.get("critical", 0),
                    "error_count": error_map.get("error", 0),
                    "warning_count": error_map.get("warning", 0),
                    "recent_errors": [dict(row) for row in recent_errors],
                }
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to query component status: {e}",
                    error_code="DB_QUERY_COMPONENT_FAILED",
                )
            return {}
    
    async def get_active_alerts(
        self,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get active (unacknowledged) alerts."""
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM system_alerts
                    WHERE acknowledged = FALSE
                    ORDER BY timestamp DESC
                    LIMIT $1
                """, limit)
                
                return [dict(row) for row in rows]
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to query active alerts: {e}",
                    error_code="DB_QUERY_ALERTS_FAILED",
                )
            return []
    
    async def acknowledge_alert(
        self,
        alert_id: int,
        acknowledged_by: str = "system",
    ) -> bool:
        """Mark alert as acknowledged."""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE system_alerts
                    SET acknowledged = TRUE,
                        acknowledged_at = NOW(),
                        acknowledged_by = $1
                    WHERE id = $2
                """, acknowledged_by, alert_id)
            return True
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to acknowledge alert: {e}",
                    error_code="DB_UPDATE_ALERT_FAILED",
                )
            return False
    
    async def cleanup_old_logs(
        self,
        days: int = 30,
    ) -> Dict[str, int]:
        """Clean up old logs and data."""
        try:
            async with self.db_pool.acquire() as conn:
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                
                # Count and delete old error events
                error_result = await conn.fetchval("""
                    DELETE FROM error_events
                    WHERE timestamp < $1
                """, cutoff)
                
                # Count and delete old logs
                log_result = await conn.fetchval("""
                    DELETE FROM application_logs
                    WHERE timestamp < $1
                """, cutoff)
                
                # Count and delete old metrics
                metric_result = await conn.fetchval("""
                    DELETE FROM performance_metrics
                    WHERE timestamp < $1
                """, cutoff)
                
                return {
                    "errors_deleted": error_result or 0,
                    "logs_deleted": log_result or 0,
                    "metrics_deleted": metric_result or 0,
                }
        except Exception as e:
            if self.logger:
                self.logger.error_structured(
                    f"Failed to cleanup old logs: {e}",
                    error_code="DB_CLEANUP_FAILED",
                )
            return {}
