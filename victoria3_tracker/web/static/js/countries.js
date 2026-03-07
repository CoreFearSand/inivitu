/**
 * Countries-specific JavaScript for Victoria 3 Game Tracker
 */

// Country picker state
let _pickerData = [];
const _pickerSelected = new Set();

// Country detail state
let countryState = {
    charts: {},
    currentPlaythrough: null,
    refreshIntervals: {},
    lastUpdate: null
};

// Initialize country detail page when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (typeof window.countryData !== 'undefined') {
        initializeCountryDetail();
        setupEventHandlers();
        loadCountryData();
    }
});

/**
 * Initialize the country detail page
 */
function initializeCountryDetail() {
    console.log('Initializing Country Detail for:', window.countryData.tag);
    
    // Setup chart configurations
    setupChartDefaults();
    
    // Initialize tooltips
    initializeTooltips();
    
    // Load playthrough options
    loadPlaythroughOptions();
}

/**
 * Setup event handlers
 */
function setupEventHandlers() {
    // Playthrough selection change
    const playthroughSelect = document.getElementById('playthrough-select');
    if (playthroughSelect) {
        playthroughSelect.addEventListener('change', function() {
            countryState.currentPlaythrough = this.value;
            loadCountryData();
        });
    }
    
    // Metric selector changes
    const economicMetric = document.getElementById('economic-metric-select');
    if (economicMetric) {
        economicMetric.addEventListener('change', function() {
            loadEconomicChart(this.value);
        });
    }
    
    const socialMetric = document.getElementById('social-metric-select');
    if (socialMetric) {
        socialMetric.addEventListener('change', function() {
            loadSocialChart(this.value);
        });
    }
    
    const historyMetric = document.getElementById('history-metric-select');
    if (historyMetric) {
        historyMetric.addEventListener('change', function() {
            loadHistoryChart(this.value);
        });
    }
    
    const rankingsMetric = document.getElementById('rankings-metric-select');
    if (rankingsMetric) {
        rankingsMetric.addEventListener('change', function() {
            loadRankings(this.value);
        });
    }
    
    // Refresh and export buttons
    document.addEventListener('click', function(e) {
        if (e.target.matches('#refresh-data') || e.target.closest('#refresh-data')) {
            handleRefresh();
        }
        
        if (e.target.matches('#export-data') || e.target.closest('#export-data')) {
            handleExport();
        }
        
        if (e.target.matches('#compare-country') || e.target.closest('#compare-country')) {
            handleCompare();
        }

        if (e.target.matches('#run-comparison') || e.target.closest('#run-comparison')) {
            runComparison();
        }
    });
    
    // Tab change handlers
    document.addEventListener('shown.bs.tab', function(e) {
        const targetId = e.target.getAttribute('data-bs-target');
        handleTabChange(targetId);
    });
    
    // Window resize handler for charts
    window.addEventListener('resize', debounce(function() {
        resizeCharts();
    }, 250));
}

/**
 * Load playthrough options for the dropdown
 */
async function loadPlaythroughOptions() {
    const playthroughSelect = document.getElementById('playthrough-select');
    if (!playthroughSelect) return;
    
    try {
        const data = await getPlaythroughs();
        
        // Clear existing options except "All Playthroughs"
        playthroughSelect.innerHTML = '<option value="">All Playthroughs</option>';
        
        if (data.playthroughs && data.playthroughs.length > 0) {
            data.playthroughs.forEach(playthrough => {
                const option = document.createElement('option');
                option.value = playthrough.playthrough_id;
                option.textContent = `${playthrough.name} (${playthrough.start_date} - ${playthrough.end_date})`;
                playthroughSelect.appendChild(option);
            });
        }
        
    } catch (error) {
        console.error('Error loading playthrough options:', error);
        showAlert('Failed to load playthrough options', 'warning');
    }
}

/**
 * Load all country data
 */
function loadCountryData() {
    loadMetricsOverview();
    loadMetricsTable();
    loadEconomicChart('gdp');
    loadSocialChart('population');
    loadHistoryChart('gdp');
    loadRankings('gdp');
}

/**
 * Load metrics overview cards
 */
async function loadMetricsOverview() {
    try {
        const params = countryState.currentPlaythrough ? { playthrough_id: countryState.currentPlaythrough } : {};
        const data = await getCountryMetrics(window.countryData.tag, params);
        
        updateMetricsCards(data);
        
    } catch (error) {
        console.error('Error loading metrics overview:', error);
        showAlert('Failed to load metrics overview', 'danger');
    }
}

/**
 * Update metrics overview cards
 */
function updateMetricsCards(data) {
    const keyMetrics = ['gdp', 'population', 'prestige', 'military_size'];
    
    keyMetrics.forEach(metric => {
        const valueElement = document.getElementById(`metric-${metric}`);
        const changeElement = document.getElementById(`change-${metric}`);
        
        if (valueElement && data.metrics && data.metrics[metric]) {
            const metricData = data.metrics[metric];
            const latestValue = metricData.latest_value;
            const change = metricData.change_percent;
            
            // Update value
            valueElement.textContent = formatNumber(latestValue);
            
            // Update change indicator
            if (changeElement && change !== null && change !== undefined) {
                const changeText = change > 0 ? `+${change.toFixed(1)}%` : `${change.toFixed(1)}%`;
                changeElement.textContent = changeText;
                changeElement.className = `metric-change ${change >= 0 ? 'positive' : 'negative'}`;
            } else if (changeElement) {
                changeElement.textContent = '-';
                changeElement.className = 'metric-change';
            }
        } else if (valueElement) {
            valueElement.textContent = '-';
            if (changeElement) {
                changeElement.textContent = '-';
                changeElement.className = 'metric-change';
            }
        }
    });
}

/**
 * Load metrics table
 */
async function loadMetricsTable() {
    const tableBody = document.getElementById('metrics-table-body');
    if (!tableBody) return;
    
    try {
        showLoading(tableBody, 'Loading metrics...');
        
        const params = countryState.currentPlaythrough ? { playthrough_id: countryState.currentPlaythrough } : {};
        const data = await getCountryMetrics(window.countryData.tag, params);
        
        let html = '';
        if (data.metrics && Object.keys(data.metrics).length > 0) {
            Object.entries(data.metrics).forEach(([metric, metricData]) => {
                html += createMetricTableRow(metric, metricData);
            });
        } else {
            html = '<tr><td colspan="5" class="text-center text-muted">No metrics available</td></tr>';
        }
        
        tableBody.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading metrics table:', error);
        tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Error loading metrics</td></tr>';
    }
}

/**
 * Create metric table row HTML
 */
function createMetricTableRow(metric, metricData) {
    const metricName = metric.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    const value = formatNumber(metricData.latest_value);
    const change = metricData.change_percent;
    const date = formatGameDate(metricData.latest_date);
    const rank = metricData.rank || '-';
    
    let changeHtml = '-';
    if (change !== null && change !== undefined) {
        const changeText = change > 0 ? `+${change.toFixed(1)}%` : `${change.toFixed(1)}%`;
        const changeClass = change >= 0 ? 'text-success' : 'text-danger';
        changeHtml = `<span class="${changeClass}">${changeText}</span>`;
    }
    
    return `
        <tr>
            <td><strong>${metricName}</strong></td>
            <td>${value}</td>
            <td>${changeHtml}</td>
            <td>${date}</td>
            <td>${rank}</td>
        </tr>
    `;
}

/**
 * Load economic chart
 */
async function loadEconomicChart(metric = 'gdp') {
    const canvas = document.getElementById('economic-chart');
    if (!canvas) return;
    
    try {
        const params = countryState.currentPlaythrough ? { playthrough_id: countryState.currentPlaythrough } : {};
        const data = await getCountryMetrics(window.countryData.tag, { ...params, metric, history: true });
        
        updateChart('economic', data, metric);
        
    } catch (error) {
        console.error('Error loading economic chart:', error);
        showAlert('Failed to load economic chart', 'danger');
    }
}

/**
 * Load social chart
 */
async function loadSocialChart(metric = 'population') {
    const canvas = document.getElementById('social-chart');
    if (!canvas) return;
    
    try {
        const params = countryState.currentPlaythrough ? { playthrough_id: countryState.currentPlaythrough } : {};
        const data = await getCountryMetrics(window.countryData.tag, { ...params, metric, history: true });
        
        updateChart('social', data, metric);
        
    } catch (error) {
        console.error('Error loading social chart:', error);
        showAlert('Failed to load social chart', 'danger');
    }
}

/**
 * Load history chart
 */
async function loadHistoryChart(metric = 'gdp') {
    const canvas = document.getElementById('history-chart');
    if (!canvas) return;
    
    try {
        const params = countryState.currentPlaythrough ? { playthrough_id: countryState.currentPlaythrough } : {};
        const data = await getCountryMetrics(window.countryData.tag, { ...params, metric, history: true });
        
        updateChart('history', data, metric);
        
    } catch (error) {
        console.error('Error loading history chart:', error);
        showAlert('Failed to load history chart', 'danger');
    }
}

/**
 * Update chart with data
 */
function updateChart(chartType, data, metric) {
    const canvas = document.getElementById(`${chartType}-chart`);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    
    // Destroy existing chart
    if (countryState.charts[chartType]) {
        countryState.charts[chartType].destroy();
    }
    
    const chartData = [];
    if (data.history && data.history.length > 0) {
        data.history.forEach(point => {
            chartData.push({
                x: point.date,
                y: point.value
            });
        });
    }
    
    const metricName = metric.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    
    countryState.charts[chartType] = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: `${window.countryData.name} - ${metricName}`,
                data: chartData,
                borderColor: '#007bff',
                backgroundColor: '#007bff20',
                fill: true,
                tension: 0.1,
                pointRadius: 3,
                pointHoverRadius: 5
            }]
        },
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
                        text: metricName
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
 * Load rankings
 */
async function loadRankings(metric = 'gdp') {
    const tableBody = document.getElementById('rankings-table-body');
    if (!tableBody) return;
    
    try {
        showLoading(tableBody, 'Loading rankings...');
        
        const params = countryState.currentPlaythrough ? { playthrough_id: countryState.currentPlaythrough } : {};
        const data = await getRankings(metric, params);
        
        let html = '';
        if (data.rankings && data.rankings.length > 0) {
            const currentCountryRank = data.rankings.findIndex(country => 
                country.country_tag === window.countryData.tag
            );
            
            data.rankings.forEach((country, index) => {
                const isCurrentCountry = country.country_tag === window.countryData.tag;
                html += createRankingTableRow(country, index, isCurrentCountry, currentCountryRank);
            });
        } else {
            html = '<tr><td colspan="4" class="text-center text-muted">No rankings available</td></tr>';
        }
        
        tableBody.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading rankings:', error);
        tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-danger">Error loading rankings</td></tr>';
    }
}

/**
 * Create ranking table row HTML
 */
function createRankingTableRow(country, index, isCurrentCountry, currentCountryRank) {
    const rank = index + 1;
    const name = getCountryName(country.country_tag);
    const value = formatNumber(country.amount);
    
    let difference = '-';
    if (currentCountryRank >= 0 && currentCountryRank !== index) {
        const currentCountryValue = country.amount; // This would need to be calculated properly
        // For now, just show rank difference
        const rankDiff = currentCountryRank - index;
        difference = rankDiff > 0 ? `+${rankDiff}` : `${rankDiff}`;
    }
    
    const rowClass = isCurrentCountry ? 'table-primary' : '';
    const badgeClass = rank <= 3 ? 'bg-warning' : 'bg-secondary';
    
    return `
        <tr class="${rowClass}">
            <td><span class="badge ${badgeClass}">${rank}</span></td>
            <td>
                <strong>${name}</strong>
                ${isCurrentCountry ? '<span class="badge bg-primary ms-2">You</span>' : ''}
                <br><small class="text-muted">${country.country_tag}</small>
            </td>
            <td>${value}</td>
            <td>${difference}</td>
        </tr>
    `;
}

/**
 * Handle tab changes
 */
function handleTabChange(targetId) {
    switch (targetId) {
        case '#metrics-pane':
            loadMetricsTable();
            break;
        case '#history-pane':
            const historyMetric = document.getElementById('history-metric-select')?.value || 'gdp';
            loadHistoryChart(historyMetric);
            break;
        case '#comparison-pane':
            loadComparisonData();
            break;
        case '#rankings-pane':
            const rankingsMetric = document.getElementById('rankings-metric-select')?.value || 'gdp';
            loadRankings(rankingsMetric);
            break;
    }
}

/**
 * Load comparison data — populates the searchable country picker
 */
async function loadComparisonData() {
    try {
        const data = await getCountries({ limit: 1000 });
        if (data.countries) {
            initCountryPicker(data.countries);
        }
    } catch (error) {
        console.error('Error loading comparison data:', error);
        showAlert('Failed to load comparison data', 'danger');
    }
}

// ── Searchable country picker ─────────────────────────────────────────────

function initCountryPicker(countries) {
    _pickerData = countries
        .filter(c => c.country_tag !== window.countryData.tag)
        .map(c => ({ tag: c.country_tag, name: c.name || c.country_tag, flagUrl: c.flag_url || '', flagUrlAlt: c.flag_url_alt || '' }))
        .sort((a, b) => a.name.localeCompare(b.name));
    _pickerSelected.clear();
    _syncHiddenSelect();
    _renderPickerChips();

    const input = document.getElementById('country-picker-input');
    const box   = document.getElementById('country-picker-box');
    const drop  = document.getElementById('country-picker-dropdown');
    if (!input || !box || !drop) return;

    input.addEventListener('focus', () => {
        _renderPickerDropdown(input.value);
        drop.style.display = '';
    });
    input.addEventListener('input', () => {
        _renderPickerDropdown(input.value);
        drop.style.display = '';
    });
    box.addEventListener('click', () => input.focus());

    // Close dropdown when clicking outside
    document.addEventListener('mousedown', function pickerClose(e) {
        const wrapper = document.getElementById('country-picker-box')?.parentElement;
        if (wrapper && !wrapper.contains(e.target)) {
            drop.style.display = 'none';
        }
    });
}

function _renderPickerChips() {
    const box   = document.getElementById('country-picker-box');
    const input = document.getElementById('country-picker-input');
    if (!box || !input) return;

    box.querySelectorAll('.picker-chip').forEach(el => el.remove());

    _pickerSelected.forEach(tag => {
        const entry = _pickerData.find(p => p.tag === tag);
        const flagHtml = entry?.flagUrl
            ? `<img src="${entry.flagUrl}" data-alt="${entry.flagUrlAlt || ''}" style="width:16px;height:11px;object-fit:cover;border-radius:1px;flex-shrink:0;" onerror="var a=this.dataset.alt;if(a){this.src=a;this.dataset.alt=''}else{this.style.display='none'}">`
            : '';
        const chip = document.createElement('span');
        chip.className = 'picker-chip badge bg-primary d-inline-flex align-items-center gap-1';
        chip.style.cssText = 'font-size: 0.75rem; cursor: default; user-select: none;';
        chip.innerHTML = `${flagHtml}${getCountryName(tag)} <span data-tag="${tag}" style="cursor:pointer; opacity:.8; font-size:.9em;">&times;</span>`;
        chip.querySelector('span').addEventListener('mousedown', e => {
            e.preventDefault();
            _togglePickerTag(tag);
        });
        box.insertBefore(chip, input);
    });
}

function _renderPickerDropdown(filter) {
    const drop = document.getElementById('country-picker-dropdown');
    if (!drop) return;

    const term = (filter || '').toLowerCase();
    const visible = _pickerData.filter(c =>
        c.name.toLowerCase().includes(term) || c.tag.toLowerCase().includes(term)
    );

    drop.innerHTML = '';
    if (visible.length === 0) {
        drop.innerHTML = '<div class="px-3 py-2 text-muted small">No countries found</div>';
        return;
    }

    visible.forEach(c => {
        const item = document.createElement('div');
        item.className = 'px-3 py-1 small d-flex align-items-center gap-2';
        item.style.cssText = 'cursor: pointer; user-select: none;';
        const checked = _pickerSelected.has(c.tag);
        const flagHtml = c.flagUrl
            ? `<img src="${c.flagUrl}" data-alt="${c.flagUrlAlt || ''}" style="width:20px;height:14px;object-fit:cover;border-radius:2px;flex-shrink:0;" onerror="var a=this.dataset.alt;if(a){this.src=a;this.dataset.alt=''}else{this.style.display='none'}">`
            : '<span style="width:20px;flex-shrink:0;"></span>';
        item.innerHTML = `<input type="checkbox" ${checked ? 'checked' : ''} style="pointer-events:none; flex-shrink:0;"> ${flagHtml} <span>${c.name}</span> <small class="text-muted ms-auto">${c.tag}</small>`;
        item.addEventListener('mousedown', e => {
            e.preventDefault();
            _togglePickerTag(c.tag);
        });
        item.addEventListener('mouseover', () => item.style.background = '#f8f9fa');
        item.addEventListener('mouseout',  () => item.style.background = '');
        drop.appendChild(item);
    });
}

function _togglePickerTag(tag) {
    if (_pickerSelected.has(tag)) {
        _pickerSelected.delete(tag);
    } else {
        _pickerSelected.add(tag);
    }
    _syncHiddenSelect();
    _renderPickerChips();
    const input = document.getElementById('country-picker-input');
    _renderPickerDropdown(input?.value || '');
}

function _syncHiddenSelect() {
    const select = document.getElementById('comparison-countries');
    if (!select) return;
    select.innerHTML = '';
    _pickerSelected.forEach(tag => {
        const opt = document.createElement('option');
        opt.value = tag;
        opt.selected = true;
        select.appendChild(opt);
    });
}

/**
 * Run comparison between selected countries
 */
async function runComparison() {
    const select = document.getElementById('comparison-countries');
    if (!select) return;

    const selectedTags = Array.from(select.selectedOptions).map(o => o.value);
    if (selectedTags.length === 0) {
        showAlert('Please select at least one country to compare', 'warning', 3000);
        return;
    }

    const metric = document.getElementById('comparison-metric-select')?.value || 'gdp';
    const allTags = [window.countryData.tag, ...selectedTags.filter(t => t !== window.countryData.tag)];

    const placeholder = document.getElementById('comparison-placeholder');
    const chartContainer = document.getElementById('comparison-chart-container');

    if (placeholder) placeholder.style.display = 'none';
    if (chartContainer) {
        chartContainer.style.display = '';
        chartContainer.innerHTML = '<div class="text-center py-4"><div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div></div>';
    }

    try {
        const response = await fetch('/api/compare/countries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ countries: allTags, metric, limit: 50 })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        renderComparisonChart(data, metric);

    } catch (error) {
        console.error('Error running comparison:', error);
        if (chartContainer) {
            chartContainer.innerHTML = '<div class="text-center text-danger py-4">Failed to load comparison data</div>';
        }
    }
}

/**
 * Render the comparison multi-line chart
 */
function renderComparisonChart(data, metric) {
    const chartContainer = document.getElementById('comparison-chart-container');
    if (!chartContainer) return;

    chartContainer.innerHTML = '<canvas id="comparison-chart"></canvas>';
    const canvas = document.getElementById('comparison-chart');
    const ctx = canvas.getContext('2d');

    if (countryState.charts['comparison']) {
        countryState.charts['comparison'].destroy();
    }

    const colors = ['#007bff', '#28a745', '#dc3545', '#ffc107', '#17a2b8', '#6f42c1', '#fd7e14', '#20c997', '#e83e8c', '#6c757d'];

    const datasets = Object.entries(data.data).map(([tag, records], i) => {
        const sorted = [...records].reverse();
        const points = sorted.map(r => ({ x: r.in_game_date || r.recorded_at, y: r.amount }));
        return {
            label: getCountryName(tag),
            data: points,
            borderColor: colors[i % colors.length],
            backgroundColor: colors[i % colors.length] + '20',
            fill: false,
            tension: 0.1,
            pointRadius: 2,
            pointHoverRadius: 4
        };
    });

    const metricName = metric.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

    countryState.charts['comparison'] = new Chart(ctx, {
        type: 'line',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        parser: 'yyyy-MM-dd',
                        displayFormats: { day: 'MMM dd', month: 'MMM yyyy' }
                    },
                    title: { display: true, text: 'Date' }
                },
                y: {
                    title: { display: true, text: metricName },
                    ticks: { callback: v => formatNumber(v) }
                }
            },
            plugins: {
                legend: { display: true, position: 'top' },
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)}`
                    }
                }
            }
        }
    });
}

/**
 * Handle refresh action
 */
function handleRefresh() {
    loadCountryData();
    showAlert('Data refreshed successfully', 'success', 3000);
}

/**
 * Handle export action
 */
function handleExport() {
    // Implement export functionality
    showAlert('Export functionality coming soon', 'info', 3000);
}

/**
 * Handle compare action
 */
function handleCompare() {
    // Switch to comparison tab
    const comparisonTab = document.getElementById('comparison-tab');
    if (comparisonTab) {
        const tab = new bootstrap.Tab(comparisonTab);
        tab.show();
    }
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
 * Resize charts on window resize
 */
function resizeCharts() {
    Object.values(countryState.charts).forEach(chart => {
        if (chart && typeof chart.resize === 'function') {
            chart.resize();
        }
    });
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    // Stop any refresh intervals
    Object.values(countryState.refreshIntervals).forEach(interval => {
        clearInterval(interval);
    });
    
    // Destroy charts
    Object.values(countryState.charts).forEach(chart => {
        if (chart && typeof chart.destroy === 'function') {
            chart.destroy();
        }
    });
});

// Export functions for global use
window.loadCountryData = loadCountryData;
window.loadMetricsOverview = loadMetricsOverview;
window.loadMetricsTable = loadMetricsTable;
window.loadEconomicChart = loadEconomicChart;
window.loadSocialChart = loadSocialChart;
window.loadHistoryChart = loadHistoryChart;
window.loadRankings = loadRankings;
window.loadPlaythroughOptions = loadPlaythroughOptions;
window.runComparison = runComparison;
window.renderComparisonChart = renderComparisonChart;