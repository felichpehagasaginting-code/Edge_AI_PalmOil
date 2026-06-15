-- =============================================================================
-- FILE: timescaledb/init.sql
-- PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Server Backend
-- DESCRIPTION:
--   Database initialization script for the FFB grading traceability system.
--   Executed automatically on first TimescaleDB container startup via
--   the Docker entrypoint script (/docker-entrypoint-initdb.d/).
--
--   Creates:
--     1. grading_events  — Main hypertable for FFB scan results
--     2. gateway_status  — Gateway heartbeat/health tracking hypertable
--     3. Indexes          — Optimized for time-series queries by Grafana
--     4. Views            — Pre-built analytics views for Grafana dashboards
--
-- TIMESCALEDB HYPERTABLE:
--   A hypertable automatically partitions data into time-based "chunks"
--   for dramatically faster time-range queries vs standard PostgreSQL tables.
--   Default chunk interval: 7 days (suitable for continuous factory monitoring)
-- =============================================================================

-- Enable the TimescaleDB extension (must be first)
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- =============================================================================
-- TABLE 1: grading_events — FFB Scan Results
-- =============================================================================

CREATE TABLE IF NOT EXISTS grading_events (
    -- Primary time column (required for hypertable partitioning)
    -- Use timestamptz (with timezone) for correct time-series semantics.
    event_time      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    -- Sensor/device identification for multi-conveyor deployments
    -- sensor_id allows filtering events by conveyor line or location
    sensor_id       VARCHAR(64)         NOT NULL DEFAULT 'TBS_SCANNER_001',

    -- FFB Grading Result
    -- grade: 0=Mentah, 1=Matang, 2=Overripe, 3=Janjang Kosong
    grade           SMALLINT            NOT NULL CHECK (grade >= 0 AND grade <= 3),

    -- grade_name: Human-readable label for Grafana display (denormalized for speed)
    grade_name      VARCHAR(32)         NOT NULL,

    -- confidence_pct: Model confidence percentage [0..100]
    confidence_pct  SMALLINT            NOT NULL CHECK (confidence_pct >= 0 AND confidence_pct <= 100),

    -- is_anomaly: TRUE if grade==3 (Janjang Kosong) or confidence < threshold
    -- Pre-computed flag for fast anomaly filtering in Grafana alerts
    is_anomaly      BOOLEAN             NOT NULL DEFAULT FALSE,

    -- transport: Which channel delivered this event ('wifi_mqtt' or 'lora')
    -- Useful for network reliability analysis
    transport       VARCHAR(16)         NOT NULL DEFAULT 'wifi_mqtt',

    -- esp_uptime_ms: ESP-12E uptime at time of transmission (for drift analysis)
    esp_uptime_ms   BIGINT,

    -- scan_count: Total scan count from ESP-12E since last reboot (for gap detection)
    scan_count      BIGINT,

    -- raw_payload: Original JSON string from MAX78000 (for audit trail)
    raw_payload     TEXT
);

-- Convert to TimescaleDB hypertable
-- chunk_time_interval: 7 days — each "chunk" contains 7 days of data
-- This is appropriate for factory monitoring at ~60-600 scans/hour
SELECT create_hypertable(
    'grading_events',
    'event_time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

-- Enable automatic data compression for chunks older than 30 days
-- Compressed chunks use ~10x less disk space — critical for long-term storage
ALTER TABLE grading_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'sensor_id, grade',
    timescaledb.compress_orderby = 'event_time DESC'
);

-- Schedule automatic compression (chunks older than 30 days)
SELECT add_compression_policy('grading_events', INTERVAL '30 days', if_not_exists => TRUE);

-- =============================================================================
-- INDEXES for grading_events
-- =============================================================================

-- Index on sensor_id for multi-sensor deployments
CREATE INDEX IF NOT EXISTS idx_grading_sensor_time
    ON grading_events (sensor_id, event_time DESC);

-- Index for anomaly queries (filter only anomalies)
CREATE INDEX IF NOT EXISTS idx_grading_anomaly_time
    ON grading_events (is_anomaly, event_time DESC)
    WHERE is_anomaly = TRUE;

-- Index for grade-specific queries (e.g., "how many Matang today?")
CREATE INDEX IF NOT EXISTS idx_grading_grade_time
    ON grading_events (grade, event_time DESC);

-- =============================================================================
-- TABLE 2: gateway_status — ESP-12E Heartbeat / Health Tracking
-- =============================================================================

CREATE TABLE IF NOT EXISTS gateway_status (
    event_time      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    gateway_id      VARCHAR(64)     NOT NULL DEFAULT 'ESP_TBS_GW_001',
    status          VARCHAR(16)     NOT NULL,   -- 'online' or 'offline'
    ip_address      VARCHAR(45),                -- IPv4 or IPv6 address
    wifi_rssi_dbm   SMALLINT,                   -- Wi-Fi signal strength (dBm)
    lora_status     VARCHAR(8),                 -- 'ok' or 'fail'
    uptime_sec      BIGINT,                     -- Gateway uptime in seconds
    total_scans     BIGINT                      -- Total lifetime scan count
);

SELECT create_hypertable(
    'gateway_status',
    'event_time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists       => TRUE
);

ALTER TABLE gateway_status SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'gateway_id',
    timescaledb.compress_orderby = 'event_time DESC'
);

SELECT add_compression_policy('gateway_status', INTERVAL '7 days', if_not_exists => TRUE);

-- =============================================================================
-- ANALYTICS VIEWS (used by Grafana dashboards)
-- =============================================================================

-- View 1: Grade Distribution by Hour (for Grafana bar chart)
CREATE OR REPLACE VIEW v_grade_distribution_hourly AS
SELECT
    time_bucket('1 hour', event_time)   AS bucket,
    sensor_id,
    grade,
    grade_name,
    COUNT(*)                            AS count,
    AVG(confidence_pct)                 AS avg_confidence
FROM grading_events
GROUP BY bucket, sensor_id, grade, grade_name
ORDER BY bucket DESC;

-- View 2: Throughput Rate (bunches per minute, 5-min rolling window)
CREATE OR REPLACE VIEW v_throughput_5min AS
SELECT
    time_bucket('5 minutes', event_time) AS bucket,
    sensor_id,
    COUNT(*)                             AS bunches_per_5min,
    COUNT(*) / 5.0                       AS bunches_per_min
FROM grading_events
GROUP BY bucket, sensor_id
ORDER BY bucket DESC;

-- View 3: Anomaly Rate by Hour
CREATE OR REPLACE VIEW v_anomaly_rate_hourly AS
SELECT
    time_bucket('1 hour', event_time)   AS bucket,
    sensor_id,
    COUNT(*) FILTER (WHERE is_anomaly)  AS anomaly_count,
    COUNT(*)                            AS total_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE is_anomaly) / NULLIF(COUNT(*), 0),
        2
    )                                   AS anomaly_rate_pct
FROM grading_events
GROUP BY bucket, sensor_id
ORDER BY bucket DESC;

-- View 4: Recent events for live feed (last 100 events)
CREATE OR REPLACE VIEW v_recent_events AS
SELECT
    event_time,
    sensor_id,
    grade,
    grade_name,
    confidence_pct,
    is_anomaly,
    transport
FROM grading_events
ORDER BY event_time DESC
LIMIT 100;

-- View 5: Daily Grade Summary for production report
CREATE OR REPLACE VIEW v_daily_grade_summary AS
SELECT
    time_bucket('1 day', event_time)    AS day,
    sensor_id,
    SUM(CASE WHEN grade = 0 THEN 1 ELSE 0 END)  AS mentah_count,
    SUM(CASE WHEN grade = 1 THEN 1 ELSE 0 END)  AS matang_count,
    SUM(CASE WHEN grade = 2 THEN 1 ELSE 0 END)  AS overripe_count,
    SUM(CASE WHEN grade = 3 THEN 1 ELSE 0 END)  AS janjang_kosong_count,
    COUNT(*)                                      AS total_scanned,
    AVG(confidence_pct)                          AS avg_confidence,
    SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END)  AS total_anomalies
FROM grading_events
GROUP BY day, sensor_id
ORDER BY day DESC;

-- =============================================================================
-- DATA RETENTION POLICY (auto-delete old data)
-- =============================================================================

-- Keep raw scan data for 1 year (365 days), then auto-drop old chunks
-- This prevents unbounded disk growth in production
SELECT add_retention_policy(
    'grading_events',
    INTERVAL '365 days',
    if_not_exists => TRUE
);

-- Keep gateway status for 90 days
SELECT add_retention_policy(
    'gateway_status',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- =============================================================================
-- SAMPLE DATA (for testing — remove in production)
-- =============================================================================

-- Insert 10 sample grading events to verify schema and views work
INSERT INTO grading_events
    (event_time, sensor_id, grade, grade_name, confidence_pct, is_anomaly, transport)
VALUES
    (NOW() - INTERVAL '5 minutes',  'TBS_SCANNER_001', 1, 'Matang',         92, FALSE, 'wifi_mqtt'),
    (NOW() - INTERVAL '4 minutes',  'TBS_SCANNER_001', 1, 'Matang',         88, FALSE, 'wifi_mqtt'),
    (NOW() - INTERVAL '3 minutes',  'TBS_SCANNER_001', 0, 'Mentah',         78, FALSE, 'wifi_mqtt'),
    (NOW() - INTERVAL '2 minutes',  'TBS_SCANNER_001', 3, 'Janjang Kosong', 94, TRUE,  'wifi_mqtt'),
    (NOW() - INTERVAL '1 minute',   'TBS_SCANNER_001', 2, 'Overripe',       85, FALSE, 'wifi_mqtt'),
    (NOW() - INTERVAL '30 seconds', 'TBS_SCANNER_001', 1, 'Matang',         96, FALSE, 'wifi_mqtt'),
    (NOW(),                          'TBS_SCANNER_001', 1, 'Matang',         91, FALSE, 'wifi_mqtt');

-- Insert sample gateway status
INSERT INTO gateway_status
    (event_time, gateway_id, status, ip_address, wifi_rssi_dbm, lora_status, uptime_sec, total_scans)
VALUES
    (NOW(), 'ESP_TBS_GW_001', 'online', '192.168.1.101', -65, 'ok', 3600, 42);

-- =============================================================================
-- VERIFY SETUP
-- =============================================================================

\echo '--- TimescaleDB Schema Initialized Successfully ---'
\echo 'Tables created: grading_events, gateway_status'
\echo 'Hypertables created with 7-day chunks'
\echo 'Compression policies: 30 days (grading), 7 days (status)'
\echo 'Retention policies: 365 days (grading), 90 days (status)'
\echo 'Views: v_grade_distribution_hourly, v_throughput_5min, v_anomaly_rate_hourly, v_recent_events, v_daily_grade_summary'
\echo '----------------------------------------------------'
