"""
FILE: 0_shared/integration_example.py
PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Integration Examples
DESCRIPTION:
  Examples showing how to integrate error tracking and logging
  into different components of the system.

EXAMPLES:
  1. FastAPI Integration
  2. MQTT Service Integration
  3. Background Task Integration
"""

# ────────────────────────────────────────────────────────────────────────────
# Example 1: FastAPI API Server Integration
# ────────────────────────────────────────────────────────────────────────────

"""
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from typing import AsyncIterator

from logger_config import setup_logger, get_logger
from error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity
from performance_monitor import PerformanceMonitor
from db_logging import DatabaseLogger


# Setup logging at app startup
logger = get_logger("dashboard_api")

# Initialize error tracker
error_tracker = ErrorTracker(
    logger=logger,
    alert_callback=None,  # Can be set to a function to handle alerts
)

# Initialize performance monitor
perf_monitor = PerformanceMonitor(logger=logger)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    '''Setup and teardown'''
    
    # Setup logging
    setup_logger(
        app_name="dashboard_api",
        log_level="INFO",
        log_dir="logs",
    )
    
    logger.info_structured(
        "Starting Dashboard API",
        version="1.0.0",
        environment="production",
    )
    
    # Create database connection pool
    import asyncpg
    dsn = "postgresql://user:password@host/dbname"
    app.state.pool = await asyncpg.create_pool(dsn)
    
    # Initialize database logger
    db_logger = DatabaseLogger(app.state.pool, logger=logger)
    app.state.db_logger = db_logger
    
    yield  # App is running
    
    await app.state.pool.close()
    logger.info_structured("Dashboard API shutdown")


app = FastAPI(lifespan=lifespan)


# Middleware for tracking requests
@app.middleware("http")
async def request_tracking_middleware(request, call_next):
    '''Track all API requests'''
    with perf_monitor.track_operation(
        f"api_{request.method}_{request.url.path}",
        component="api_server",
        tags={"method": request.method, "path": request.url.path}
    ):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            # Track error
            error_tracker.track_error(
                category=ErrorCategory.API,
                severity=ErrorSeverity.ERROR,
                message=f"Request failed: {exc}",
                error_code="API_REQUEST_FAILED",
                component="api_server",
                context={
                    "method": request.method,
                    "path": request.url.path,
                    "exception": str(exc),
                },
                traceback=traceback.format_exc(),
            )
            raise


@app.get("/health")
async def health_check():
    '''Health check endpoint with error tracking'''
    try:
        with perf_monitor.track_operation("health_check", component="api_server"):
            # Check database connection
            async with app.state.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            return {
                "status": "healthy",
                "component": "dashboard_api",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as exc:
        error_tracker.track_error(
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            message=f"Health check failed: {exc}",
            error_code="HEALTH_CHECK_FAILED",
            component="api_server",
        )
        raise HTTPException(status_code=500, detail="Health check failed")


@app.get("/api/stats/today")
async def get_today_stats():
    '''Get today's statistics with error tracking'''
    try:
        with perf_monitor.track_operation("get_today_stats", component="api_server"):
            async with app.state.pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT COUNT(*), 
                           COUNT(CASE WHEN grade = 1 THEN 1 END) as matang_count
                    FROM grading_events
                    WHERE DATE(timestamp) = CURRENT_DATE
                """)
            
            return {
                "total_scans": result["count"],
                "matang_count": result["matang_count"],
            }
    except Exception as exc:
        error_tracker.track_error(
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            message=f"Failed to fetch today's stats: {exc}",
            error_code="FETCH_STATS_FAILED",
            component="api_server",
            context={"endpoint": "/api/stats/today"},
        )
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")


@app.get("/api/errors/recent")
async def get_recent_errors(hours: int = 24, limit: int = 50):
    '''Get recent errors'''
    errors = error_tracker.get_recent_errors(limit=limit)
    return {"errors": errors, "total": len(errors)}


@app.get("/api/system/health")
async def get_system_health():
    '''Get system health status'''
    health_status = {
        "api_server": error_tracker.get_component_health("api_server"),
        "database": error_tracker.get_component_health("database"),
        "mqtt": error_tracker.get_component_health("mqtt"),
    }
    
    # Get performance stats
    perf_stats = perf_monitor.get_operation_stats()
    
    return {
        "health": health_status,
        "performance": perf_stats,
    }
"""


# ────────────────────────────────────────────────────────────────────────────
# Example 2: MQTT Service Integration (mqtt_to_db.py)
# ────────────────────────────────────────────────────────────────────────────

"""
import paho.mqtt.client as mqtt
from logger_config import setup_logger, get_logger
from error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity
from performance_monitor import PerformanceMonitor


class MQTTService:
    def __init__(self):
        self.logger = get_logger("mqtt_to_db")
        self.error_tracker = ErrorTracker(logger=self.logger)
        self.perf_monitor = PerformanceMonitor(logger=self.logger)
        
        # Setup logging
        setup_logger(
            app_name="mqtt_to_db",
            log_level="INFO",
        )
    
    def on_connect(self, client, userdata, flags, rc):
        '''MQTT connect callback'''
        if rc == 0:
            self.logger.info_structured(
                "Connected to MQTT broker",
                broker="mosquitto",
                port=1883,
            )
            client.subscribe("pks/grading/tbs/result", qos=1)
        else:
            self.error_tracker.track_error(
                category=ErrorCategory.MQTT,
                severity=ErrorSeverity.ERROR,
                message=f"MQTT connection failed with code {rc}",
                error_code=f"MQTT_CONNECT_ERROR_{rc}",
                component="mqtt_to_db",
            )
    
    def on_message(self, client, userdata, msg):
        '''MQTT message callback'''
        with self.perf_monitor.track_operation(
            "mqtt_message_processing",
            component="mqtt_to_db",
        ):
            try:
                # Parse message
                payload = json.loads(msg.payload.decode())
                
                self.logger.debug_structured(
                    "MQTT message received",
                    topic=msg.topic,
                    payload=payload,
                )
                
                # Process and insert to database
                self._process_grading_result(payload)
                
            except json.JSONDecodeError as e:
                self.error_tracker.track_error(
                    category=ErrorCategory.DATA_PROCESSING,
                    severity=ErrorSeverity.WARNING,
                    message=f"Failed to parse MQTT payload: {e}",
                    error_code="JSON_PARSE_ERROR",
                    component="mqtt_to_db",
                    context={"topic": msg.topic, "raw": msg.payload[:100]},
                )
            except Exception as e:
                self.error_tracker.track_error(
                    category=ErrorCategory.MQTT,
                    severity=ErrorSeverity.ERROR,
                    message=f"Error processing MQTT message: {e}",
                    error_code="MQTT_PROCESSING_ERROR",
                    component="mqtt_to_db",
                    traceback=traceback.format_exc(),
                )
    
    def _process_grading_result(self, payload):
        '''Process grading result'''
        with self.perf_monitor.track_operation(
            "database_insert",
            component="mqtt_to_db",
        ):
            # Insert to database
            # ... database code ...
            pass
"""


# ────────────────────────────────────────────────────────────────────────────
# Example 3: Background Task Integration
# ────────────────────────────────────────────────────────────────────────────

"""
import asyncio
from logger_config import get_logger
from error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity
from performance_monitor import PerformanceMonitor
from db_logging import DatabaseLogger


class HealthCheckTask:
    def __init__(self, db_pool, logger=None):
        self.db_pool = db_pool
        self.logger = logger or get_logger("health_check")
        self.error_tracker = ErrorTracker(logger=self.logger)
        self.perf_monitor = PerformanceMonitor(logger=self.logger)
        self.db_logger = DatabaseLogger(db_pool, logger=self.logger)
    
    async def run_periodic_health_check(self):
        '''Run periodic health checks'''
        while True:
            try:
                with self.perf_monitor.track_operation(
                    "health_check_cycle",
                    component="health_checker",
                ):
                    # Check database
                    await self._check_database_health()
                    
                    # Check MQTT
                    await self._check_mqtt_health()
                    
                    # Get statistics and log
                    stats = self.error_tracker.get_error_stats(minutes=60)
                    self.logger.info_structured(
                        "Health check completed",
                        error_stats=stats,
                    )
                
                await asyncio.sleep(300)  # 5 minutes
            except Exception as e:
                self.error_tracker.track_error(
                    category=ErrorCategory.RESOURCE,
                    severity=ErrorSeverity.ERROR,
                    message=f"Health check failed: {e}",
                    error_code="HEALTH_CHECK_FAILED",
                    component="health_checker",
                    traceback=traceback.format_exc(),
                )
                await asyncio.sleep(60)  # Retry after 1 minute
    
    async def _check_database_health(self):
        '''Check database health'''
        try:
            async with self.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            self.logger.debug_structured("Database healthy")
        except Exception as e:
            self.error_tracker.track_error(
                category=ErrorCategory.DATABASE,
                severity=ErrorSeverity.CRITICAL,
                message=f"Database connection failed: {e}",
                error_code="DB_CONNECTION_FAILED",
                component="database",
            )
    
    async def _check_mqtt_health(self):
        '''Check MQTT broker health'''
        # Implementation would check MQTT connection
        pass


async def cleanup_old_logs_task(db_pool, db_logger):
    '''Periodic task to cleanup old logs'''
    while True:
        try:
            result = await db_logger.cleanup_old_logs(days=30)
            logger = get_logger("cleanup_task")
            logger.info_structured(
                "Cleanup completed",
                records_deleted=result,
            )
        except Exception as e:
            logger = get_logger("cleanup_task")
            logger.error_structured(
                f"Cleanup failed: {e}",
                error_code="CLEANUP_FAILED",
            )
        
        await asyncio.sleep(86400)  # 24 hours
"""
