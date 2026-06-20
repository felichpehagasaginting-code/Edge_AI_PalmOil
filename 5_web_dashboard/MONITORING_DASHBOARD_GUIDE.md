"""
FILE: 5_web_dashboard/MONITORING_DASHBOARD_GUIDE.md
PROJECT: Monitoring Dashboard - Setup & Integration Guide
DESCRIPTION:
  Complete guide untuk setup dan menggunakan monitoring dashboard UI.
"""

# 🎯 Monitoring Dashboard - Complete Guide

## 📊 Overview

Kami telah membuat **monitoring dashboard interaktif** yang menampilkan:
- ✅ Real-time error tracking dan logs
- ✅ Component health status
- ✅ System-wide alerts
- ✅ Performance metrics
- ✅ Beautiful charts dan visualizations
- ✅ Searchable error logs

---

## 📁 Files Dibuat

```
5_web_dashboard/
├── backend/
│   └── monitoring_api.py        ← API endpoints
│
└── frontend/
    ├── monitoring.html          ← Main dashboard page
    ├── monitoring.js            ← Frontend logic
    └── monitoring.css           ← (included in HTML)
```

---

## 🚀 Quick Start

### Step 1: Add Monitoring API to FastAPI Server

Edit `5_web_dashboard/backend/api_server.py` dan tambahkan:

```python
from monitoring_api import router as monitoring_router, set_monitoring_services

# Di app startup (dalam lifespan function):
# Initialize error tracker
from error_tracker import ErrorTracker
from performance_monitor import PerformanceMonitor
from db_logging import DatabaseLogger

error_tracker = ErrorTracker(logger=logger)
perf_monitor = PerformanceMonitor(logger=logger)
db_logger = DatabaseLogger(pool, logger=logger)

# Inject services ke monitoring API
set_monitoring_services(error_tracker, perf_monitor, db_logger, logger)

# Include monitoring routes
app.include_router(monitoring_router)
```

### Step 2: Update Nginx Config

Edit `nginx.conf` untuk serve monitoring page:

```nginx
location /monitoring {
    alias /var/www/html/monitoring.html;
    try_files $uri $uri/ =404;
}

location /js/monitoring.js {
    alias /var/www/html/js/monitoring.js;
}
```

### Step 3: Access Dashboard

Buka browser:
```
http://localhost:8080/monitoring
```

---

## 📊 Dashboard Features

### 1. **Overview Tab** 📊
- **Statistics Cards**
  - Total Errors (Last Hour)
  - Critical Alerts
  - Active Alerts
  - System Status
  
- **Error Trend Chart**
  - Line chart showing errors over time
  - Last 60 minutes data
  
- **Component Health**
  - Live health status untuk setiap component
  - Error/Warning/Critical counters
  - Status indicators (🟢🟡🔴)

### 2. **Errors Tab** ⚠️
- **Error Table**
  - Time, Message, Component, Severity, Code
  - Real-time updates setiap 10 detik
  
- **Filters**
  - By Component
  - By Severity (Critical, Error, Warning, Info)
  - By Time Window (1h, 6h, 24h, 7d)
  
- **Search & Sort**
  - Clickable columns
  - Message truncation dengan tooltip

### 3. **Alerts Tab** 🔔
- **Active Alerts List**
  - Alert Type, Message, Severity
  - Timestamp setiap alert
  
- **Alert Management**
  - Acknowledge button untuk setiap alert
  - Color-coded by severity (🔴 Critical, 🟠 Warning)
  
- **Alert History**
  - Recent alerts dengan status

### 4. **Components Tab** 🔧
- **Component Status Details**
  - Per-component health breakdown
  - Error counts by type
  - Last error information
  - Status badges

### 5. **Performance Tab** ⚡
- **Performance Metrics Cards**
  - Operation average latency
  - Peak latency
  - Error rate %
  
- **Performance Chart**
  - Bar chart comparing average vs max times
  - Multi-operation visualization
  - Sortable by duration

---

## 🎨 UI Components

### Status Indicators
```
🟢 Healthy      - No issues
🟡 Warning      - Some warnings
🔴 Critical     - Critical errors
```

### Color Coding
- **Critical Errors**: Red (#f44336)
- **Warnings**: Orange (#ff9800)
- **Healthy**: Green (#4caf50)
- **Info**: Blue (#1976d2)

### Interactive Elements
- Tab switching (smooth transitions)
- Real-time data refresh (10 sec)
- Filterable tables
- Responsive design (mobile-friendly)
- Hover effects dan tooltips

---

## 📡 API Endpoints

All endpoints return JSON data:

```
GET /api/monitoring/errors/recent
   Query: hours=24, limit=50, component=, severity=
   Returns: { count, errors[], filters, timestamp }

GET /api/monitoring/errors/stats
   Query: minutes=60
   Returns: { statistics, total_errors, critical_count, error_rate_per_hour }

GET /api/monitoring/errors/by-component
   Query: hours=24
   Returns: { components{}, total_components, time_window_hours }

GET /api/monitoring/alerts/active
   Query: limit=50
   Returns: { count, alerts[], timestamp }

GET /api/monitoring/components/health
   Returns: { components{}, overall_status, critical_count, degraded_count }

GET /api/monitoring/performance/metrics
   Query: minutes=60
   Returns: { operation_stats, database_query, api_response, time_window_minutes }

GET /api/monitoring/system/overview
   Returns: { summary, errors, performance, components, timestamp }

POST /api/monitoring/alerts/{id}/acknowledge
   Returns: { status: "success", alert_id }
```

---

## 🔄 Real-Time Updates

Dashboard automatically refreshes setiap **10 seconds** ketika:
- Tab Overview active
- Tab Errors active
- Tab Components active
- Tab Performance active
- Tab Alerts active

**Manual Refresh**: Klik button "🔄 Refresh"

---

## 🎯 Integration Steps

### 1. Update API Server

```python
# 5_web_dashboard/backend/api_server.py

from monitoring_api import router as monitoring_router, set_monitoring_services
from error_tracker import ErrorTracker
from performance_monitor import PerformanceMonitor
from db_logging import DatabaseLogger

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ... existing setup ...
    
    # Initialize monitoring services
    logger = get_logger("dashboard_api")
    error_tracker = ErrorTracker(logger=logger)
    perf_monitor = PerformanceMonitor(logger=logger)
    db_logger = DatabaseLogger(app.state.pool, logger=logger)
    
    # Inject into monitoring API
    set_monitoring_services(error_tracker, perf_monitor, db_logger, logger)
    
    # Store in app state for use in endpoints
    app.state.error_tracker = error_tracker
    app.state.perf_monitor = perf_monitor
    app.state.db_logger = db_logger
    
    yield
    
    # Cleanup

app = FastAPI(lifespan=lifespan)

# Include monitoring routes
app.include_router(monitoring_router)
```

### 2. Use Monitoring in Endpoints

```python
@app.get("/api/stats/today")
async def get_today_stats():
    monitor = request.app.state.perf_monitor
    tracker = request.app.state.error_tracker
    
    with monitor.track_operation("get_today_stats", component="api"):
        try:
            # Your code
            return result
        except Exception as e:
            tracker.track_error(
                category=ErrorCategory.DATABASE,
                severity=ErrorSeverity.ERROR,
                message=str(e),
                component="api_server",
            )
            raise
```

### 3. Add Dashboard Link to Index

Edit `frontend/index.html` dan tambahkan:

```html
<!-- In navbar or menu -->
<a href="/monitoring" class="nav-link">
    📊 Monitoring Dashboard
</a>
```

---

## 📊 Data Sources

Dashboard mengambil data dari:
1. **Error Tracker** - In-memory error history (1000 events max)
2. **Performance Monitor** - Operation metrics (24 hour window)
3. **Database** - Historical data (via db_logging)
4. **Real-time** - Updated setiap 10 seconds

---

## 🎨 Customization

### Change Refresh Interval

Edit `monitoring.js`:
```javascript
const REFRESH_INTERVAL = 10000; // Change to desired milliseconds
```

### Add New Metrics

1. Add endpoint ke `monitoring_api.py`
2. Add fetch call di `monitoring.js`
3. Add rendering function

### Modify Colors

Edit `monitoring.html` CSS section:
```css
.status-healthy { background: #4caf50; }
.status-warning { background: #ff9800; }
.status-critical { background: #f44336; }
```

### Add More Components

Edit `monitoring_api.py` di endpoint `get_components_health()`:
```python
components = [
    "api_server",
    "mqtt_to_db",
    "database",
    "edge_device",
    "mqtt_broker",
    # Add more here
]
```

---

## 🔍 Troubleshooting

### Dashboard tidak tampil
1. Check file paths di nginx.conf
2. Verify monitoring.html dan monitoring.js accessible
3. Check browser console untuk JavaScript errors

### Data tidak load
1. Verify API endpoints di `monitoring_api.py` mounted di app
2. Check set_monitoring_services() called
3. Check browser Network tab untuk API responses

### Refresh tidak jalan
1. Check REFRESH_INTERVAL di monitoring.js
2. Verify error tracking services initialized
3. Check browser console untuk errors

### Charts tidak render
1. Verify Chart.js CDN accessible
2. Check canvas elements exist
3. Verify data passed to Chart.js

---

## 📈 Performance Notes

- **Chart Updates**: Every 30 seconds
- **Data Refresh**: Every 10 seconds
- **Memory Usage**: ~2-5MB (depends on data volume)
- **Network Usage**: ~50KB per refresh
- **Browser Support**: Chrome, Firefox, Safari, Edge (latest versions)

---

## 🎓 Example Scenarios

### Scenario 1: Monitor API Errors
1. Open Monitoring Dashboard
2. Click "Errors" tab
3. Filter by component: "api_server"
4. Filter by severity: "error"
5. View recent API errors

### Scenario 2: Check System Health
1. Open Monitoring Dashboard
2. Click "Overview" tab
3. View component health indicators
4. See error trends over time
5. Check critical alerts count

### Scenario 3: Investigate Performance
1. Click "Performance" tab
2. View operation latencies
3. Check p95 latencies
4. See which operations are slowest

### Scenario 4: Acknowledge Alerts
1. Click "Alerts" tab
2. Review active alerts
3. Click ✕ to acknowledge each alert
4. Alerts removed from list

---

## 🔐 Security Notes

1. **CORS**: Configure appropriately for your environment
2. **Authentication**: Add auth middleware if needed
3. **Rate Limiting**: Consider rate limiting on endpoints
4. **Data Sensitivity**: Error messages may contain sensitive data

---

## 📚 Related Files

- Core Logic: `0_shared/error_tracker.py`
- Logger: `0_shared/logger_config.py`
- Performance: `0_shared/performance_monitor.py`
- DB: `0_shared/db_logging.py`

---

## ✨ Features Summary

✅ Real-time monitoring dashboard
✅ Beautiful, responsive UI
✅ Component health tracking
✅ Error tracking dengan filtering
✅ Alert management
✅ Performance metrics visualization
✅ Search & filtering
✅ Auto-refresh (configurable)
✅ Multiple tabs dengan different views
✅ Mobile-friendly design

---

## 🚀 Next Steps

1. ✅ Add monitoring endpoints to API server
2. ✅ Access dashboard at `/monitoring`
3. ✅ Configure auto-refresh interval
4. ✅ Add dashboard link to main index
5. ✅ Customize colors & branding
6. ✅ Set up alerts notifications
7. ✅ Integrate with existing dashboard

Ready to go! 🎉
