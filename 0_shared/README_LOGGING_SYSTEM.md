"""
FILE: 0_shared/README_LOGGING_SYSTEM.md
PROJECT: Error Tracking and Logging System for IoT Grad Scanner

This document describes the comprehensive error tracking and logging
system implementation for the entire IoT ecosystem.

## System Architecture

The logging system consists of several integrated components:

### 1. **Core Modules**

#### logger_config.py
- Centralized structured logging configuration
- JSON formatted logs for better parsing
- Support for file and console handlers with rotation
- Extended logger class with structured logging methods

**Usage:**
```python
from logger_config import setup_logger, get_logger

# Setup at app startup
setup_logger(app_name="my_service", log_level="INFO")

# Get logger in any module
logger = get_logger(__name__)

# Use structured logging
logger.info_structured("User logged in", user_id=123, role="admin")
logger.error_structured("Database error", error_code="DB_001", component="api")
```

#### error_tracker.py
- Track and categorize errors
- Automatic alert generation for error spikes
- Error statistics and trending
- Component health monitoring

**Usage:**
```python
from error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity

tracker = ErrorTracker(logger=logger)

tracker.track_error(
    category=ErrorCategory.DATABASE,
    severity=ErrorSeverity.CRITICAL,
    message="Connection timeout",
    error_code="DB_TIMEOUT",
    component="api_server",
    context={"host": "db.example.com"},
)

# Get statistics
stats = tracker.get_error_stats(minutes=60)
component_health = tracker.get_component_health("api_server")
```

#### performance_monitor.py
- Track operation latencies
- Calculate throughput metrics
- SLA monitoring and compliance tracking
- Performance degradation alerts

**Usage:**
```python
from performance_monitor import PerformanceMonitor

monitor = PerformanceMonitor(logger=logger)

# Track operation
with monitor.track_operation("database_query", component="api"):
    result = db.query(...)

# Get metrics
stats = monitor.get_metric_stats("database_query_duration_ms")
throughput = monitor.get_throughput("database_query", minutes=60)

# Check SLA
sla_status = monitor.check_sla(
    "database_query",
    max_latency_ms=100,
    min_success_rate=0.99
)
```

#### db_logging.py
- Persist logs, errors, and metrics to TimescaleDB
- Query and aggregate log data
- Alert acknowledgment and management
- Automatic cleanup of old logs

**Usage:**
```python
from db_logging import DatabaseLogger

db_logger = DatabaseLogger(db_pool=pool)

# Log error event
await db_logger.log_error_event(error_event)

# Query recent errors
errors = await db_logger.get_recent_errors(hours=24, limit=100)

# Get statistics
stats = await db_logger.get_error_stats(hours=24)
```

### 2. **Database Schema**

The system uses TimescaleDB hypertables for efficient time-series storage:

- **error_events**: All error events from the system
- **application_logs**: Application logs with structured data
- **system_alerts**: System alerts and notifications
- **performance_metrics**: Operation metrics and latencies
- **component_health**: Component health status history

Run `database_schema.sql` to create all tables:
```bash
psql -U tbs_user -d grading_db -f database_schema.sql
```

### 3. **Error Categories**

```
DATABASE          - Database connection, query, transaction errors
MQTT              - MQTT broker, subscription, message errors
DEVICE_COMM       - Device communication protocol errors
DATA_PROCESSING   - Data parsing, validation, processing errors
API               - API endpoint, request, response errors
AUTHENTICATION    - Auth failures, permission issues
RESOURCE          - Memory, CPU, disk space issues
UNKNOWN           - Unclassified errors
```

### 4. **Error Severity Levels**

```
INFO      - Informational messages
WARNING   - Non-critical issues
ERROR     - Critical operational issues
CRITICAL  - System-threatening issues
```

## Integration Guide

### For API Server (5_web_dashboard/backend/api_server.py)

```python
from logger_config import setup_logger, get_logger
from error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity
from performance_monitor import PerformanceMonitor
from db_logging import DatabaseLogger

# In lifespan function
setup_logger(app_name="dashboard_api", log_level="INFO")
logger = get_logger("dashboard_api")
error_tracker = ErrorTracker(logger=logger)
perf_monitor = PerformanceMonitor(logger=logger)
db_logger = DatabaseLogger(pool, logger=logger)

# In API endpoints
with perf_monitor.track_operation("endpoint_name", component="api"):
    try:
        # Your code here
        pass
    except Exception as e:
        error_tracker.track_error(
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            message=str(e),
            component="api_server",
        )
```

### For MQTT Service (4_server_backend/mqtt_to_db/mqtt_to_db.py)

```python
from logger_config import setup_logger, get_logger
from error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity
from performance_monitor import PerformanceMonitor

setup_logger(app_name="mqtt_to_db", log_level="INFO")
logger = get_logger("mqtt_to_db")
error_tracker = ErrorTracker(logger=logger)
perf_monitor = PerformanceMonitor(logger=logger)

# In MQTT callbacks
def on_message(client, userdata, msg):
    with perf_monitor.track_operation("mqtt_message", component="mqtt_to_db"):
        try:
            # Process message
            pass
        except Exception as e:
            error_tracker.track_error(
                category=ErrorCategory.MQTT,
                severity=ErrorSeverity.ERROR,
                message=str(e),
                component="mqtt_to_db",
            )
```

### For Other Components

Similar patterns can be applied to:
- Edge device firmware (ESP-12E, MAX78000)
- Background task services
- Scheduled maintenance tasks

## Configuration

Configuration is in `logging_config.yaml`:

```yaml
logging:
  enabled: true
  log_level: "INFO"
  file:
    enabled: true
    directory: "logs"
    max_size_mb: 10

error_tracking:
  enabled: true
  alerts:
    error_spike_count: 10
    error_spike_window_seconds: 60

performance:
  enabled: true
  sla:
    database_query_latency_ms: 100
    api_response_latency_ms: 200
```

## API Endpoints for Monitoring

New endpoints available in dashboard API:

```
GET /api/errors/recent?hours=24&limit=50
  - Get recent errors

GET /api/errors/stats?hours=24
  - Get error statistics

GET /api/system/health
  - Get overall system health

GET /api/alerts/active
  - Get active alerts

POST /api/alerts/{id}/acknowledge
  - Acknowledge an alert

GET /api/performance/stats
  - Get performance metrics

GET /api/components/{name}/status
  - Get component status
```

## Alert Triggers

The system automatically generates alerts for:

1. **Critical Errors**: Any critical-severity error
2. **Error Spikes**: 10+ errors of the same type within 60 seconds
3. **Repeated Errors**: Same error 5+ times within 5 minutes
4. **Component Degradation**: High error rates on specific components
5. **SLA Violations**: Operations exceeding latency thresholds

## Log Retention

Default retention policies:

- Error events: 30 days
- Application logs: 14 days
- Performance metrics: 7 days
- Component health: 30 days

Automatic cleanup runs every 6 hours.

## Performance Considerations

1. **Log Volume**: Average 1000-5000 logs/day
2. **Storage**: ~500MB/month for full logging (varies by verbosity)
3. **Query Performance**: Indexed queries return results in <100ms
4. **Alert Latency**: Alerts generated within 1-2 seconds of error

## Troubleshooting

### Logs not appearing in database
- Check database connection pool configuration
- Verify database user has INSERT permissions
- Check database_schema.sql was executed successfully

### High memory usage
- Reduce log_retention in performance_monitor
- Lower alert_thresholds to generate fewer in-memory events
- Increase cleanup frequency

### Missing alerts
- Check alerting.enabled is true in config
- Verify alert thresholds match your expectations
- Check alert_callback is properly configured

## Future Enhancements

Planned improvements:
1. Elasticsearch integration for distributed logging
2. Grafana dashboards for visualization
3. Email/SMS alerting
4. Machine learning for anomaly detection
5. Distributed tracing support
6. Custom metrics from user applications

## Support

For issues or questions:
1. Check logs in `logs/` directory
2. Query application_logs table for historical data
3. Review error_events table for systematic issues
"""
