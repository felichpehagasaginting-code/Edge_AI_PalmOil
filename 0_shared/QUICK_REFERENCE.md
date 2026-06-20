# Error Tracking & Logging System - Quick Reference

## 🚀 30-Second Setup

```bash
# 1. Create database schema
psql -U tbs_user -d grading_db -f 0_shared/database_schema.sql

# 2. Test the system
cd 0_shared && python demo_system.py

# 3. View generated logs
cat logs/demo_app.log
```

## 📝 Core Components at a Glance

| Component | Purpose | Import |
|-----------|---------|--------|
| **logger_config.py** | Structured JSON logging | `from logger_config import setup_logger, get_logger` |
| **error_tracker.py** | Error tracking & alerts | `from error_tracker import ErrorTracker, ErrorCategory` |
| **performance_monitor.py** | Performance metrics | `from performance_monitor import PerformanceMonitor` |
| **db_logging.py** | Database persistence | `from db_logging import DatabaseLogger` |

## 🔧 Usage Patterns

### Pattern 1: Setup (Startup)
```python
# In your app's startup code
from logger_config import setup_logger, get_logger
from error_tracker import ErrorTracker
from performance_monitor import PerformanceMonitor

setup_logger(app_name="my_service", log_level="INFO")
logger = get_logger(__name__)
tracker = ErrorTracker(logger=logger)
monitor = PerformanceMonitor(logger=logger)
```

### Pattern 2: Track Operations
```python
# In any async function
with monitor.track_operation("operation_name", component="my_component"):
    try:
        result = await do_something()
    except Exception as e:
        tracker.track_error(
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            message=str(e),
            component="my_component",
        )
        raise
```

### Pattern 3: Structured Logging
```python
logger.info_structured(
    "User action completed",
    user_id=123,
    action="login",
    duration_ms=45.2,
)

logger.error_structured(
    "Failed to process data",
    error_code="PROC_001",
    component="processor",
    retries=3,
)
```

### Pattern 4: Query Status
```python
# Get error statistics
stats = tracker.get_error_stats(minutes=60)

# Get component health
health = tracker.get_component_health("api_server")

# Get performance metrics
perf = monitor.get_metric_stats("database_query_duration_ms")

# Check SLA compliance
sla = monitor.check_sla("api_endpoint", max_latency_ms=200)
```

## 📊 Error Categories

```python
ErrorCategory.DATABASE         # Database errors
ErrorCategory.MQTT            # MQTT broker errors
ErrorCategory.DEVICE_COMM     # Device communication
ErrorCategory.DATA_PROCESSING # Data parsing/validation
ErrorCategory.API             # API errors
ErrorCategory.AUTHENTICATION  # Auth failures
ErrorCategory.RESOURCE        # Resource exhaustion
ErrorCategory.UNKNOWN         # Uncategorized
```

## ⚠️ Error Severity Levels

```python
ErrorSeverity.INFO            # Informational
ErrorSeverity.WARNING         # Non-critical issue
ErrorSeverity.ERROR           # Critical issue
ErrorSeverity.CRITICAL        # System-threatening
```

## 🎯 Automatic Alerts

The system automatically generates alerts for:

```
🔴 CRITICAL ERROR
   └─ Any critical-severity error

⚠️  ERROR SPIKE
   └─ 10+ same errors in 60 seconds

⚠️  REPEATED ERROR
   └─ Same error 5+ times in 5 minutes

⚠️  DEGRADATION
   └─ High error rate on component
```

## 📁 File Organization

```
0_shared/
├── Core Modules
│  ├── logger_config.py       # Structured logging setup
│  ├── error_tracker.py       # Error tracking & alerts
│  ├── performance_monitor.py # Performance metrics
│  └── db_logging.py          # Database persistence
│
├── Configuration
│  ├── logging_config.yaml    # System configuration
│  └── config_loader.py       # Config file loader
│
├── Database
│  └── database_schema.sql    # TimescaleDB schema
│
├── Documentation
│  ├── README_LOGGING_SYSTEM.md          # Full docs
│  ├── SYSTEM_IMPLEMENTATION_SUMMARY.md  # Overview
│  ├── integration_example.py            # Code examples
│  └── QUICK_REFERENCE.md               # This file
│
├── Testing
│  ├── demo_system.py         # Demo/test script
│  └── requirements.txt       # Python dependencies
│
└── Package Files
   ├── __init__.py            # Package initialization
   └── [generated logs/]      # Runtime logs (auto-created)
```

## 🔌 Integration Checklist

- [ ] Run `database_schema.sql` to create tables
- [ ] Import modules in your service
- [ ] Call `setup_logger()` at startup
- [ ] Initialize `ErrorTracker` and `PerformanceMonitor`
- [ ] Wrap operations with `track_operation()` context manager
- [ ] Use structured logging for important events
- [ ] Query monitoring endpoints for status
- [ ] Set up alerting handlers if needed
- [ ] Test with `demo_system.py`

## 📊 Database Queries

### Get Recent Errors
```sql
SELECT timestamp, component, severity, message 
FROM error_events 
WHERE timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC 
LIMIT 100;
```

### Error Statistics by Category
```sql
SELECT category, severity, COUNT(*) as count
FROM error_events 
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY category, severity
ORDER BY count DESC;
```

### Component Status
```sql
SELECT component, 
       COUNT(*) as error_count,
       COUNT(CASE WHEN severity='CRITICAL' THEN 1 END) as critical
FROM error_events
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY component;
```

### Performance Metrics
```sql
SELECT metric_name, 
       component,
       AVG(metric_value) as avg,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY metric_value) as p95
FROM performance_metrics
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY metric_name, component;
```

## 🎓 Learning Path

1. **Start**: Read `SYSTEM_IMPLEMENTATION_SUMMARY.md`
2. **Understand**: Review `integration_example.py` for patterns
3. **Test**: Run `demo_system.py` to see all features
4. **Reference**: Check `README_LOGGING_SYSTEM.md` for details
5. **Integrate**: Use patterns from `integration_example.py` in your code
6. **Monitor**: Query database tables for statistics

## ⚙️ Configuration Key Settings

```yaml
# Log level
logging.log_level: "INFO"  # DEBUG, INFO, WARNING, ERROR

# Error spike threshold
error_tracking.alerts.error_spike_count: 10
error_tracking.alerts.error_spike_window_seconds: 60

# Repeated error threshold
error_tracking.alerts.repeated_error_count: 5
error_tracking.alerts.repeated_error_window_seconds: 300

# SLA thresholds (milliseconds)
performance.sla.database_query_latency_ms: 100
performance.sla.api_response_latency_ms: 200
performance.sla.mqtt_message_latency_ms: 500

# Data retention (days)
error_tracking.retention.days: 30
performance.retention_hours: 24
```

## 💡 Pro Tips

1. **Use structured logging** for better searchability
2. **Catch errors at boundaries** (API, MQTT, Database)
3. **Track metrics for operations** you care about
4. **Set appropriate SLA thresholds** for your use case
5. **Query alerts regularly** to stay informed
6. **Use component names consistently** across service
7. **Archive old logs** periodically to manage storage
8. **Monitor database size** to ensure it doesn't grow unbounded

## 🆘 Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| "Logs not saving to DB" | Check database connection pool in config |
| "Too many alerts" | Increase error spike/repeated thresholds |
| "Memory usage high" | Lower retention_hours in performance monitor |
| "Slow database queries" | Add indexes (already included in schema) |
| "Can't find logs" | Check logs/ directory and log_level setting |

## 📞 Support Resources

- Full Documentation: `README_LOGGING_SYSTEM.md`
- Integration Examples: `integration_example.py`
- System Overview: `SYSTEM_IMPLEMENTATION_SUMMARY.md`
- Database Schema: `database_schema.sql`
- Demo Script: `demo_system.py`
- Configuration: `logging_config.yaml`

---

**System Status**: ✅ Implementation Complete
**Version**: 1.0.0
**Last Updated**: 2024
**Ready for Integration**: Yes
