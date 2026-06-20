"""
FILE: 5_web_dashboard/backend/monitoring_api.py
PROJECT: Edge AI Palm Oil FFB (TBS) - Monitoring API Endpoints
DESCRIPTION:
  API endpoints for error tracking, logging, and system monitoring.
  Provides real-time data for the monitoring dashboard.

ENDPOINTS:
  GET /api/monitoring/errors/recent          — Recent errors
  GET /api/monitoring/errors/stats            — Error statistics
  GET /api/monitoring/errors/by-component     — Errors by component
  GET /api/monitoring/alerts/active           — Active alerts
  GET /api/monitoring/alerts/history          — Alert history
  GET /api/monitoring/components/health       — Component health status
  GET /api/monitoring/performance/metrics     — Performance metrics
  GET /api/monitoring/system/overview         — System overview
  POST /api/monitoring/alerts/{id}/acknowledge — Acknowledge alert
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

# Will be injected from main app
monitoring_services = {}


def set_monitoring_services(error_tracker, perf_monitor, db_logger, logger):
    """Inject monitoring services into router."""
    monitoring_services["error_tracker"] = error_tracker
    monitoring_services["perf_monitor"] = perf_monitor
    monitoring_services["db_logger"] = db_logger
    monitoring_services["logger"] = logger


@router.get("/errors/recent")
async def get_recent_errors(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=500),
    component: Optional[str] = None,
    severity: Optional[str] = None,
):
    """Get recent error events."""
    try:
        tracker = monitoring_services.get("error_tracker")
        if not tracker:
            raise HTTPException(status_code=503, detail="Error tracker not available")
        
        errors = tracker.get_recent_errors(limit=limit)
        
        # Filter by component
        if component:
            errors = [e for e in errors if e["component"] == component]
        
        # Filter by severity
        if severity:
            errors = [e for e in errors if e["severity"] == severity]
        
        return {
            "count": len(errors),
            "errors": errors,
            "filters": {
                "hours": hours,
                "component": component,
                "severity": severity,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors/stats")
async def get_error_statistics(minutes: int = Query(60, ge=1, le=1440)):
    """Get error statistics for the time window."""
    try:
        tracker = monitoring_services.get("error_tracker")
        if not tracker:
            raise HTTPException(status_code=503, detail="Error tracker not available")
        
        stats = tracker.get_error_stats(minutes=minutes)
        
        # Calculate additional metrics
        total_errors = len(tracker.error_history)
        critical_errors = sum(
            1 for e in tracker.error_history
            if str(e.severity).lower() == "critical"
        )
        error_rate = len(tracker.error_history) / (minutes / 60) if minutes > 0 else 0
        
        return {
            "statistics": stats,
            "total_errors": total_errors,
            "critical_count": critical_errors,
            "error_rate_per_hour": error_rate,
            "time_window_minutes": minutes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors/by-component")
async def get_errors_by_component(hours: int = Query(24, ge=1, le=168)):
    """Get error distribution by component."""
    try:
        tracker = monitoring_services.get("error_tracker")
        if not tracker:
            raise HTTPException(status_code=503, detail="Error tracker not available")
        
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=hours)
        
        errors_by_component = {}
        for error in tracker.error_history:
            if error.timestamp > window_start:
                component = error.component
                if component not in errors_by_component:
                    errors_by_component[component] = {
                        "total": 0,
                        "by_severity": {},
                        "last_error": None,
                    }
                
                errors_by_component[component]["total"] += 1
                severity = str(error.severity).lower()
                errors_by_component[component]["by_severity"][severity] = \
                    errors_by_component[component]["by_severity"].get(severity, 0) + 1
                errors_by_component[component]["last_error"] = error.timestamp.isoformat()
        
        return {
            "components": errors_by_component,
            "total_components": len(errors_by_component),
            "time_window_hours": hours,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/active")
async def get_active_alerts(limit: int = Query(50, ge=1, le=200)):
    """Get active (unacknowledged) alerts."""
    try:
        tracker = monitoring_services.get("error_tracker")
        if not tracker:
            raise HTTPException(status_code=503, detail="Error tracker not available")
        
        alerts = tracker.get_active_alerts()
        
        return {
            "count": len(alerts),
            "alerts": alerts[:limit],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/components/health")
async def get_components_health():
    """Get health status of all components."""
    try:
        tracker = monitoring_services.get("error_tracker")
        if not tracker:
            raise HTTPException(status_code=503, detail="Error tracker not available")
        
        components = [
            "api_server",
            "mqtt_to_db",
            "database",
            "edge_device",
            "mqtt_broker",
        ]
        
        health_status = {}
        for component in components:
            health = tracker.get_component_health(component)
            health_status[component] = health
        
        # Calculate overall status
        critical_components = sum(
            1 for h in health_status.values() if h["status"] == "critical"
        )
        degraded_components = sum(
            1 for h in health_status.values() if h["status"] in ["degraded", "unhealthy"]
        )
        
        overall_status = "critical" if critical_components > 0 else \
                        "warning" if degraded_components > 0 else "healthy"
        
        return {
            "components": health_status,
            "overall_status": overall_status,
            "critical_count": critical_components,
            "degraded_count": degraded_components,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/metrics")
async def get_performance_metrics(minutes: int = Query(60, ge=1, le=1440)):
    """Get performance metrics."""
    try:
        monitor = monitoring_services.get("perf_monitor")
        if not monitor:
            raise HTTPException(status_code=503, detail="Performance monitor not available")
        
        # Get operation statistics
        op_stats = monitor.get_operation_stats()
        
        # Get specific metrics
        db_query_stats = monitor.get_metric_stats("database_query_duration_ms", minutes)
        api_stats = monitor.get_metric_stats("api_response_duration_ms", minutes)
        
        return {
            "operation_stats": op_stats,
            "database_query": db_query_stats,
            "api_response": api_stats,
            "time_window_minutes": minutes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/overview")
async def get_system_overview():
    """Get overall system status overview."""
    try:
        tracker = monitoring_services.get("error_tracker")
        monitor = monitoring_services.get("perf_monitor")
        
        if not tracker or not monitor:
            raise HTTPException(status_code=503, detail="Services not available")
        
        # Get stats
        error_stats = tracker.get_error_stats(minutes=60)
        perf_stats = monitor.get_operation_stats()
        
        # Get component health
        components = ["api_server", "mqtt_to_db", "database"]
        health_by_component = {
            comp: tracker.get_component_health(comp) for comp in components
        }
        
        # Get alerts
        active_alerts = tracker.get_active_alerts()
        
        return {
            "summary": {
                "total_errors_1h": len(tracker.error_history[-100:]),
                "critical_alerts": len([a for a in active_alerts if a.get("severity") == "critical"]),
                "active_alerts": len(active_alerts),
            },
            "errors": error_stats,
            "performance": perf_stats,
            "components": health_by_component,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int):
    """Acknowledge an alert."""
    try:
        # In a real implementation, this would update the database
        db_logger = monitoring_services.get("db_logger")
        logger = monitoring_services.get("logger")
        
        if db_logger:
            success = await db_logger.acknowledge_alert(alert_id)
            if success:
                logger.info_structured(
                    "Alert acknowledged",
                    alert_id=alert_id,
                    acknowledged_by="api",
                )
                return {"status": "success", "alert_id": alert_id}
            else:
                raise HTTPException(status_code=404, detail="Alert not found")
        else:
            raise HTTPException(status_code=503, detail="Database logger not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/search")
async def search_logs(
    query: str = Query(..., min_length=1),
    component: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    """Search application logs."""
    try:
        # This would search the database in production
        logger = monitoring_services.get("logger")
        
        logger.info_structured(
            "Log search performed",
            query=query,
            component=component,
            level=level,
            limit=limit,
        )
        
        return {
            "query": query,
            "component": component,
            "level": level,
            "results": [],
            "count": 0,
            "note": "Database search results would appear here",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
