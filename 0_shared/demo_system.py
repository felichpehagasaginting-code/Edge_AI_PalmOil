"""
FILE: 0_shared/demo_system.py
PROJECT: Error Tracking and Logging System — Demo/Testing
DESCRIPTION:
  Comprehensive demo showing all features of the logging and error tracking system.
  Run this to test and understand the system capabilities.

USAGE:
  python demo_system.py

This will demonstrate:
  - Structured logging
  - Error tracking and categorization
  - Alert generation
  - Performance monitoring
  - Component health tracking
"""

import asyncio
import json
from datetime import datetime, timezone
from logger_config import setup_logger, get_logger
from error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity
from performance_monitor import PerformanceMonitor


def demo_structured_logging():
    """Demo 1: Structured logging capabilities."""
    print("\n" + "="*70)
    print("DEMO 1: Structured Logging")
    print("="*70)
    
    setup_logger(app_name="demo_app", log_level="DEBUG")
    logger = get_logger("demo")
    
    # Info with structured data
    logger.info_structured(
        "User login successful",
        user_id=12345,
        email="user@example.com",
        ip_address="192.168.1.100",
        session_duration_seconds=3600,
    )
    
    # Warning with context
    logger.warning_structured(
        "High API response time detected",
        endpoint="/api/data",
        response_time_ms=450,
        threshold_ms=200,
        component="api_server",
    )
    
    # Error with structured data
    logger.error_structured(
        "Database query timeout",
        error_code="DB_TIMEOUT_001",
        query_type="SELECT",
        duration_ms=30000,
        retries=3,
        component="database",
    )
    
    print("\n✓ Structured logs generated (check logs/ directory)")


def demo_error_tracking():
    """Demo 2: Error tracking and categorization."""
    print("\n" + "="*70)
    print("DEMO 2: Error Tracking and Categorization")
    print("="*70)
    
    setup_logger(app_name="demo_app", log_level="INFO")
    logger = get_logger("demo")
    
    # Create error tracker
    tracker = ErrorTracker(logger=logger)
    
    # Track different error categories
    errors = [
        {
            "category": ErrorCategory.DATABASE,
            "severity": ErrorSeverity.ERROR,
            "message": "Connection pool exhausted",
            "error_code": "DB_POOL_EXHAUSTED",
        },
        {
            "category": ErrorCategory.MQTT,
            "severity": ErrorSeverity.WARNING,
            "message": "MQTT broker disconnected",
            "error_code": "MQTT_DISCONNECT",
        },
        {
            "category": ErrorCategory.API,
            "severity": ErrorSeverity.CRITICAL,
            "message": "Authentication service unavailable",
            "error_code": "AUTH_UNAVAILABLE",
        },
        {
            "category": ErrorCategory.DATA_PROCESSING,
            "severity": ErrorSeverity.ERROR,
            "message": "Invalid JSON payload received",
            "error_code": "JSON_INVALID",
        },
    ]
    
    print("\nTracking errors:")
    for error_data in errors:
        error_event = tracker.track_error(
            category=error_data["category"],
            severity=error_data["severity"],
            message=error_data["message"],
            error_code=error_data["error_code"],
            component="demo_service",
            context={"retry_count": 3, "timestamp": datetime.now(timezone.utc).isoformat()},
        )
        print(f"  ✓ {error_data['category'].value}: {error_data['message']}")
    
    # Display statistics
    print("\nError Statistics:")
    stats = tracker.get_error_stats()
    print(f"  Total errors: {len(tracker.error_history)}")
    
    # Component health
    health = tracker.get_component_health("demo_service")
    print(f"\nComponent Health (demo_service):")
    print(f"  Status: {health['status']}")
    print(f"  Errors: {health['errors']}")
    print(f"  Warnings: {health['warnings']}")
    print(f"  Critical: {health['critical_errors']}")


def demo_error_spike_alerts():
    """Demo 3: Alert generation for error spikes."""
    print("\n" + "="*70)
    print("DEMO 3: Error Spike Detection and Alerts")
    print("="*70)
    
    setup_logger(app_name="demo_app", log_level="WARNING")
    logger = get_logger("demo")
    
    # Create error tracker with lower thresholds for demo
    tracker = ErrorTracker(
        logger=logger,
        alert_thresholds={
            "error_spike_count": 3,
            "error_spike_window_seconds": 60,
            "repeated_error_count": 2,
            "repeated_error_window_seconds": 60,
        }
    )
    
    print("\nGenerating repeated errors to trigger alerts:")
    
    # Generate multiple errors rapidly
    for i in range(5):
        tracker.track_error(
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            message="Database connection failed",
            error_code="DB_CONNECTION_FAILED",
            component="demo_service",
            context={"attempt": i + 1},
        )
        print(f"  ✓ Error {i+1}/5 tracked")
    
    # Display alerts
    print(f"\nAlerts Generated: {len(tracker.alerts)}")
    for alert in tracker.alerts:
        print(f"\n  Alert Type: {alert.alert_type.value}")
        print(f"  Severity: {alert.severity.value}")
        print(f"  Message: {alert.message}")
        print(f"  Related Errors: {len(alert.related_errors)}")


def demo_performance_monitoring():
    """Demo 4: Performance monitoring."""
    print("\n" + "="*70)
    print("DEMO 4: Performance Monitoring")
    print("="*70)
    
    setup_logger(app_name="demo_app", log_level="DEBUG")
    logger = get_logger("demo")
    
    monitor = PerformanceMonitor(logger=logger)
    
    # Simulate various operations
    print("\nSimulating operations:")
    
    # Database query
    import time
    with monitor.track_operation("database_query", component="demo_service"):
        time.sleep(0.05)  # Simulate 50ms query
    print("  ✓ Database query (50ms)")
    
    # API request
    with monitor.track_operation("api_request", component="demo_service"):
        time.sleep(0.03)  # Simulate 30ms request
    print("  ✓ API request (30ms)")
    
    # Data processing
    with monitor.track_operation("data_processing", component="demo_service"):
        time.sleep(0.02)  # Simulate 20ms processing
    print("  ✓ Data processing (20ms)")
    
    # Manual metric recording
    monitor.record_metric("inference_time_ms", 45.2, component="edge_device")
    monitor.record_metric("inference_time_ms", 42.8, component="edge_device")
    monitor.record_metric("inference_time_ms", 48.5, component="edge_device")
    print("  ✓ Edge device inference times recorded")
    
    # Display statistics
    print("\nPerformance Statistics:")
    
    stats = monitor.get_operation_stats()
    for op_name, op_stats in stats.items():
        print(f"\n  {op_name}:")
        print(f"    Count: {op_stats['count']}")
        print(f"    Avg: {op_stats['avg_time_ms']:.2f}ms")
        print(f"    Min: {op_stats['min_time_ms']:.2f}ms")
        print(f"    Max: {op_stats['max_time_ms']:.2f}ms")
    
    # Metric statistics
    print("\n  inference_time_ms:")
    inference_stats = monitor.get_metric_stats("inference_time_ms")
    print(f"    Mean: {inference_stats['mean']:.2f}ms")
    print(f"    P95: {inference_stats['p95']:.2f}ms")
    print(f"    P99: {inference_stats['p99']:.2f}ms")
    
    # SLA check
    print("\nSLA Compliance:")
    sla = monitor.check_sla(
        "database_query",
        max_latency_ms=100,
        min_success_rate=0.99,
    )
    print(f"  {sla['operation']}: {sla['sla_status'].upper()}")
    if sla['sla_status'] == 'met':
        print(f"    ✓ All operations within SLA")
    else:
        print(f"    ✗ SLA violation detected")


def demo_component_health():
    """Demo 5: Component health monitoring."""
    print("\n" + "="*70)
    print("DEMO 5: Component Health Monitoring")
    print("="*70)
    
    setup_logger(app_name="demo_app", log_level="INFO")
    logger = get_logger("demo")
    
    tracker = ErrorTracker(logger=logger)
    
    # Simulate errors for different components
    components_data = [
        ("api_server", ErrorSeverity.WARNING, 2, 0),
        ("mqtt_service", ErrorSeverity.ERROR, 5, 1),
        ("database", ErrorSeverity.CRITICAL, 0, 1),
        ("edge_device", ErrorSeverity.WARNING, 3, 0),
    ]
    
    print("\nGenerating component errors:")
    for component, severity, warnings, critical in components_data:
        for _ in range(warnings):
            tracker.track_error(
                category=ErrorCategory.RESOURCE,
                severity=ErrorSeverity.WARNING,
                message=f"Warning in {component}",
                component=component,
            )
        for _ in range(critical):
            tracker.track_error(
                category=ErrorCategory.DATABASE,
                severity=ErrorSeverity.CRITICAL,
                message=f"Critical error in {component}",
                component=component,
            )
    
    # Display health status
    print("\nComponent Health Status:")
    for component, _, _, _ in components_data:
        health = tracker.get_component_health(component)
        status_symbol = "🟢" if health["status"] == "healthy" else \
                       "🟡" if health["status"] in ["warning", "unhealthy"] else \
                       "🔴"
        
        print(f"\n  {status_symbol} {component.upper()}")
        print(f"    Status: {health['status']}")
        print(f"    Errors: {health['errors']}")
        print(f"    Warnings: {health['warnings']}")
        print(f"    Critical: {health['critical_errors']}")


def demo_log_export():
    """Demo 6: Export log data."""
    print("\n" + "="*70)
    print("DEMO 6: Log Data Export")
    print("="*70)
    
    setup_logger(app_name="demo_app", log_level="INFO")
    logger = get_logger("demo")
    
    tracker = ErrorTracker(logger=logger)
    
    # Create sample data
    for i in range(5):
        tracker.track_error(
            category=ErrorCategory.API,
            severity=ErrorSeverity.ERROR,
            message=f"Sample error {i+1}",
            error_code="SAMPLE_ERROR",
            component="demo_service",
        )
    
    # Export recent errors
    print("\nRecent Errors (JSON export):")
    recent = tracker.get_recent_errors(limit=3)
    print(json.dumps(recent, indent=2))
    
    print("\nError Statistics:")
    stats = tracker.get_error_stats(minutes=60)
    print(json.dumps(stats, indent=2, default=str))
    
    print("\nActive Alerts:")
    alerts = tracker.get_active_alerts()
    print(f"Total active alerts: {len(alerts)}")
    if alerts:
        print(json.dumps(alerts, indent=2, default=str))


async def main():
    """Run all demos."""
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  ERROR TRACKING & LOGGING SYSTEM - COMPREHENSIVE DEMO".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    # Run demos
    demo_structured_logging()
    demo_error_tracking()
    demo_error_spike_alerts()
    demo_performance_monitoring()
    demo_component_health()
    demo_log_export()
    
    print("\n" + "="*70)
    print("✓ All demos completed successfully!")
    print("="*70)
    print("\nNext steps:")
    print("  1. Check logs/ directory for generated JSON logs")
    print("  2. Review README_LOGGING_SYSTEM.md for integration guide")
    print("  3. See integration_example.py for component-specific setup")
    print("  4. Run database_schema.sql to create database tables")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
