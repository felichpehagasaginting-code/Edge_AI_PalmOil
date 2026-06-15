/**
 * @file    config.js
 * @brief   Dashboard configuration constants.
 *
 * Auto-detects hostname so the same build works on localhost (dev) and the
 * factory server (production) without changing anything.
 */

const CONFIG = Object.freeze({
  // ── REST API ─────────────────────────────────────────────────────────────
  // Proxied via Nginx to FastAPI backend at /api/*
  API_BASE: `${window.location.origin}/api`,

  // ── MQTT over WebSocket ───────────────────────────────────────────────────
  // Mosquitto listens on port 9001 for WebSocket clients.
  // Must be reachable from the browser (same host as the dashboard server).
  MQTT_WS_URL:  `ws://${window.location.hostname}:9001/mqtt`,
  MQTT_USERNAME: 'iot_gateway',
  MQTT_PASSWORD: 'secure_mqtt_pass',  // Match mosquitto/passwd

  // ── MQTT Topics ────────────────────────────────────────────────────────────
  MQTT_TOPIC_RESULT: 'pks/grading/tbs/result',
  MQTT_TOPIC_STATUS: 'pks/grading/tbs/status',

  // ── Polling ────────────────────────────────────────────────────────────────
  // How often (ms) to refresh historical data from the REST API
  HISTORICAL_REFRESH_MS: 5000,

  // ── Live Feed ─────────────────────────────────────────────────────────────
  FEED_MAX_ROWS:   50,      // Max rows in the live scan table
  THROUGHPUT_WINDOW_MINUTES: 30,
  GRADES_WINDOW_HOURS:       24,

  // ── Thresholds (must match firmware constants) ────────────────────────────
  MIN_CONFIDENCE_ANOMALY: 60,   // Below this → anomaly flag
  JANJANG_KOSONG_GRADE:    3,   // Grade 3 = empty bunch

  // ── Grade metadata ────────────────────────────────────────────────────────
  GRADES: [
    { id: 0, name: 'Mentah',         color: '#5e6272', colorSolid: '#7c8099' },
    { id: 1, name: 'Matang',         color: '#00ff9d', colorSolid: '#00cc7d' },
    { id: 2, name: 'Overripe',       color: '#ffa502', colorSolid: '#e6940b' },
    { id: 3, name: 'Janjang Kosong', color: '#ff4757', colorSolid: '#cc2233' },
  ],

  // ── Gateway staleness threshold ────────────────────────────────────────────
  GATEWAY_STALE_THRESHOLD_SEC: 90,
});
