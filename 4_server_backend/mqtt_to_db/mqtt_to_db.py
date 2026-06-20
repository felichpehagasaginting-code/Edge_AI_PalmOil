#!/usr/bin/env python3
"""
FILE: mqtt_to_db/mqtt_to_db.py
PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Server Backend
DESCRIPTION:
  Lightweight, robust Python daemon that:
    1. Subscribes to MQTT topic: pks/grading/tbs/result
    2. Parses each incoming JSON payload from the ESP-12E gateway
    3. Inserts a row into the TimescaleDB grading_events hypertable
    4. Subscribes to pks/grading/tbs/status for gateway heartbeat logging

  Runs as a Docker container service with automatic restart on failure.
  Handles MQTT reconnection, database connection pooling, and
  structured logging for production observability.

ENVIRONMENT VARIABLES (set in docker-compose.yml):
  MQTT_BROKER_HOST  — Mosquitto hostname (default: mosquitto)
  MQTT_BROKER_PORT  — Mosquitto port (default: 1883)
  MQTT_USERNAME     — MQTT auth username
  MQTT_PASSWORD     — MQTT auth password
  MQTT_TOPIC        — Topic to subscribe (default: pks/grading/tbs/result)
  DB_HOST           — TimescaleDB hostname (default: timescaledb)
  DB_PORT           — Database port (default: 5432)
  DB_NAME           — Database name (default: grading_db)
  DB_USER           — Database user (default: tbs_user)
  DB_PASSWORD       — Database password
  LOG_LEVEL         — Logging level (DEBUG/INFO/WARNING, default: INFO)
  CONFIDENCE_ANOMALY_THRESHOLD — Min confidence % to flag anomaly
                                 (default: 60)

TOPIC PROTOCOL:
  pks/grading/tbs/result  ← {"g":<grade>,"c":<confidence>,
                             "ts":<ms>,"cnt":<n>}
  pks/grading/tbs/status  ← {"status":"online","uptime":<ms>,
                             "ip":"...","rssi":<dBm>}
"""

import os
import sys
import json
import time
import signal
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Third-party dependencies (see requirements.txt)
import paho.mqtt.client as mqtt
import psycopg2
import psycopg2.pool
import psycopg2.extras

###############################################################################
# Logging Setup
###############################################################################

LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s [%(levelname)-8s] %(name)-20s %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("mqtt_to_db")

###############################################################################
# Configuration (from environment variables)
###############################################################################


class Config:
    """
    All configuration is read from environment variables, consistent with
    12-factor app principles for container deployments.
    """

    # ── MQTT ─────────────────────────────────────────────────────────────────
    MQTT_BROKER_HOST: str = os.getenv("MQTT_BROKER_HOST", "mosquitto")
    MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    MQTT_USERNAME: str = os.getenv("MQTT_USERNAME", "iot_gateway")
    MQTT_PASSWORD: str = os.getenv("MQTT_PASSWORD", "secure_mqtt_pass")
    MQTT_CLIENT_ID: str = "mqtt_to_db_daemon_001"
    MQTT_KEEPALIVE: int = 60          # seconds
    MQTT_QOS: int = 1           # Subscribe at QoS 1 for at-least-once

    # Topics to subscribe
    MQTT_TOPIC_RESULT: str = os.getenv(
        "MQTT_TOPIC", "pks/grading/tbs/result"
    )
    MQTT_TOPIC_STATUS: str = "pks/grading/tbs/status"

    # ── Database ─────────────────────────────────────────────────────────────
    DB_HOST: str = os.getenv("DB_HOST", "timescaledb")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "grading_db")
    DB_USER: str = os.getenv("DB_USER", "tbs_user")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "secure_db_pass_123")

    # Connection pool: min 1, max 5 connections
    DB_POOL_MIN: int = 1
    DB_POOL_MAX: int = 5

    # ── Business Logic ───────────────────────────────────────────────────────
    # Grade index for "Janjang Kosong" (empty bunch) — triggers anomaly flag
    JANJANG_KOSONG_GRADE: int = 3

    # Minimum confidence % threshold — below this flags anomaly
    CONFIDENCE_ANOMALY_THRESHOLD: int = int(
        os.getenv("CONFIDENCE_ANOMALY_THRESHOLD", "60")
    )

    # Device ID prefix for sensor_id field in database
    SENSOR_ID: str = "TBS_SCANNER_001"

    # ── Reconnection Policy ──────────────────────────────────────────────────
    MQTT_RECONNECT_DELAY_MIN: float = 1.0    # Start with 1s
    MQTT_RECONNECT_DELAY_MAX: float = 60.0   # Cap at 60s (exponential backoff)
    DB_RECONNECT_DELAY: float = 5.0    # 5s between DB reconnect attempts

    # ── Grade Name Lookup ────────────────────────────────────────────────────
    GRADE_NAMES: Dict[int, str] = {
        0: "Mentah",
        1: "Matang",
        2: "Overripe",
        3: "Janjang Kosong"
    }

    @classmethod
    def grade_to_name(cls, grade: int) -> str:
        """Return human-readable grade name, or 'Unknown' for invalid index."""
        return cls.GRADE_NAMES.get(grade, f"Unknown({grade})")

    @classmethod
    def is_anomaly(cls, grade: int, confidence_pct: int) -> bool:
        """
        Determine if a scan result should be flagged as an anomaly.
        Anomaly conditions:
          1. Grade is Janjang Kosong (empty bunch)
          2. Confidence is below the defined threshold (model uncertainty)
        """
        return (grade == cls.JANJANG_KOSONG_GRADE or
                confidence_pct < cls.CONFIDENCE_ANOMALY_THRESHOLD)


###############################################################################
# Database Connection Pool
###############################################################################

class DatabaseManager:
    """
    Manages a psycopg2 ThreadedConnectionPool to TimescaleDB.
    Thread-safe: MQTT callbacks run in the paho-mqtt network loop thread,
    while the main thread may also perform DB health checks.
    """

    def __init__(self):
        self._pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
        self._lock = threading.Lock()

    def connect(self) -> bool:
        """
        Initialize the connection pool. Retries with delay on failure.
        Returns True on success, False on failure.
        """
        dsn = (
            f"host={Config.DB_HOST} "
            f"port={Config.DB_PORT} "
            f"dbname={Config.DB_NAME} "
            f"user={Config.DB_USER} "
            f"password={Config.DB_PASSWORD} "
            f"connect_timeout=10 "
            f"application_name=mqtt_to_db"
        )

        try:
            with self._lock:
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=Config.DB_POOL_MIN,
                    maxconn=Config.DB_POOL_MAX,
                    dsn=dsn
                )
            logger.info(
                "Database pool established: %s:%s/%s (pool: %s-%s)",
                Config.DB_HOST, Config.DB_PORT, Config.DB_NAME,
                Config.DB_POOL_MIN, Config.DB_POOL_MAX
            )
            return True

        except psycopg2.Error as e:
            logger.error("Database connection failed: %s", e)
            return False

    def is_connected(self) -> bool:
        """Returns True if the pool is initialized and has available
        connections.
        """
        return self._pool is not None

    def get_connection(self):
        """
        Acquire a connection from the pool.
        Raises psycopg2.pool.PoolError if no connections available.
        """
        if not self._pool:
            raise psycopg2.DatabaseError("Database pool not initialized.")
        return self._pool.getconn()

    def return_connection(self, conn, failed: bool = False):
        """Return a connection to the pool. Mark as failed if it had
        an error.
        """
        if self._pool and conn:
            self._pool.putconn(conn, close=failed)

    def close(self):
        """Close all connections in the pool."""
        with self._lock:
            if self._pool:
                self._pool.closeall()
                self._pool = None
                logger.info("Database connection pool closed.")

    def insert_grading_event(
        self,
        grade: int,
        confidence_pct: int,
        is_anomaly: bool,
        transport: str = "wifi_mqtt",
        esp_uptime_ms: Optional[int] = None,
        scan_count: Optional[int] = None,
        raw_payload: Optional[str] = None
    ) -> bool:
        """
        Insert a single FFB grading event into the grading_events hypertable.

        Args:
            grade:          CNN predicted class index [0..3]
            confidence_pct: Model confidence percentage [0..100]
            is_anomaly:     True if Janjang Kosong or low confidence
            transport:      'wifi_mqtt' or 'lora'
            esp_uptime_ms:  ESP-12E uptime in ms at scan time
            scan_count:     Total scan count from ESP-12E
            raw_payload:    Original JSON string for audit trail

        Returns:
            True on success, False on database error.
        """
        grade_name = Config.grade_to_name(grade)
        event_time = datetime.now(timezone.utc)

        sql = """
            INSERT INTO grading_events
                (event_time, sensor_id, grade, grade_name, confidence_pct,
                 is_anomaly, transport, esp_uptime_ms, scan_count, raw_payload)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql, (
                    event_time,
                    Config.SENSOR_ID,
                    grade,
                    grade_name,
                    confidence_pct,
                    is_anomaly,
                    transport,
                    esp_uptime_ms,
                    scan_count,
                    raw_payload
                ))
            conn.commit()

            logger.info(
                "DB INSERT: grade=%s (%s), confidence=%s%%, "
                "anomaly=%s, transport=%s",
                grade, grade_name, confidence_pct, is_anomaly, transport
            )
            return True

        except psycopg2.Error as e:
            logger.error("DB INSERT failed: %s", e)
            if conn:
                try:
                    conn.rollback()
                except Exception:  # pylint: disable=broad-except
                    pass
            self.return_connection(conn, failed=True)
            conn = None  # Prevent double-return in finally
            return False

        finally:
            if conn:
                self.return_connection(conn, failed=False)

    def insert_gateway_status(
        self,
        status: str,
        ip_address: Optional[str],
        wifi_rssi_dbm: Optional[int],
        lora_status: Optional[str],
        uptime_sec: Optional[int],
        total_scans: Optional[int],
        gateway_id: str = "ESP_TBS_GW_001"
    ) -> bool:
        """
        Insert a gateway heartbeat/status record into the
        gateway_status hypertable.
        """
        event_time = datetime.now(timezone.utc)

        sql = """
            INSERT INTO gateway_status
                (event_time, gateway_id, status, ip_address, wifi_rssi_dbm,
                 lora_status, uptime_sec, total_scans)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql, (
                    event_time, gateway_id, status, ip_address,
                    wifi_rssi_dbm, lora_status, uptime_sec, total_scans
                ))
            conn.commit()
            logger.debug("Gateway status logged: %s (%s)", status, gateway_id)
            return True

        except psycopg2.Error as e:
            logger.error("Gateway status INSERT failed: %s", e)
            if conn:
                try:
                    conn.rollback()
                except Exception:  # pylint: disable=broad-except
                    pass
            self.return_connection(conn, failed=True)
            conn = None
            return False

        finally:
            if conn:
                self.return_connection(conn)


###############################################################################
# MQTT→DB Bridge Daemon
###############################################################################

class MqttToDbDaemon:
    """
    Main daemon class. Manages MQTT subscription and database insertion.

    The paho-mqtt library is single-threaded by default for callbacks.
    We use loop_start() to run the MQTT network loop in a background thread,
    so callbacks can block slightly on DB operations without dropping messages.
    """

    def __init__(self):
        self.db = DatabaseManager()
        self.mqtt_client: Optional[mqtt.Client] = None
        self._running = False
        self._reconnect_delay = Config.MQTT_RECONNECT_DELAY_MIN
        self._stats = {
            "messages_received":  0,
            "inserts_successful": 0,
            "inserts_failed":     0,
            "parse_errors":       0,
            "started_at":         datetime.now(timezone.utc).isoformat()
        }

    def _on_connect(self, _client, _userdata, _flags, rc):
        """MQTT connection callback.

        Called when the client connects to the broker.
        rc: 0=Connected, non-zero=Error (see paho-mqtt rc codes).
        """
        if rc == 0:
            logger.info(
                "MQTT connected to %s:%s",
                Config.MQTT_BROKER_HOST, Config.MQTT_BROKER_PORT
            )
            self._reconnect_delay = Config.MQTT_RECONNECT_DELAY_MIN

            # Subscribe to result topic (QoS 1: at-least-once delivery)
            _client.subscribe(Config.MQTT_TOPIC_RESULT, qos=Config.MQTT_QOS)
            logger.info(
                "Subscribed to: %s (QoS %s)",
                Config.MQTT_TOPIC_RESULT,
                Config.MQTT_QOS
            )

            # Subscribe to status topic (QoS 0: best effort for heartbeats)
            _client.subscribe(Config.MQTT_TOPIC_STATUS, qos=0)
            logger.info("Subscribed to: %s (QoS 0)", Config.MQTT_TOPIC_STATUS)

        else:
            rc_messages = {
                1: "Unacceptable protocol version",
                2: "Identifier rejected",
                3: "Server unavailable",
                4: "Bad username or password",
                5: "Not authorized"
            }
            logger.error(
                "MQTT connection refused: %s",
                rc_messages.get(rc, f"Unknown error {rc}")
            )

    def _on_disconnect(self, _client, _userdata, rc):
        """
        MQTT disconnection callback. paho-mqtt will automatically attempt
        reconnection (reconnect_delay_set was called in start()).
        """
        if rc == 0:
            logger.info("MQTT disconnected gracefully.")
        else:
            logger.warning(
                "MQTT unexpected disconnect (rc=%s). "
                "Auto-reconnecting in %.1fs...",
                rc, self._reconnect_delay
            )
            # Exponential backoff for reconnect delay
            self._reconnect_delay = min(
                self._reconnect_delay * 2,
                Config.MQTT_RECONNECT_DELAY_MAX
            )

    def _on_message(self, _client, _userdata, msg: mqtt.MQTTMessage):
        """MQTT message callback.

        Called for every received message on subscribed topics.
        Runs in the paho-mqtt network loop thread.
        """
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace").strip()

        logger.debug("MQTT message: topic=%s, payload=%s", topic, payload)
        self._stats["messages_received"] += 1

        # ── Dispatch by topic ────────────────────────────────────────────────
        if topic == Config.MQTT_TOPIC_RESULT:
            self._handle_grading_result(payload)

        elif topic == Config.MQTT_TOPIC_STATUS:
            self._handle_gateway_status(payload)

        else:
            logger.warning("Received message on unexpected topic: %s", topic)

    def _handle_grading_result(self, payload: str) -> None:
        """
        Parse and persist a grading result payload.

        Expected JSON format:
            {"g":<grade>,"c":<confidence>,"ts":<esp_uptime_ms>,
             "cnt":<scan_count>}
        """
        # ── Parse JSON ───────────────────────────────────────────────────────
        try:
            data: Dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.error("JSON parse error: %s | payload='%s'", e, payload)
            self._stats["parse_errors"] += 1
            return

        # ── Validate required fields ───────────────────────────────────────
        grade = data.get("g")
        confidence = data.get("c")

        if grade is None or confidence is None:
            logger.error("Missing required fields in payload: %s", payload)
            self._stats["parse_errors"] += 1
            return

        # Type validation and bounds checking
        try:
            grade = int(grade)
            confidence = int(confidence)
        except (ValueError, TypeError) as e:
            logger.error(
                "Field type conversion error: %s | payload='%s'",
                e, payload
            )
            self._stats["parse_errors"] += 1
            return

        if not 0 <= grade <= 3:
            logger.error(
                "Invalid grade value: %s (expected 0-3) | payload='%s'",
                grade, payload
            )
            self._stats["parse_errors"] += 1
            return

        if not 0 <= confidence <= 100:
            logger.error("Invalid confidence: %s (expected 0-100)", confidence)
            self._stats["parse_errors"] += 1
            return

        # ── Extract optional fields ────────────────────────────────────────
        esp_uptime_ms: Optional[int] = data.get("ts")
        scan_count: Optional[int] = data.get("cnt")

        # Determine anomaly flag
        anomaly = Config.is_anomaly(grade, confidence)

        if anomaly:
            logger.warning(
                "ANOMALY DETECTED: grade=%s (%s), confidence=%s%%",
                grade, Config.grade_to_name(grade), confidence
            )

        # ── Database insertion ─────────────────────────────────────────────
        if not self.db.is_connected():
            logger.error(
                "Database not connected — attempting reconnect before insert."
            )
            self._reconnect_database()

        success = self.db.insert_grading_event(
            grade=grade,
            confidence_pct=confidence,
            is_anomaly=anomaly,
            transport="wifi_mqtt",
            esp_uptime_ms=esp_uptime_ms,
            scan_count=scan_count,
            raw_payload=payload
        )

        if success:
            self._stats["inserts_successful"] += 1
        else:
            self._stats["inserts_failed"] += 1
            logger.error(
                "DB insertion failed for payload: %s — total failures: %s",
                payload, self._stats['inserts_failed']
            )

    def _handle_gateway_status(self, payload: str) -> None:
        """Parse and log a gateway heartbeat/status message to the DB."""
        try:
            data: Dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError as e:
            logger.warning("Gateway status JSON parse error: %s", e)
            return

        status = data.get("status", "unknown")
        ip_address = data.get("ip")
        wifi_rssi_dbm = data.get("rssi")
        lora_status = data.get("lora", "unknown")
        total_scans = data.get("scans")

        # Convert uptime from ms to seconds for the DB field
        uptime_ms = data.get("uptime")
        uptime_sec = int(uptime_ms / 1000) if uptime_ms is not None else None

        logger.info(
            "Gateway status: %s, IP=%s, RSSI=%s dBm, "
            "LoRa=%s, uptime=%ss, scans=%s",
            status, ip_address, wifi_rssi_dbm, lora_status,
            uptime_sec, total_scans
        )

        if self.db.is_connected():
            self.db.insert_gateway_status(
                status=status,
                ip_address=ip_address,
                wifi_rssi_dbm=wifi_rssi_dbm,
                lora_status=lora_status,
                uptime_sec=uptime_sec,
                total_scans=total_scans
            )

    def _reconnect_database(self) -> None:
        """Attempt to re-establish the database connection pool."""
        logger.info("Attempting database reconnect...")
        for attempt in range(5):
            if self.db.connect():
                logger.info("Database reconnected on attempt %s.", attempt + 1)
                return
            logger.warning(
                "DB reconnect attempt %s/5 failed. Retrying in %ss...",
                attempt + 1, Config.DB_RECONNECT_DELAY
            )
            time.sleep(Config.DB_RECONNECT_DELAY)
        logger.error(
            "All DB reconnect attempts failed. "
            "Continuing without persistence."
        )

    def _print_stats(self):
        """Log runtime statistics for observability."""
        logger.info(
            "Stats | received=%s, inserted=%s, failed=%s, parse_errors=%s",
            self._stats['messages_received'],
            self._stats['inserts_successful'],
            self._stats['inserts_failed'],
            self._stats['parse_errors']
        )

    def start(self) -> None:
        """Initialize all connections and start the daemon event loop."""
        logger.info("Starting mqtt_to_db daemon...")
        logger.info(
            "  MQTT: %s:%s",
            Config.MQTT_BROKER_HOST, Config.MQTT_BROKER_PORT
        )
        logger.info(
            "  DB:   %s:%s/%s",
            Config.DB_HOST, Config.DB_PORT, Config.DB_NAME
        )
        logger.info(
            "  Topics: %s, %s",
            Config.MQTT_TOPIC_RESULT, Config.MQTT_TOPIC_STATUS
        )
        logger.info(
            "  Anomaly threshold: confidence < %s%%",
            Config.CONFIDENCE_ANOMALY_THRESHOLD
        )

        # ── Connect to Database ────────────────────────────────────────────
        logger.info("Connecting to TimescaleDB...")
        while not self.db.connect():
            logger.warning(
                "DB not ready — retrying in %ss...",
                Config.DB_RECONNECT_DELAY
            )
            time.sleep(Config.DB_RECONNECT_DELAY)

        # ── Configure MQTT Client ─────────────────────────────────────────
        self.mqtt_client = mqtt.Client(
            client_id=Config.MQTT_CLIENT_ID,
            clean_session=True,
            protocol=mqtt.MQTTv311
        )

        self.mqtt_client.username_pw_set(
            Config.MQTT_USERNAME,
            Config.MQTT_PASSWORD
        )

        # Set Last Will & Testament (LWT) for daemon crash detection
        lwt_payload = json.dumps({
            "status": "offline",
            "reason": "daemon_crash"
        })
        self.mqtt_client.will_set(
            Config.MQTT_TOPIC_STATUS,
            payload=lwt_payload,
            qos=0,
            retain=False
        )

        # Assign callbacks
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self._on_message

        # Configure automatic reconnection (exponential backoff 1s→60s)
        self.mqtt_client.reconnect_delay_set(
            min_delay=int(Config.MQTT_RECONNECT_DELAY_MIN),
            max_delay=int(Config.MQTT_RECONNECT_DELAY_MAX)
        )

        # ── Connect to Mosquitto ───────────────────────────────────────────
        logger.info("Connecting to MQTT broker %s...", Config.MQTT_BROKER_HOST)
        while True:
            try:
                self.mqtt_client.connect(
                    Config.MQTT_BROKER_HOST,
                    Config.MQTT_BROKER_PORT,
                    Config.MQTT_KEEPALIVE
                )
                break
            except (ConnectionRefusedError, OSError) as e:
                logger.warning(
                    "MQTT connect failed: %s. Retrying in %ss...",
                    e, Config.MQTT_RECONNECT_DELAY_MIN
                )
                time.sleep(Config.MQTT_RECONNECT_DELAY_MIN)

        # ── Start MQTT Network Loop (background thread) ────────────────────
        # loop_start() creates a background thread that handles:
        #   - Sending/receiving MQTT packets
        #   - Keepalive PING/PINGRESP
        #   - Automatic reconnect after disconnect
        self.mqtt_client.loop_start()
        self._running = True

        logger.info("mqtt_to_db daemon running. Press Ctrl+C to stop.")

        # ── Main Thread: Periodic Statistics Logging ───────────────────────
        stats_interval_sec = 300  # Log stats every 5 minutes
        last_stats_time = time.monotonic()

        try:
            while self._running:
                time.sleep(1)

                # Periodic stats logging
                if (time.monotonic() - last_stats_time) >= stats_interval_sec:
                    self._print_stats()
                    last_stats_time = time.monotonic()

        except KeyboardInterrupt:
            logger.info("Interrupt received — shutting down gracefully...")

        finally:
            self.stop()

    def stop(self) -> None:
        """Gracefully shut down MQTT and database connections."""
        self._running = False

        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            logger.info("MQTT client disconnected.")

        self.db.close()
        self._print_stats()
        logger.info("mqtt_to_db daemon stopped.")


###############################################################################
# Signal Handlers (for Docker graceful shutdown)
###############################################################################

_daemon: Optional[MqttToDbDaemon] = None


def _signal_handler(signum, _frame):
    """Handle SIGTERM (Docker stop) and SIGINT (Ctrl+C) for graceful exit."""
    sig_name = signal.Signals(signum).name
    logger.info("Received signal %s — initiating graceful shutdown.", sig_name)
    if _daemon:
        _daemon.stop()
    sys.exit(0)


if __name__ == "__main__":

    # Register signal handlers for graceful Docker shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT,  _signal_handler)

    _daemon = MqttToDbDaemon()
    _daemon.start()
