"""
FILE: 5_web_dashboard/backend/api_server_monitoring_integration.py
PROJECT: Example of how to integrate monitoring into api_server.py
DESCRIPTION:
  This is an example snippet showing how to add monitoring support
  to the existing api_server.py file.
"""

# ============================================================================
# INTEGRATION SNIPPET FOR api_server.py
# ============================================================================

# Add these imports at the top of api_server.py
from sys import path as sys_path
sys_path.insert(0, str(Path(__file__).parent.parent.parent / "0_shared"))

from logger_config import setup_logger, get_logger
from error_tracker import ErrorTracker, ErrorCategory, ErrorSeverity
from performance_monitor import PerformanceMonitor
from db_logging import DatabaseLogger

# Import monitoring API router
from monitoring_api import router as monitoring_router, set_monitoring_services


# ============================================================================
# MODIFY LIFESPAN FUNCTION
# ============================================================================

@asynccontextmanager
async def lifespan(api_app: FastAPI) -> AsyncIterator[None]:
    """Create asyncpg connection pool on startup, close on shutdown."""
    
    dsn = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    
    # Setup logging (NEW)
    setup_logger(app_name="dashboard_api", log_level="INFO")
    logger = get_logger("dashboard_api")
    
    logger.info_structured(
        "Connecting to TimescaleDB",
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
    )
    
    try:
        api_app.state.pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=DB_POOL_MIN,
            max_size=DB_POOL_MAX,
            command_timeout=10,
        )
        logger.info_structured("Database pool ready")
        
        # Initialize monitoring services (NEW)
        error_tracker = ErrorTracker(logger=logger)
        perf_monitor = PerformanceMonitor(logger=logger)
        db_logger = DatabaseLogger(api_app.state.pool, logger=logger)
        
        # Store in app state
        api_app.state.error_tracker = error_tracker
        api_app.state.perf_monitor = perf_monitor
        api_app.state.db_logger = db_logger
        api_app.state.logger = logger
        
        # Inject into monitoring API
        set_monitoring_services(error_tracker, perf_monitor, db_logger, logger)
        
    except Exception as exc:
        logger.error_structured(
            "Database pool creation failed",
            error=str(exc),
            error_code="DB_POOL_CREATION_FAILED",
        )
        raise

    yield  # App is running here

    await api_app.state.pool.close()
    logger.info_structured("Database pool closed")


# ============================================================================
# MODIFY APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="TBS Grading Dashboard API",
    description="REST API for the Edge AI Palm Oil FFB Grading Dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Include monitoring router (NEW)
app.include_router(monitoring_router)


# ============================================================================
# ADD MIDDLEWARE FOR REQUEST TRACKING (OPTIONAL)
# ============================================================================

@app.middleware("http")
async def request_tracking_middleware(request, call_next):
    """Track all API requests with performance monitoring."""
    monitor = request.app.state.perf_monitor
    logger = request.app.state.logger
    
    # Create operation name
    op_name = f"{request.method}_{request.url.path}".replace("/", "_").strip("_")
    
    with monitor.track_operation(op_name, component="api_server"):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            # Track error
            error_tracker = request.app.state.error_tracker
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


# ============================================================================
# MODIFY ENDPOINTS WITH ERROR TRACKING
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint with error tracking."""
    monitor = request.app.state.perf_monitor
    tracker = request.app.state.error_tracker
    logger = request.app.state.logger
    
    try:
        with monitor.track_operation("health_check", component="api_server"):
            # Check database connection
            async with request.app.state.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            logger.info_structured(
                "Health check passed",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            
            return {
                "status": "healthy",
                "component": "dashboard_api",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as exc:
        tracker.track_error(
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            message=f"Health check failed: {exc}",
            error_code="HEALTH_CHECK_FAILED",
            component="api_server",
        )
        raise HTTPException(status_code=500, detail="Health check failed")


@app.get("/api/stats/today")
async def get_today_stats():
    """Get today's statistics with error tracking."""
    monitor = request.app.state.perf_monitor
    tracker = request.app.state.error_tracker
    logger = request.app.state.logger
    
    try:
        with monitor.track_operation("get_today_stats", component="api_server"):
            async with request.app.state.pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_scans,
                        COUNT(CASE WHEN grade = 1 THEN 1 END) as matang,
                        COUNT(CASE WHEN grade = 0 THEN 1 END) as mentah,
                        COUNT(CASE WHEN grade = 2 THEN 1 END) as overripe,
                        COUNT(CASE WHEN grade = 3 THEN 1 END) as janjang
                    FROM grading_events
                    WHERE DATE(timestamp) = CURRENT_DATE
                """)
            
            logger.info_structured(
                "Today stats retrieved",
                total_scans=result["total_scans"],
            )
            
            return {
                "total_scans": result["total_scans"],
                "matang": result["matang"],
                "mentah": result["mentah"],
                "overripe": result["overripe"],
                "janjang": result["janjang"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as exc:
        tracker.track_error(
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            message=f"Failed to fetch stats: {exc}",
            error_code="FETCH_STATS_FAILED",
            component="api_server",
            context={"endpoint": "/api/stats/today"},
        )
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")


@app.get("/api/events/recent")
async def get_recent_events(limit: int = Query(50, le=500)):
    """Get recent events with error tracking."""
    monitor = request.app.state.perf_monitor
    tracker = request.app.state.error_tracker
    
    try:
        with monitor.track_operation("get_recent_events", component="api_server"):
            async with request.app.state.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM grading_events
                    ORDER BY timestamp DESC
                    LIMIT $1
                """, limit)
            
            return {
                "count": len(rows),
                "events": [dict(row) for row in rows],
            }
    except Exception as exc:
        tracker.track_error(
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.ERROR,
            message=f"Failed to fetch events: {exc}",
            error_code="FETCH_EVENTS_FAILED",
            component="api_server",
        )
        raise HTTPException(status_code=500, detail="Failed to fetch events")


# ============================================================================
# END OF INTEGRATION SNIPPET
# ============================================================================

"""
INTEGRATION CHECKLIST:

1. ✅ Add imports from 0_shared modules
2. ✅ Initialize monitoring services in lifespan
3. ✅ Store services in app.state
4. ✅ Inject into monitoring API router
5. ✅ Include monitoring router in app
6. ✅ Add request tracking middleware (optional)
7. ✅ Update endpoints with error tracking
8. ✅ Use monitor.track_operation() context manager
9. ✅ Call tracker.track_error() on exceptions
10. ✅ Use logger.info_structured() for important events

After integration:
- Dashboard accessible at /monitoring
- All endpoints tracked with latency
- All errors captured and displayed
- Real-time monitoring available

Test with:
- python demo_system.py  (for core system)
- curl http://localhost:8000/api/monitoring/system/overview
- curl http://localhost:8000/monitoring  (for dashboard)
"""
