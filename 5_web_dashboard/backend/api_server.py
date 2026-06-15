###############################################################################
# FILE: 5_web_dashboard/backend/api_server.py
# PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Web Dashboard
# DESCRIPTION:
#   FastAPI REST API server that exposes TimescaleDB grading data to the
#   web dashboard frontend. Provides endpoints for:
#     - Today's production statistics
#     - Recent scan events (live feed table)
#     - Throughput trend (time-series for chart)
#     - Grade distribution trend (hourly breakdown)
#     - Gateway status
#
# ALL configuration via environment variables (Docker-friendly).
#
# ENDPOINTS:
#   GET /health                        — Health check
#   GET /api/stats/today               — Today's aggregated counts
#   GET /api/events/recent?limit=50    — Latest N scan events
#   GET /api/trend/throughput?minutes=30 — Throughput per-minute timeseries
#   GET /api/trend/grades?hours=24     — Hourly grade breakdown
#   GET /api/gateway/status            — Latest gateway heartbeat row
###############################################################################

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("dashboard_api")

# ── Configuration from environment ────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST",     "timescaledb")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME",     "grading_db")
DB_USER     = os.getenv("DB_USER",     "tbs_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secure_db_pass_123")

# asyncpg connection pool (min 2, max 10)
DB_POOL_MIN = 2
DB_POOL_MAX = 10

# ── Application lifespan (startup / shutdown) ──────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create asyncpg connection pool on startup, close on shutdown."""
    dsn = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    logger.info(f"Connecting to TimescaleDB at {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    try:
        app.state.pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=DB_POOL_MIN,
            max_size=DB_POOL_MAX,
            command_timeout=10,
        )
        logger.info("Database connection pool ready.")
    except Exception as exc:
        logger.error(f"Database pool creation failed: {exc}")
        raise

    yield  # App is running here

    await app.state.pool.close()
    logger.info("Database pool closed.")


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TBS Grading Dashboard API",
    description="REST API for the Edge AI Palm Oil FFB Grading Dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the Nginx-served frontend (same origin or localhost dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restricted to LAN; tighten in internet deployments
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Helper ─────────────────────────────────────────────────────────────────────

async def _query(sql: str, *args: Any) -> list[dict]:
    """Execute a SELECT query and return a list of row dicts."""
    try:
        async with app.state.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(row) for row in rows]
    except asyncpg.PostgresError as exc:
        logger.error(f"DB query failed: {exc}\nSQL: {sql[:200]}")
        raise HTTPException(status_code=503, detail="Database query failed")


async def _query_one(sql: str, *args: Any) -> dict | None:
    """Execute a SELECT query and return a single row dict or None."""
    try:
        async with app.state.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
            return dict(row) if row else None
    except asyncpg.PostgresError as exc:
        logger.error(f"DB query_one failed: {exc}\nSQL: {sql[:200]}")
        raise HTTPException(status_code=503, detail="Database query failed")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check() -> dict:
    """Health check — also validates DB connectivity."""
    try:
        async with app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"DB unreachable: {exc}")


@app.get("/api/stats/today")
async def stats_today() -> dict:
    """
    Today's aggregated production statistics.

    Returns:
        total_scanned:   Total bunches scanned today
        mentah_count:    Class 0 count
        matang_count:    Class 1 count
        overripe_count:  Class 2 count
        janjang_count:   Class 3 (empty bunch) count
        anomaly_count:   Total anomaly events
        avg_confidence:  Average model confidence (%)
        matang_rate_pct: Percentage of bunches graded Matang
    """
    sql = """
        SELECT
            COUNT(*)                                            AS total_scanned,
            COUNT(*) FILTER (WHERE grade = 0)                  AS mentah_count,
            COUNT(*) FILTER (WHERE grade = 1)                  AS matang_count,
            COUNT(*) FILTER (WHERE grade = 2)                  AS overripe_count,
            COUNT(*) FILTER (WHERE grade = 3)                  AS janjang_count,
            COUNT(*) FILTER (WHERE is_anomaly)                 AS anomaly_count,
            ROUND(AVG(confidence_pct), 1)                      AS avg_confidence,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE grade = 1)
                / NULLIF(COUNT(*), 0),
            1)                                                 AS matang_rate_pct
        FROM grading_events
        WHERE event_time >= CURRENT_DATE
    """
    row = await _query_one(sql)
    if not row:
        return {
            "total_scanned": 0, "mentah_count": 0, "matang_count": 0,
            "overripe_count": 0, "janjang_count": 0, "anomaly_count": 0,
            "avg_confidence": 0.0, "matang_rate_pct": 0.0,
        }
    # Coerce asyncpg Decimal → float for JSON serialization
    return {k: (float(v) if v is not None else 0) for k, v in row.items()}


@app.get("/api/events/recent")
async def events_recent(
    limit: int = Query(default=50, ge=1, le=200, description="Max rows to return"),
) -> list[dict]:
    """
    Latest N scan events for the live feed table.

    Returns rows ordered by event_time DESC, each with:
        event_time, grade, grade_name, confidence_pct,
        is_anomaly, transport, scan_count
    """
    sql = """
        SELECT
            event_time,
            grade,
            grade_name,
            confidence_pct,
            is_anomaly,
            transport,
            scan_count
        FROM grading_events
        ORDER BY event_time DESC
        LIMIT $1
    """
    rows = await _query(sql, limit)
    # Serialize datetimes to ISO strings for JSON
    for row in rows:
        if row.get("event_time"):
            row["event_time"] = row["event_time"].isoformat()
    return rows


@app.get("/api/trend/throughput")
async def trend_throughput(
    minutes: int = Query(default=30, ge=5, le=1440, description="Rolling window in minutes"),
) -> list[dict]:
    """
    Bunches-per-minute throughput for the last N minutes (1-min buckets).

    Returns list of { bucket: ISO-datetime, count: int } for Chart.js.
    """
    sql = """
        SELECT
            time_bucket('1 minute', event_time) AS bucket,
            COUNT(*)                             AS count
        FROM grading_events
        WHERE event_time >= NOW() - ($1 || ' minutes')::INTERVAL
        GROUP BY bucket
        ORDER BY bucket ASC
    """
    rows = await _query(sql, str(minutes))
    for row in rows:
        if row.get("bucket"):
            row["bucket"] = row["bucket"].isoformat()
        row["count"] = int(row["count"])
    return rows


@app.get("/api/trend/grades")
async def trend_grades(
    hours: int = Query(default=24, ge=1, le=168, description="Hours of history"),
) -> list[dict]:
    """
    Hourly grade count breakdown for the last N hours.

    Returns list of {
        bucket, mentah, matang, overripe, janjang_kosong
    } for stacked bar or multi-line chart.
    """
    sql = """
        SELECT
            time_bucket('1 hour', event_time)                    AS bucket,
            COUNT(*) FILTER (WHERE grade = 0)                    AS mentah,
            COUNT(*) FILTER (WHERE grade = 1)                    AS matang,
            COUNT(*) FILTER (WHERE grade = 2)                    AS overripe,
            COUNT(*) FILTER (WHERE grade = 3)                    AS janjang_kosong
        FROM grading_events
        WHERE event_time >= NOW() - ($1 || ' hours')::INTERVAL
        GROUP BY bucket
        ORDER BY bucket ASC
    """
    rows = await _query(sql, str(hours))
    for row in rows:
        if row.get("bucket"):
            row["bucket"] = row["bucket"].isoformat()
        for key in ("mentah", "matang", "overripe", "janjang_kosong"):
            row[key] = int(row.get(key) or 0)
    return rows


@app.get("/api/gateway/status")
async def gateway_status() -> dict:
    """Latest gateway heartbeat row from gateway_status table."""
    sql = """
        SELECT
            event_time,
            gateway_id,
            status,
            ip_address,
            wifi_rssi_dbm,
            lora_status,
            uptime_sec,
            total_scans
        FROM gateway_status
        ORDER BY event_time DESC
        LIMIT 1
    """
    row = await _query_one(sql)
    if not row:
        return {"status": "unknown", "gateway_id": "ESP_TBS_GW_001"}
    if row.get("event_time"):
        row["event_time"] = row["event_time"].isoformat()
    # Flag if last heartbeat is stale (> 90 seconds)
    from datetime import datetime, timezone, timedelta
    if row.get("event_time"):
        last_seen = datetime.fromisoformat(row["event_time"])
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        age_sec = (datetime.now(timezone.utc) - last_seen).total_seconds()
        row["stale"] = age_sec > 90
        row["age_sec"] = int(age_sec)
    return row
