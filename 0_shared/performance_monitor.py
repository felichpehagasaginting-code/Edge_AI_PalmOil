"""
FILE: 0_shared/performance_monitor.py
PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Performance Monitoring
DESCRIPTION:
  Performance monitoring and metrics collection system.
  Tracks:
    - Operation duration and latency
    - Throughput metrics
    - Resource usage (if available)
    - Performance degradation alerts
    - SLA tracking

USAGE:
  from performance_monitor import PerformanceMonitor
  
  monitor = PerformanceMonitor(logger=logger)
  
  # Using as context manager
  with monitor.track_operation("database_query", component="api"):
      result = db.query(...)
  
  # Manual tracking
  monitor.record_metric("inference_time_ms", value=45.2, component="edge_device")
  
  # Get metrics
  stats = monitor.get_metric_stats("inference_time_ms")
"""

import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Any, Generator
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class MetricPoint:
    """A single metric measurement."""
    timestamp: datetime
    value: float
    component: str
    operation: Optional[str] = None
    tags: Optional[Dict[str, str]] = None


class PerformanceMonitor:
    """Performance metrics collection and analysis."""
    
    def __init__(self, logger=None, retention_hours: int = 24):
        """
        Initialize performance monitor.
        
        Args:
            logger: Logger instance
            retention_hours: How long to keep metrics in memory
        """
        self.logger = logger
        self.retention_hours = retention_hours
        self.metrics: Dict[str, List[MetricPoint]] = defaultdict(list)
        self.operation_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "total_time": 0.0,
                "min_time": float("inf"),
                "max_time": 0.0,
                "errors": 0,
            }
        )
    
    @contextmanager
    def track_operation(
        self,
        operation_name: str,
        component: str = "unknown",
        tags: Optional[Dict[str, str]] = None,
    ) -> Generator[None, None, None]:
        """
        Context manager for tracking operation duration.
        
        Args:
            operation_name: Name of the operation
            component: Component performing operation
            tags: Additional tags for the metric
        
        Yields:
            None
        """
        start_time = time.time()
        start_datetime = datetime.now(timezone.utc)
        error_occurred = False
        
        try:
            yield
        except Exception as e:
            error_occurred = True
            self.operation_stats[operation_name]["errors"] += 1
            if self.logger:
                self.logger.error_structured(
                    f"Operation failed: {operation_name}",
                    component=component,
                    error=str(e),
                )
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000
            self.record_metric(
                metric_name=f"{operation_name}_duration_ms",
                value=duration_ms,
                component=component,
                operation=operation_name,
                tags=tags,
            )
            
            # Update stats
            stats = self.operation_stats[operation_name]
            stats["count"] += 1
            stats["total_time"] += duration_ms
            stats["min_time"] = min(stats["min_time"], duration_ms)
            stats["max_time"] = max(stats["max_time"], duration_ms)
            
            if self.logger and not error_occurred:
                self.logger.debug_structured(
                    f"Operation completed: {operation_name}",
                    component=component,
                    duration_ms=round(duration_ms, 2),
                )
    
    def record_metric(
        self,
        metric_name: str,
        value: float,
        component: str = "unknown",
        operation: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a single metric point.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            component: Component reporting metric
            operation: Related operation
            tags: Additional tags
        """
        now = datetime.now(timezone.utc)
        point = MetricPoint(
            timestamp=now,
            value=value,
            component=component,
            operation=operation,
            tags=tags or {},
        )
        
        self.metrics[metric_name].append(point)
        
        # Clean old metrics
        self._cleanup_old_metrics(metric_name)
    
    def _cleanup_old_metrics(self, metric_name: str) -> None:
        """Remove metrics older than retention period."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.retention_hours)
        
        self.metrics[metric_name] = [
            m for m in self.metrics[metric_name]
            if m.timestamp > cutoff
        ]
    
    def get_metric_stats(
        self,
        metric_name: str,
        minutes: int = 60,
    ) -> Dict[str, Any]:
        """Get statistics for a metric."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=minutes)
        
        points = [
            m for m in self.metrics[metric_name]
            if m.timestamp > window_start
        ]
        
        if not points:
            return {
                "metric": metric_name,
                "count": 0,
                "data_points": [],
            }
        
        values = [p.value for p in points]
        
        return {
            "metric": metric_name,
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
            "p50": self._percentile(values, 50),
            "p95": self._percentile(values, 95),
            "p99": self._percentile(values, 99),
            "time_window_minutes": minutes,
        }
    
    def get_operation_stats(self) -> Dict[str, Any]:
        """Get aggregated operation statistics."""
        stats = {}
        
        for op_name, op_stats in self.operation_stats.items():
            if op_stats["count"] == 0:
                continue
            
            stats[op_name] = {
                "count": op_stats["count"],
                "total_time_ms": op_stats["total_time"],
                "avg_time_ms": op_stats["total_time"] / op_stats["count"],
                "min_time_ms": op_stats["min_time"] if op_stats["min_time"] != float("inf") else 0,
                "max_time_ms": op_stats["max_time"],
                "error_count": op_stats["errors"],
                "error_rate": op_stats["errors"] / op_stats["count"],
            }
        
        return stats
    
    def get_throughput(
        self,
        operation_name: str,
        minutes: int = 60,
    ) -> Dict[str, Any]:
        """Calculate throughput for an operation."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=minutes)
        
        metric_name = f"{operation_name}_duration_ms"
        points = [
            m for m in self.metrics[metric_name]
            if m.timestamp > window_start
        ]
        
        if not points or minutes == 0:
            return {
                "operation": operation_name,
                "throughput_per_minute": 0,
                "time_window_minutes": minutes,
            }
        
        throughput_per_minute = len(points) / minutes
        
        return {
            "operation": operation_name,
            "operation_count": len(points),
            "throughput_per_minute": round(throughput_per_minute, 2),
            "time_window_minutes": minutes,
        }
    
    def check_sla(
        self,
        operation_name: str,
        max_latency_ms: float,
        min_success_rate: float = 0.99,
        minutes: int = 60,
    ) -> Dict[str, Any]:
        """Check if operation meets SLA."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=minutes)
        
        metric_name = f"{operation_name}_duration_ms"
        points = [
            m for m in self.metrics[metric_name]
            if m.timestamp > window_start
        ]
        
        op_stats = self.operation_stats[operation_name]
        
        if op_stats["count"] == 0:
            return {
                "operation": operation_name,
                "sla_status": "unknown",
                "message": "No data available",
            }
        
        within_sla = sum(1 for p in points if p.value <= max_latency_ms)
        latency_sla_met = within_sla / len(points) >= (1 - (1 - min_success_rate))
        
        success_count = op_stats["count"] - op_stats["errors"]
        success_rate = success_count / op_stats["count"]
        success_sla_met = success_rate >= min_success_rate
        
        overall_sla_met = latency_sla_met and success_sla_met
        
        return {
            "operation": operation_name,
            "sla_status": "met" if overall_sla_met else "violated",
            "latency_sla_met": latency_sla_met,
            "success_sla_met": success_sla_met,
            "max_latency_ms": max_latency_ms,
            "actual_p95_latency_ms": self._percentile([p.value for p in points], 95),
            "success_rate": round(success_rate * 100, 2),
            "min_required_success_rate": round(min_success_rate * 100, 2),
            "time_window_minutes": minutes,
        }
    
    @staticmethod
    def _percentile(values: List[float], percentile: int) -> float:
        """Calculate percentile."""
        if not values:
            return 0
        
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def get_component_metrics(
        self,
        component: str,
        minutes: int = 60,
    ) -> Dict[str, Any]:
        """Get all metrics for a component."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=minutes)
        
        component_metrics = {}
        
        for metric_name, points in self.metrics.items():
            filtered_points = [
                p for p in points
                if p.component == component and p.timestamp > window_start
            ]
            
            if filtered_points:
                values = [p.value for p in filtered_points]
                component_metrics[metric_name] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values),
                }
        
        return {
            "component": component,
            "metrics": component_metrics,
            "time_window_minutes": minutes,
        }
