/**
 * Dashboard-specific JavaScript for Victoria 3 Game Tracker
 */

// Dashboard state
let dashboardState = {
    charts: {},
    refreshIntervals: {},
    lastUpdate: null
};

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeDashboard();
    setupEventHandlers();
    startAutoRefresh();
});

/**
 * Initialize the dashboard
 */
function initializeDashboard() {
    console.log('Initializing Victoria 3 Dashboard...');
    
    // Load initial data
    loadDashboardData();
    
    // Setup chart configurations
    setupChartDefaults();
    
    // Initialize tooltips
    initializeTooltips();
}

/**
 * Setup event handlers
 */
function setupEventHandlers() {
    // Metric selector changes
    const rankingMetric = document.getElementById('ranking-metric');
    if (rankingMetric) {
        rankingMetric.addEventListener('change', function() {
            loadTopCountries(this.value);
        });
    }
    
    const trendMetric = document.getElementById('trend-metric');
    if (trendMetric) {
        trendMetric.addEventListener('change', function() {
            loadTrends(this.value);
        });
    }
    
    // Refresh buttons
    document.addEventListener('click', function(e) {
        if (e.target.matches('[data-refresh]')) {
            const refreshType = e.target.getAttribute('data-refresh');
            handleRefresh(refreshType);
        }
    });
    
    // Window resize handler for charts
    window.addEventListener('resize', debounce(function() {
        resizeCharts();
    }, 250));
}

/**
 * Load all dashboard data
 */
function loadDashboardData() {
    loadStats();
    loadRecentSaves();
    loadTopCountries('gdp');
    loadTrends('gdp');
}

/**
 * Load dashboard statistics
 */
async function loadStats() {
    try {
        const data = await getStats();
        updateStatsCards(data);
    } catch (error) {
        console.error('Error loading stats:', error);
        showAlert('Failed to load statistics', 'danger');
    }
}

/**
 * Update statistics cards
 */
function updateStatsCards(data) {
    const elements = {
        'total-saves': data.database?.saves_count || 0,
        'total-countries': data.database?.countries_count || 0,
        'total-metrics': data.database?.countrymetrics_count || 0
    };
    
    // Update numeric values
    Object.entries(elements).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) {
            animateNumber(element, parseInt(element.textContent) || 0, value);
        }
    });
    
    // Update latest date
    const latestDateElement = document.getElementById('latest-date');
    if (latestDateElement && data.latest_save) {
        latestDateElement.textContent = formatGameDate(data.latest_save.in_game_date);
    }
}

/**
 * Load recent saves
 */
async function loadRecentSaves() {
    const loading = document.getElementById('recent-saves-loading');
    const list = document.getElementById('recent-saves-list');
    
    if (!loading || !list) return;
    
    try {
        loading.style.display = 'block';
        list.style.display = 'none';
        
        const data = await getSaves({ limit: 5 });
        
        let html = '';
        if (data.saves && data.saves.length > 0) {
            data.saves.forEach(save => {
                html += createSaveListItem(save);
            });
        } else {
            html = '<div class="text-muted text-center py-3">No saves processed yet</div>';
        }
        
        list.innerHTML = html;
        loading.style.display = 'none';
        list.style.display = 'block';
        
    } catch (error) {
        console.error('Error loading recent saves:', error);
        loading.style.display = 'none';
        list.innerHTML = '<div class="text-danger text-center py-3">Error loading saves</div>';
        list.style.display = 'block';
    }
}

/**
 * Create save list item HTML
 */
function createSaveListItem(save) {
    const fileSize = formatFileSize(save.file_size);
    const processingTime = save.processing_time_ms ? `${save.processing_time_ms}ms` : '-';
    
    return `
        <div class="d-flex justify-content-between align-items-center border-bottom py-2">
            <div>
                <div class="fw-bold">${save.filename}</div>
                <small class="text-muted">
                    ${formatGameDate(save.in_game_date)} • 
                    ${save.country_count} countries • 
                    ${fileSize}
                </small>
            </div>
            <div class="text-end">
                <small class="text-muted">
                    ${formatDate(save.saved_at)}<br>
                    <span class="badge bg-light text-dark">${processingTime}</span>
                </small>
            </div>
        </div>
    `;
}

/**
 * Load top countries for a metric
 */
async function loadTopCountries(metric = 'gdp') {
    const loading = document.getElementById('top-countries-loading');
    const list = document.getElementById('top-countries-list');
    
    if (!loading || !list) return;
    
    try {
        loading.style.display = 'block';
        list.style.display = 'none';
        
        const data = await getRankings(metric, { limit: 10 });
        
        let html = '';
        if (data.rankings && data.rankings.length > 0) {
            data.rankings.forEach((country, index) => {
                html += createCountryRankingItem(country, index, metric);
            });
        } else {
            html = '<div class="text-muted text-center py-3">No data available</div>';
        }
        
        list.innerHTML = html;
        loading.style.display = 'none';
        list.style.display = 'block';
        
    } catch (error) {
        console.error('Error loading top countries:', error);
        loading.style.display = 'none';
        list.innerHTML = '<div class="text-danger text-center py-3">Error loading rankings</div>';
        list.style.display = 'block';
    }
}

/**
 * Create country ranking item HTML
 */
function createCountryRankingItem(country, index, metric) {
    const badgeClasses = ['bg-warning', 'bg-secondary', 'bg-info'];
    const badgeClass = index < 3 ? badgeClasses[index] : 'bg-light text-dark';
    const metricIcon = getMetricIcon(metric);
    
    return `
        <div class="d-flex justify-content-between align-items-center py-2">
            <div class="d-flex align-items-center">
                <span class="badge ${badgeClass} me-2">${index + 1}</span>
                <div>
                    <div class="fw-bold">${country.name || country.country_tag}</div>
                    <small class="text-muted">${country.country_tag}</small>
                </div>
            </div>
            <div class="text-end">
                <div class="fw-bold">${formatNumber(country.amount)}</div>
                <small class="text-muted">${metricIcon}</small>
            </div>
        </div>
    `;
}

/**
 * Load metric trends
 */
async function loadTrends(metric = 'gdp') {
    try {
        const data = await getTrends(metric, { countries: 5, points: 20 });
        updateTrendsChart(data);
    } catch (error) {
        console.error('Error loading trends:', error);
        showAlert('Failed to load trend data', 'danger');
    }
}

/**
 * Update trends chart
 */
function updateTrendsChart(data) {
    const canvas = document.getElementById('trends-chart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    
    // Destroy existing chart
    if (dashboardState.charts.trends) {
        dashboardState.charts.trends.destroy();
    }
    
    const datasets = [];
    const colors = [
        '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
        '#FF9F40', '#FF6384', '#C9CBCF', '#4BC0C0', '#FF6384'
    ];
    
    let colorIndex = 0;
    for (const [countryTag, countryData] of Object.entries(data.trends || {})) {
        if (countryData.data && countryData.data.length > 0) {
            datasets.push({
                label: countryData.name || countryTag,
                data: countryData.data.map(point => ({
                    x: point.date,
                    y: point.value
                })),
                borderColor: colors[colorIndex % colors.length],
                backgroundColor: colors[colorIndex % colors.length] + '20',
                fill: false,
                tension: 0.1,
                pointRadius: 3,
                pointHoverRadius: 5
            });
            colorIndex++;
        }
    }
    
    dashboardState.charts.trends = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        parser: 'yyyy-MM-dd',
                        displayFormats: {
                            day: 'MMM dd',
                            month: 'MMM yyyy'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Date'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: (data.metric_name || 'Value').toUpperCase()
                    },
                    ticks: {
                        callback: function(value) {
                            return formatNumber(value);
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${formatNumber(context.parsed.y)}`;
                        }
                    }
                }
            }
        }
    });
}

/**
 * Setup Chart.js defaults
 */
function setupChartDefaults() {
    Chart.defaults.font.family = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";
    Chart.defaults.color = '#666';
    Chart.defaults.borderColor = '#e0e0e0';
}

/**
 * Initialize Bootstrap tooltips
 */
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

/**
 * Handle refresh actions
 */
function handleRefresh(type) {
    switch (type) {
        case 'stats':
            loadStats();
            break;
        case 'saves':
            loadRecentSaves();
            break;
        case 'countries':
            const metric = document.getElementById('ranking-metric')?.value || 'gdp';
            loadTopCountries(metric);
            break;
        case 'trends':
            const trendMetric = document.getElementById('trend-metric')?.value || 'gdp';
            loadTrends(trendMetric);
            break;
        case 'all':
            loadDashboardData();
            break;
    }
}

/**
 * Start auto-refresh intervals
 */
function startAutoRefresh() {
    // Refresh stats every 30 seconds
    dashboardState.refreshIntervals.stats = setInterval(() => {
        loadStats();
    }, 30000);
    
    // Refresh recent saves every 60 seconds
    dashboardState.refreshIntervals.saves = setInterval(() => {
        loadRecentSaves();
    }, 60000);
}

/**
 * Stop auto-refresh intervals
 */
function stopAutoRefresh() {
    Object.values(dashboardState.refreshIntervals).forEach(interval => {
        clearInterval(interval);
    });
    dashboardState.refreshIntervals = {};
}

/**
 * Resize charts on window resize
 */
function resizeCharts() {
    Object.values(dashboardState.charts).forEach(chart => {
        if (chart && typeof chart.resize === 'function') {
            chart.resize();
        }
    });
}

/**
 * Animate number changes
 */
function animateNumber(element, start, end, duration = 1000) {
    if (start === end) {
        element.textContent = end;
        return;
    }
    
    const range = end - start;
    const increment = range / (duration / 16); // 60fps
    let current = start;
    
    const timer = setInterval(() => {
        current += increment;
        
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        
        element.textContent = Math.floor(current);
    }, 16);
}

/**
 * Format file sizes
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/**
 * Get metric icon
 */
function getMetricIcon(metric) {
    const icons = {
        'gdp': '💰',
        'population': '👥',
        'prestige': '⭐',
        'military_size': '⚔️',
        'literacy': '📚',
        'weekly_income': '💵',
        'money_holding': '🏦'
    };
    
    return icons[metric] || '📊';
}

/**
 * Handle WebSocket events
 */
if (typeof addWebSocketHandler !== 'undefined') {
    // New save processed
    addWebSocketHandler('new_save', function(data) {
        console.log('New save processed:', data);
        
        // Add to activity feed
        addActivityItem(`New save processed: ${data.filename}`, 'success');
        
        // Refresh relevant sections
        setTimeout(() => {
            loadStats();
            loadRecentSaves();
        }, 1000);
    });
    
    // Processing status updates
    addWebSocketHandler('processing_status', function(data) {
        console.log('Processing status:', data);
        
        if (data.status === 'error') {
            addActivityItem(`Processing failed: ${data.filename || 'Unknown file'}`, 'danger');
        } else if (data.status === 'success') {
            addActivityItem(`Processing completed: ${data.filename || 'Unknown file'}`, 'success');
        } else if (data.status === 'processing') {
            addActivityItem(`Processing started: ${data.filename || 'Unknown file'}`, 'info');
        }
    });
    
    // Country updates
    addWebSocketHandler('country_update', function(data) {
        console.log('Country update:', data);
        addActivityItem(`Country data updated: ${data.country_tag || 'Unknown'}`, 'info');
    });
    
    // Metric updates
    addWebSocketHandler('metric_update', function(data) {
        console.log('Metric update:', data);
        addActivityItem(`Metric updated: ${data.metric_name || 'Unknown'}`, 'info');
    });
}

/**
 * Add activity item to feed
 */
function addActivityItem(message, type = 'info') {
    const feed = document.getElementById('activity-feed');
    if (!feed) return;
    
    const timestamp = new Date().toLocaleTimeString();
    
    const alertClass = {
        'success': 'alert-success',
        'danger': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    }[type] || 'alert-info';
    
    const item = document.createElement('div');
    item.className = `alert ${alertClass} alert-dismissible fade show mb-2`;
    item.innerHTML = `
        <div class="d-flex justify-content-between align-items-start">
            <div>
                <small class="text-muted">${timestamp}</small><br>
                ${message}
            </div>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    // Remove placeholder if it exists
    const placeholder = feed.querySelector('.text-muted.text-center');
    if (placeholder) {
        placeholder.remove();
    }
    
    feed.insertBefore(item, feed.firstChild);
    
    // Keep only last 10 items
    const items = feed.querySelectorAll('.alert');
    if (items.length > 10) {
        items[items.length - 1].remove();
    }
    
    // Auto-scroll to top
    feed.scrollTop = 0;
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    stopAutoRefresh();
    
    // Destroy charts
    Object.values(dashboardState.charts).forEach(chart => {
        if (chart && typeof chart.destroy === 'function') {
            chart.destroy();
        }
    });
});

// Export functions for global use
window.loadDashboardData = loadDashboardData;
window.loadStats = loadStats;
window.loadRecentSaves = loadRecentSaves;
window.loadTopCountries = loadTopCountries;
window.loadTrends = loadTrends;
window.addActivityItem = addActivityItem;