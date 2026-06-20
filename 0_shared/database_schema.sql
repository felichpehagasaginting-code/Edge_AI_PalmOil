"""
FILE: 0_shared/database_schema.sql
PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Logging Database Schema
DESCRIPTION:
  Database schema for storing error events, logs, and alerts.
  This schema extends the existing TimescaleDB setup with new hypertables
  for efficient time-series logging.

DEPLOYMENT:
  psql -U tbs_user -d grading_db -f database_schema.sql
"""

-- Error Events Hypertable
-- Stores all error events from the system
CREATE TABLE IF NOT EXISTS error_events (
    id BIGSERIAL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    error_code TEXT,
    component TEXT NOT NULL DEFAULT 'unknown',
    context JSONB,
    traceback TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by TEXT,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Convert to hypertable if not already
SELECT create_hypertable('error_events', 'timestamp', if_not_exists => TRUE);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_error_events_category_timestamp 
    ON error_events (category, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_error_events_severity_timestamp 
    ON error_events (severity, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_error_events_component_timestamp 
    ON error_events (component, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_error_events_error_code_timestamp 
    ON error_events (error_code, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_error_events_resolved 
    ON error_events (resolved, timestamp DESC);


-- Application Logs Hypertable
-- Stores application logs with structured data
CREATE TABLE IF NOT EXISTS application_logs (
    id BIGSERIAL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    app_name TEXT NOT NULL,
    logger_name TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    component TEXT,
    module TEXT,
    function_name TEXT,
    line_number INT,
    extra_data JSONB,
    duration_ms FLOAT,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Convert to hypertable if not already
SELECT create_hypertable('application_logs', 'timestamp', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_app_logs_app_level_timestamp 
    ON application_logs (app_name, level, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_app_logs_component_timestamp 
    ON application_logs (component, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_app_logs_logger_timestamp 
    ON application_logs (logger_name, timestamp DESC);


-- Alerts Hypertable
-- Stores system alerts
CREATE TABLE IF NOT EXISTS system_alerts (
    id BIGSERIAL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    alert_type TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL,
    component TEXT,
    related_errors JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    acknowledged_by TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Convert to hypertable if not already
SELECT create_hypertable('system_alerts', 'timestamp', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_alerts_type_timestamp 
    ON system_alerts (alert_type, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_severity_timestamp 
    ON system_alerts (severity, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged 
    ON system_alerts (acknowledged, timestamp DESC);


-- Performance Metrics Hypertable
-- Stores performance metrics for operations
CREATE TABLE IF NOT EXISTS performance_metrics (
    id BIGSERIAL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metric_name TEXT NOT NULL,
    metric_value FLOAT NOT NULL,
    component TEXT NOT NULL,
    operation_name TEXT,
    unit TEXT,
    tags JSONB,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Convert to hypertable if not already
SELECT create_hypertable('performance_metrics', 'timestamp', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_perf_metrics_name_timestamp 
    ON performance_metrics (metric_name, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_perf_metrics_component_timestamp 
    ON performance_metrics (component, timestamp DESC);


-- Component Health History
-- Tracks component health status over time
CREATE TABLE IF NOT EXISTS component_health (
    id BIGSERIAL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    component TEXT NOT NULL,
    status TEXT NOT NULL,
    error_count INT,
    warning_count INT,
    critical_count INT,
    last_error_timestamp TIMESTAMP WITH TIME ZONE,
    metadata JSONB,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Convert to hypertable if not already
SELECT create_hypertable('component_health', 'timestamp', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_component_health_component_timestamp 
    ON component_health (component, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_component_health_status 
    ON component_health (status, timestamp DESC);


-- Error Statistics View
-- Aggregated error statistics
CREATE OR REPLACE VIEW error_statistics_hourly AS
SELECT
    DATE_TRUNC('hour', timestamp) as hour,
    category,
    severity,
    COUNT(*) as error_count,
    COUNT(DISTINCT component) as affected_components
FROM error_events
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY DATE_TRUNC('hour', timestamp), category, severity
ORDER BY hour DESC, error_count DESC;


-- System Health View
-- Current system health status
CREATE OR REPLACE VIEW system_health_status AS
SELECT
    component,
    (SELECT status FROM component_health 
     WHERE component = ch.component 
     ORDER BY timestamp DESC LIMIT 1) as current_status,
    (SELECT COUNT(*) FROM error_events 
     WHERE component = ch.component 
     AND timestamp > NOW() - INTERVAL '1 hour'
     AND resolved = FALSE) as unresolved_errors_last_hour,
    (SELECT timestamp FROM component_health 
     WHERE component = ch.component 
     ORDER BY timestamp DESC LIMIT 1) as last_check
FROM (SELECT DISTINCT component FROM component_health) ch
ORDER BY component;


-- Grant permissions (if using separate read-only user)
GRANT SELECT ON error_events TO tbs_user;
GRANT SELECT ON application_logs TO tbs_user;
GRANT SELECT ON system_alerts TO tbs_user;
GRANT SELECT ON performance_metrics TO tbs_user;
GRANT SELECT ON component_health TO tbs_user;
GRANT SELECT ON error_statistics_hourly TO tbs_user;
GRANT SELECT ON system_health_status TO tbs_user;
