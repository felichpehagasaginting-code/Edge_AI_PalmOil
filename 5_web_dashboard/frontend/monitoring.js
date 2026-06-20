"""
FILE: 5_web_dashboard/frontend/monitoring.js
PROJECT: Monitoring Dashboard - JavaScript
DESCRIPTION:
  Frontend logic untuk monitoring dashboard UI.
  Handles data fetching, rendering charts, dan real-time updates.
"""

// Configuration
const API_BASE = '/api';
const REFRESH_INTERVAL = 10000; // 10 seconds
const CHART_UPDATE_INTERVAL = 30000; // 30 seconds

// Global state
let currentData = {};
let charts = {};
let autoRefreshEnabled = true;
let autoRefreshTimer = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Monitoring dashboard loaded');
    
    // Load initial data
    loadAllData();
    
    // Setup auto-refresh
    setupAutoRefresh();
});

/**
 * Switch between tabs
 */
function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Deactivate all buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).classList.add('active');
    
    // Activate selected button
    event.target.classList.add('active');
    
    // Load tab-specific data
    if (tabName === 'overview') {
        loadOverviewData();
    } else if (tabName === 'errors') {
        loadErrors();
    } else if (tabName === 'alerts') {
        loadAlerts();
    } else if (tabName === 'components') {
        loadComponentsDetail();
    } else if (tabName === 'performance') {
        loadPerformanceData();
    }
}

/**
 * Load all data
 */
async function loadAllData() {
    console.log('Loading all monitoring data...');
    
    try {
        // Load data for active tab
        const activeTab = document.querySelector('.tab-content.active').id;
        
        if (activeTab === 'overview') {
            await loadOverviewData();
        } else if (activeTab === 'errors') {
            await loadErrors();
        } else if (activeTab === 'alerts') {
            await loadAlerts();
        } else if (activeTab === 'components') {
            await loadComponentsDetail();
        } else if (activeTab === 'performance') {
            await loadPerformanceData();
        }
    } catch (error) {
        console.error('Error loading data:', error);
        showError('Failed to load monitoring data');
    }
}

/**
 * Load overview data
 */
async function loadOverviewData() {
    try {
        // Fetch overview data
        const response = await fetch(`${API_BASE}/monitoring/system/overview`);
        const data = await response.json();
        
        currentData.overview = data;
        
        // Render stats
        renderOverviewStats(data);
        
        // Render component health
        renderComponentHealth(data.components);
        
        // Update error trend chart
        updateErrorTrendChart(data);
        
    } catch (error) {
        console.error('Error loading overview:', error);
    }
}

/**
 * Render overview statistics cards
 */
function renderOverviewStats(data) {
    const container = document.getElementById('overviewStats');
    const summary = data.summary || {};
    
    const html = `
        <div class="stat-card">
            <h3>Total Errors (1h)</h3>
            <div class="stat-value">${summary.total_errors_1h || 0}</div>
            <div class="stat-unit">errors in last hour</div>
        </div>
        
        <div class="stat-card">
            <h3>Critical Alerts</h3>
            <div class="stat-value" style="color: #f44336;">
                ${summary.critical_alerts || 0}
            </div>
            <div class="stat-unit">critical severity</div>
        </div>
        
        <div class="stat-card">
            <h3>Active Alerts</h3>
            <div class="stat-value" style="color: #ff9800;">
                ${summary.active_alerts || 0}
            </div>
            <div class="stat-unit">unacknowledged</div>
        </div>
        
        <div class="stat-card">
            <h3>System Status</h3>
            <div style="margin: 15px 0;">
                <span class="status-indicator status-${getStatusClass(data.components)}"></span>
                <strong>${getSystemStatus(data.components)}</strong>
            </div>
            <div class="stat-unit">overall health</div>
        </div>
    `;
    
    container.innerHTML = html;
}

/**
 * Render component health
 */
function renderComponentHealth(components) {
    const container = document.getElementById('componentHealth');
    
    let html = '';
    for (const [name, health] of Object.entries(components || {})) {
        const statusClass = `status-${health.status}`;
        const statusText = capitalizeFirst(health.status);
        
        html += `
            <div class="component-item">
                <div class="component-name">
                    <span class="status-indicator ${statusClass}"></span>
                    <strong>${capitalizeFirst(name)}</strong>
                </div>
                <div class="component-stats">
                    <div class="component-stat">
                        <div class="component-stat-label">Errors</div>
                        <div class="component-stat-value">${health.errors || 0}</div>
                    </div>
                    <div class="component-stat">
                        <div class="component-stat-label">Warnings</div>
                        <div class="component-stat-value">${health.warnings || 0}</div>
                    </div>
                    <div class="component-stat">
                        <div class="component-stat-label">Critical</div>
                        <div class="component-stat-value" style="color: #f44336;">
                            ${health.critical_errors || 0}
                        </div>
                    </div>
                </div>
                <div style="font-size: 12px; color: #999; min-width: 100px;">
                    ${statusText}
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html || '<div class="loading">No components found</div>';
}

/**
 * Load errors
 */
async function loadErrors() {
    try {
        const hours = document.getElementById('errorHoursFilter')?.value || '24';
        const response = await fetch(
            `${API_BASE}/monitoring/errors/recent?hours=${hours}&limit=100`
        );
        const data = await response.json();
        
        currentData.errors = data.errors || [];
        
        // Update filter options
        updateComponentFilterOptions();
        
        // Render errors
        renderErrors(data.errors || []);
        
    } catch (error) {
        console.error('Error loading errors:', error);
        document.getElementById('errorTableBody').innerHTML = 
            '<div class="loading">Error loading data</div>';
    }
}

/**
 * Update component filter options
 */
function updateComponentFilterOptions() {
    const select = document.getElementById('errorComponentFilter');
    const components = new Set(
        (currentData.errors || []).map(e => e.component)
    );
    
    const currentValue = select.value;
    let html = '<option value="">All Components</option>';
    
    components.forEach(comp => {
        html += `<option value="${comp}">${capitalizeFirst(comp)}</option>`;
    });
    
    select.innerHTML = html;
    select.value = currentValue;
}

/**
 * Filter errors
 */
function filterErrors() {
    const component = document.getElementById('errorComponentFilter').value;
    const severity = document.getElementById('errorSeverityFilter').value;
    
    let filtered = currentData.errors || [];
    
    if (component) {
        filtered = filtered.filter(e => e.component === component);
    }
    
    if (severity) {
        filtered = filtered.filter(e => 
            e.severity.toLowerCase() === severity.toLowerCase()
        );
    }
    
    renderErrors(filtered);
}

/**
 * Render error table
 */
function renderErrors(errors) {
    const container = document.getElementById('errorTableBody');
    
    if (!errors || errors.length === 0) {
        container.innerHTML = '<div class="loading">No errors found</div>';
        return;
    }
    
    let html = '';
    errors.forEach(error => {
        const timestamp = new Date(error.timestamp).toLocaleString();
        const severityClass = `severity-${error.severity.toLowerCase()}`;
        
        html += `
            <div class="table-row">
                <div class="error-time">${formatTime(error.timestamp)}</div>
                <div class="error-message" title="${error.message}">
                    ${truncate(error.message, 50)}
                </div>
                <div class="error-component">${error.component}</div>
                <div class="error-severity ${severityClass}">
                    ${capitalizeFirst(error.severity)}
                </div>
                <div style="font-size: 12px; color: #999;">
                    ${error.error_code || '-'}
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

/**
 * Load alerts
 */
async function loadAlerts() {
    try {
        const response = await fetch(`${API_BASE}/monitoring/alerts/active?limit=50`);
        const data = await response.json();
        
        currentData.alerts = data.alerts || [];
        renderAlerts(data.alerts || []);
        
    } catch (error) {
        console.error('Error loading alerts:', error);
        document.getElementById('alertContainer').innerHTML = 
            '<div class="loading">Error loading alerts</div>';
    }
}

/**
 * Render alerts
 */
function renderAlerts(alerts) {
    const container = document.getElementById('alertContainer');
    
    if (!alerts || alerts.length === 0) {
        container.innerHTML = '<div style="padding: 40px; text-align: center; color: #999;">No active alerts</div>';
        return;
    }
    
    let html = '';
    alerts.forEach((alert, index) => {
        const severity = alert.severity?.toLowerCase() || 'warning';
        const timestamp = new Date(alert.timestamp).toLocaleString();
        
        html += `
            <div class="alert-item ${severity}">
                <div class="alert-content">
                    <div class="alert-title">
                        ${alert.alert_type ? capitalizeFirst(alert.alert_type.replace(/_/g, ' ')) : 'Alert'}
                    </div>
                    <div class="alert-message">${alert.message || 'No message'}</div>
                    <div class="alert-time">${timestamp}</div>
                </div>
                <button class="alert-close" onclick="acknowledgeAlert(${index})">
                    ✕
                </button>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

/**
 * Acknowledge alert
 */
async function acknowledgeAlert(index) {
    const alert = currentData.alerts?.[index];
    if (!alert || !alert.id) return;
    
    try {
        await fetch(
            `${API_BASE}/monitoring/alerts/${alert.id}/acknowledge`,
            { method: 'POST' }
        );
        
        // Reload alerts
        loadAlerts();
    } catch (error) {
        console.error('Error acknowledging alert:', error);
    }
}

/**
 * Load components detail
 */
async function loadComponentsDetail() {
    try {
        const response = await fetch(`${API_BASE}/monitoring/components/health`);
        const data = await response.json();
        
        renderComponentsDetail(data.components || {});
        
    } catch (error) {
        console.error('Error loading components:', error);
        document.getElementById('componentsDetail').innerHTML = 
            '<div class="loading">Error loading components</div>';
    }
}

/**
 * Render components detail
 */
function renderComponentsDetail(components) {
    const container = document.getElementById('componentsDetail');
    
    let html = '';
    for (const [name, health] of Object.entries(components || {})) {
        const statusClass = `status-${health.status}`;
        
        html += `
            <div class="component-item">
                <div class="component-name">
                    <span class="status-indicator ${statusClass}"></span>
                    <strong>${capitalizeFirst(name)}</strong>
                </div>
                <div class="component-stats">
                    <div class="component-stat">
                        <div class="component-stat-label">Errors</div>
                        <div class="component-stat-value">${health.errors || 0}</div>
                    </div>
                    <div class="component-stat">
                        <div class="component-stat-label">Warnings</div>
                        <div class="component-stat-value">${health.warnings || 0}</div>
                    </div>
                    <div class="component-stat">
                        <div class="component-stat-label">Critical</div>
                        <div class="component-stat-value" style="color: #f44336;">
                            ${health.critical_errors || 0}
                        </div>
                    </div>
                    <div class="component-stat">
                        <div class="component-stat-label">Last Error</div>
                        <div class="component-stat-value" style="font-size: 12px;">
                            ${health.last_hour_error_count ? formatTime(new Date()) : '-'}
                        </div>
                    </div>
                </div>
                <div style="font-size: 12px; padding: 10px; background: ${getStatusBg(health.status)}; border-radius: 5px; color: #333;">
                    ${capitalizeFirst(health.status)}
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html || '<div class="loading">No components found</div>';
}

/**
 * Load performance data
 */
async function loadPerformanceData() {
    try {
        const response = await fetch(`${API_BASE}/monitoring/performance/metrics?minutes=60`);
        const data = await response.json();
        
        currentData.performance = data;
        
        // Render performance stats
        renderPerformanceStats(data);
        
        // Update performance chart
        updatePerformanceChart(data);
        
    } catch (error) {
        console.error('Error loading performance:', error);
    }
}

/**
 * Render performance stats
 */
function renderPerformanceStats(data) {
    const container = document.getElementById('performanceStats');
    const opStats = data.operation_stats || {};
    
    let html = '';
    for (const [op, stats] of Object.entries(opStats).slice(0, 4)) {
        const opName = capitalizeFirst(op.replace(/_/g, ' '));
        
        html += `
            <div class="stat-card">
                <h3>${opName}</h3>
                <div style="margin: 15px 0;">
                    <div style="font-size: 18px; font-weight: 700; color: #333;">
                        ${stats.avg_time_ms?.toFixed(2) || 0}ms
                    </div>
                    <div style="font-size: 12px; color: #999;">
                        avg: ${stats.avg_time_ms?.toFixed(2) || 0}ms | 
                        p95: ${stats.max_time_ms?.toFixed(2) || 0}ms
                    </div>
                </div>
                <div style="font-size: 12px; color: #999;">
                    ${Math.round((stats.error_rate || 0) * 100)}% error rate
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html || '<div class="loading">No performance data</div>';
}

/**
 * Update error trend chart
 */
function updateErrorTrendChart(data) {
    const canvas = document.getElementById('errorTrendChart');
    if (!canvas) return;
    
    // Destroy existing chart
    if (charts.errorTrend) {
        charts.errorTrend.destroy();
    }
    
    // Create chart
    const ctx = canvas.getContext('2d');
    
    // Generate mock data (in production, would come from API)
    const labels = [];
    const errorData = [];
    
    for (let i = 59; i >= 0; i--) {
        const time = new Date();
        time.setMinutes(time.getMinutes() - i);
        labels.push(time.getHours() + ':' + String(time.getMinutes()).padStart(2, '0'));
        errorData.push(Math.floor(Math.random() * 20));
    }
    
    charts.errorTrend = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Errors',
                data: errorData,
                borderColor: '#f44336',
                backgroundColor: 'rgba(244, 67, 54, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 6,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#999' },
                    grid: { color: '#f0f0f0' }
                },
                x: {
                    ticks: { color: '#999' },
                    grid: { color: '#f0f0f0' }
                }
            }
        }
    });
}

/**
 * Update performance chart
 */
function updatePerformanceChart(data) {
    const canvas = document.getElementById('performanceChart');
    if (!canvas) return;
    
    if (charts.performance) {
        charts.performance.destroy();
    }
    
    const ctx = canvas.getContext('2d');
    
    const opStats = data.operation_stats || {};
    const labels = Object.keys(opStats).slice(0, 5)
        .map(op => capitalizeFirst(op.replace(/_/g, ' ')));
    const avgTimes = Object.values(opStats).slice(0, 5)
        .map(s => s.avg_time_ms || 0);
    const maxTimes = Object.values(opStats).slice(0, 5)
        .map(s => s.max_time_ms || 0);
    
    charts.performance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Average (ms)',
                    data: avgTimes,
                    backgroundColor: '#667eea',
                },
                {
                    label: 'Max (ms)',
                    data: maxTimes,
                    backgroundColor: '#764ba2',
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#666' }
                }
            },
            scales: {
                y: {
                    ticks: { color: '#999' },
                    grid: { color: '#f0f0f0' }
                },
                x: {
                    ticks: { color: '#999' },
                    grid: { color: '#f0f0f0' }
                }
            }
        }
    });
}

/**
 * Refresh all data
 */
function refreshData() {
    console.log('Refreshing data...');
    loadAllData();
}

/**
 * Setup auto-refresh
 */
function setupAutoRefresh() {
    autoRefreshTimer = setInterval(() => {
        if (autoRefreshEnabled) {
            loadAllData();
        }
    }, REFRESH_INTERVAL);
}

/**
 * Utility: Format time
 */
function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'now';
    if (diffMins < 60) return `${diffMins}m ago`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    
    return date.toLocaleString();
}

/**
 * Utility: Capitalize first letter
 */
function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Utility: Truncate string
 */
function truncate(str, length) {
    if (str && str.length > length) {
        return str.substring(0, length) + '...';
    }
    return str;
}

/**
 * Utility: Get status class
 */
function getStatusClass(components) {
    let hasError = false;
    let hasWarning = false;
    
    for (const health of Object.values(components || {})) {
        if (health.status === 'critical') return 'critical';
        if (health.status === 'degraded' || health.status === 'unhealthy') hasError = true;
        if (health.status === 'warning') hasWarning = true;
    }
    
    if (hasError) return 'warning';
    if (hasWarning) return 'warning';
    return 'healthy';
}

/**
 * Utility: Get system status
 */
function getSystemStatus(components) {
    const cls = getStatusClass(components);
    const statusMap = {
        'healthy': '✓ Healthy',
        'warning': '⚠ Warning',
        'critical': '✕ Critical'
    };
    return statusMap[cls] || 'Unknown';
}

/**
 * Utility: Get status background color
 */
function getStatusBg(status) {
    const bgMap = {
        'healthy': '#c8e6c9',
        'warning': '#ffe0b2',
        'unhealthy': '#ffccbc',
        'degraded': '#ffccbc',
        'critical': '#ffcdd2'
    };
    return bgMap[status] || '#f0f0f0';
}

/**
 * Show error message
 */
function showError(message) {
    console.error(message);
    // Could show a toast or modal here
}
