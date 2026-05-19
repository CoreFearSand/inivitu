/**
 * Countries-specific JavaScript for Victoria 3 Game Tracker
 */

let _pickerData = [];
const _pickerSelected = new Set();

let countryState = {
    charts: {},
    currentPlaythrough: null,
    refreshIntervals: {},
    lastUpdate: null
};

// IG type → display name (module-level so chart functions can use it)
function fmtIgType(raw) {
    return (raw || '').replace(/^ig_/, '').replace(/_/g, ' ')
        .replace(/\w/g, c => c.toUpperCase());
}

const IG_COLORS = {
    ig_landowners:        '#7B4F9E',
    ig_rural_folk:        '#4CAF50',
    ig_devout:            '#00BCD4',
    ig_intelligentsia:    '#FFC107',
    ig_armed_forces:      '#795548',
    ig_industrialists:    '#FF8C00',
    ig_petty_bourgeoisie: '#2196F3',
    ig_trade_unions:      '#F44336',
};
function igColor(igType) { return IG_COLORS[igType] || '#888888'; }



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

    if (window.countryData.isGlobal) {
        ['interest-groups-tab', 'laws-tab'].forEach(function(id) {
            const el = document.getElementById(id);
            if (el) el.closest('li, .nav-item') ? el.closest('li, .nav-item').style.display = 'none' : el.style.display = 'none';
        });
    }

    setupChartDefaults();
    initializeTooltips();
    loadPlaythroughOptions();
}

/**
 * Setup event handlers
 */
function setupEventHandlers() {
    const playthroughSelect = document.getElementById('playthrough-select');
    if (playthroughSelect) {
        playthroughSelect.addEventListener('change', function() {
            countryState.currentPlaythrough = this.value;
            loadCountryData();
        });
    }
    
    const economicMetric = document.getElementById('economic-metric-select');
    if (economicMetric) {
        economicMetric.addEventListener('change', function() {
            loadEconomicChart(this.value);
        });
    }
    
    const socialMetric = document.getElementById('social-metric-select');
    if (socialMetric) {
        socialMetric.addEventListener('change', function() {
            if (this.value === 'ig_clout') loadIgChart('clout');
            else if (this.value === 'ig_approval') loadIgChart('approval');
            else loadSocialChart(this.value);
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
    
    document.addEventListener('click', function(e) {
        if (e.target.matches('#refresh-data') || e.target.closest('#refresh-data')) {
            handleRefresh();
        }
        
        if (e.target.matches('#compare-country') || e.target.closest('#compare-country')) {
            handleCompare();
        }

        if (e.target.matches('#run-comparison') || e.target.closest('#run-comparison')) {
            runComparison();
        }
    });
    
    document.addEventListener('shown.bs.tab', function(e) {
        const targetId = e.target.getAttribute('data-bs-target');
        handleTabChange(targetId);
    });
    
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
    const keyMetrics = ['gdp', 'population', 'prestige', 'army_personnel'];
    
    keyMetrics.forEach(metric => {
        const valueElement = document.getElementById(`metric-${metric}`);
        const changeElement = document.getElementById(`change-${metric}`);
        
        if (valueElement && data.metrics && data.metrics[metric]) {
            const metricData = data.metrics[metric];
            const latestValue = metricData.latest_value;
            const change = metricData.change_percent;
            
            valueElement.textContent = formatNumber(latestValue);

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
                if (metric.startsWith('ig_')) return;   // IG aggregates shown elsewhere
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
        const data = await getCountryMetrics(window.countryData.tag, { ...params, metric, limit: 500 });

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
        const data = await getCountryMetrics(window.countryData.tag, { ...params, metric, limit: 500 });

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
        const data = await getCountryMetrics(window.countryData.tag, { ...params, metric, limit: 500 });

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
    
    if (countryState.charts[chartType]) {
        countryState.charts[chartType].destroy();
    }
    
    // Use category scale so every save gets equal horizontal space regardless
    // of the real time gap between saves.  With type:'time' (proportional),
    // unevenly-spaced saves compress clustered points to one edge, making part
    // of the line invisible.
    const chartLabels = [];
    const chartValues = [];
    if (data.history && data.history.length > 0) {
        data.history.forEach(point => {
            if (point.date && point.value != null) {
                chartLabels.push(point.date);   // 'YYYY-MM-DD'
                chartValues.push(point.value);
            }
        });
    }

    const _METRIC_LABELS = { ig_avg_clout: 'Avg IG Clout', ig_avg_approval: 'Avg IG Approval' };
    const metricName = _METRIC_LABELS[metric] || metric.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

    countryState.charts[chartType] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartLabels,
            datasets: [{
                label: `${window.countryData.name} - ${metricName}`,
                data: chartValues,
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
                    // Category scale — equal spacing per save point.
                    title: {
                        display: true,
                        text: 'Date'
                    },
                    ticks: {
                        maxTicksLimit: 8,
                        maxRotation: 30,
                        // Show only YYYY-MM so labels don't crowd each other.
                        callback: function(val, index) {
                            const label = chartLabels[index];
                            return label ? label.slice(0, 7) : '';
                        }
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
                        // Show full date in tooltip title.
                        title: function(contexts) {
                            const idx = contexts[0]?.dataIndex;
                            return chartLabels[idx] || '';
                        },
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
 * Load rankings — always shows top 5, then current country if outside top 5.
 */
async function loadRankings(metric = 'gdp') {
    const tableBody = document.getElementById('rankings-table-body');
    if (!tableBody) return;

    try {
        showLoading(tableBody, 'Loading rankings...');

        // Fetch enough rows to find the current country's actual rank
        const params = countryState.currentPlaythrough ? { playthrough_id: countryState.currentPlaythrough } : {};
        params.limit = 1000;
        const data = await getRankings(metric, params);

        let html = '';
        if (data.rankings && data.rankings.length > 0) {
            const rankings = data.rankings;
            const currentIdx = rankings.findIndex(c => c.country_tag === window.countryData.tag);

            rankings.slice(0, 5).forEach((country, index) => {
                const isCurrent = country.country_tag === window.countryData.tag;
                html += createRankingTableRow(country, index, isCurrent);
            });

            if (currentIdx >= 5) {
                html += `<tr><td colspan="4" class="text-center text-muted py-1" style="letter-spacing:2px;">···</td></tr>`;
                html += createRankingTableRow(rankings[currentIdx], currentIdx, true);
            } else if (currentIdx === -1) {
                html += `<tr><td colspan="4" class="text-center text-muted"><small>Not ranked for this metric</small></td></tr>`;
            }
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
 * Create a single ranking table row.
 */
function createRankingTableRow(country, index, isCurrentCountry) {
    const rank  = index + 1;
    const name  = getCountryName(country.country_tag);
    const value = formatNumber(country.amount);
    const rowClass   = isCurrentCountry ? 'table-primary' : '';
    const badgeClass = rank === 1 ? 'bg-warning text-dark'
                     : rank === 2 ? 'bg-secondary'
                     : rank === 3 ? 'bg-info text-dark'
                     : 'bg-light text-dark';

    return `
        <tr class="${rowClass}">
            <td><span class="badge ${badgeClass}">${rank}</span></td>
            <td>
                <strong>${name}</strong>
                ${isCurrentCountry ? '<span class="badge bg-primary ms-2">You</span>' : ''}
                <br><small class="text-muted">${country.country_tag}</small>
            </td>
            <td>${value}</td>
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
        case '#interest-groups-pane':
            loadInterestGroups();
            break;
        case '#laws-pane':
            loadLawsTimeline();
            break;
    }
}

/**
 * Load interest groups for the current country
 */
async function loadInterestGroups() {
    const tableBody = document.getElementById('interest-groups-table-body');
    if (!tableBody) return;

    try {
        tableBody.innerHTML = `<tr><td colspan="5" class="text-center">
            <div class="spinner-border spinner-border-sm" role="status"></div> Loading…
        </td></tr>`;

        const params = {};
        if (countryState.currentPlaythrough) params.playthrough_id = countryState.currentPlaythrough;

        const url = `/api/countries/${window.countryData.tag}/interest_groups` +
            (Object.keys(params).length ? '?' + new URLSearchParams(params) : '');
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        const igs = data.interest_groups || [];
        if (!igs.length) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No interest group data available for this save.</td></tr>';
            return;
        }


        tableBody.innerHTML = igs.map(ig => {
            const govBadge = ig.in_government
                ? '<span class="badge bg-success">In Government</span>'
                : '<span class="badge bg-secondary">Opposition</span>';
            const approvalClass = ig.approval >= 0 ? 'text-success' : 'text-danger';
            const approvalStr = ig.approval >= 0
                ? `+${ig.approval.toFixed(1)}`
                : ig.approval.toFixed(1);
            return `<tr>
                <td><strong>${fmtIgType(ig.ig_type)}</strong><br>
                    <small class="text-muted">${ig.ig_type}</small></td>
                <td>${govBadge}</td>
                <td>${ig.clout != null ? (ig.clout * 100).toFixed(1) + '%' : '–'}</td>
                <td class="${approvalClass}">${approvalStr}</td>
                <td>${ig.membership != null ? ig.membership.toLocaleString() : '–'}</td>
            </tr>`;
        }).join('');

    } catch (error) {
        console.error('Error loading interest groups:', error);
        if (tableBody) {
            tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Failed to load interest group data.</td></tr>';
        }
    }
}

/**
 * Multi-line time-series chart of IG clout or approval across all saves.
 * One line per interest group, each colored with its canonical in-game color.
 */
async function loadIgChart(field) {
    const canvas = document.getElementById('social-chart');
    if (!canvas) return;

    try {
        const params = {};
        if (countryState.currentPlaythrough) params.playthrough_id = countryState.currentPlaythrough;
        const url = `/api/countries/${window.countryData.tag}/interest_groups/history` +
            (Object.keys(params).length ? '?' + new URLSearchParams(params) : '');
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        const series = data.series || {};
        if (!Object.keys(series).length) return;

        if (countryState.charts['social']) countryState.charts['social'].destroy();

        const isClout = field === 'clout';

        const datasets = Object.entries(series).map(([igType, points]) => {
            const color = igColor(igType);
            return {
                label: fmtIgType(igType),
                data: points.map(p => ({
                    x: p.date,
                    y: isClout ? p.clout * 100 : p.approval
                })),
                borderColor: color,
                backgroundColor: color + '22',
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 5,
                tension: 0.3,
                fill: false,
            };
        });

        countryState.charts['social'] = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                clip: 0,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: {
                        type: 'time',
                        bounds: 'data',
                        time: {
                            parser: 'yyyy-MM-dd',
                            displayFormats: { year: 'yyyy', month: 'MMM yyyy' }
                        },
                        title: { display: false }
                    },
                    y: {
                        title: {
                            display: true,
                            text: isClout ? 'Political Clout (%)' : 'Approval'
                        },
                        ticks: {
                            callback: v => isClout ? v.toFixed(1) + '%' : (v >= 0 ? '+' : '') + v.toFixed(1)
                        }
                    }
                },
                plugins: {
                    legend: { position: 'right', labels: { boxWidth: 12 } },
                    tooltip: {
                        callbacks: {
                            label: ctx => {
                                const v = ctx.raw.y;
                                return isClout
                                    ? `${ctx.dataset.label}: ${v.toFixed(1)}%`
                                    : `${ctx.dataset.label}: ${v >= 0 ? '+' : ''}${v.toFixed(1)}`;
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error loading IG chart:', error);
    }
}


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
        const payload = { countries: allTags, metric, limit: 50 };
        if (countryState.currentPlaythrough) payload.playthrough_id = countryState.currentPlaythrough;

        const response = await fetch('/api/compare/countries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
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
            clip: 0,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: {
                    type: 'time',
                    bounds: 'data',
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
 * Handle compare action
 */
function handleCompare() {
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

window.addEventListener('beforeunload', function() {
    Object.values(countryState.refreshIntervals).forEach(interval => {
        clearInterval(interval);
    });

    Object.values(countryState.charts).forEach(chart => {
        if (chart && typeof chart.destroy === 'function') {
            chart.destroy();
        }
    });
});

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

/** State for the law timeline — reset when playthrough changes. */
let _lawState = {
    loaded: false,
    changes: [],      // all LawChange dicts from API
    byDate: {},       // date -> [LawChange]
    sortedDates: [],  // sorted unique activation dates
    startNum: 0,      // ms timestamp of first change
    endNum: 0,        // ms timestamp of last change
    steps: 1000,      // range input max
    currentDate: null,
    playthrough: null,
};

/**
 * Load law history from the API and render the timeline.
 * Called when the Laws tab becomes active.
 */
async function loadLawsTimeline() {
    const container = document.getElementById('laws-timeline-container');
    if (!container) return;

    if (_lawState.loaded && _lawState.playthrough !== countryState.currentPlaythrough) {
        _lawState.loaded = false;
    }
    if (_lawState.loaded) return;   // already rendered

    container.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2 text-muted">Loading law history...</p>
        </div>`;

    try {
        const params = {};
        if (countryState.currentPlaythrough) params.playthrough_id = countryState.currentPlaythrough;
        const url = '/api/countries/' + window.countryData.tag + '/laws/history' +
            (Object.keys(params).length ? '?' + new URLSearchParams(params) : '');
        const resp = await fetch(url);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();

        const changes = data.changes || [];
        if (!changes.length) {
            container.innerHTML = `
                <div class="text-center text-muted py-5">
                    <i class="fas fa-scroll fa-2x mb-3"></i>
                    <p>No law history found for this country.</p>
                </div>`;
            return;
        }

        // Re-derive group/label/color/category from live JS definitions so stale
        // DB values (from before a law was reclassified) never corrupt the display.
        if (typeof LAW_TO_GROUP !== 'undefined') {
            changes.forEach(function(c) {
                const liveGroup = LAW_TO_GROUP[c.law_key];
                if (liveGroup && LAW_GROUPS[liveGroup]) {
                    const def = LAW_GROUPS[liveGroup];
                    c.law_group   = liveGroup;
                    c.group_label = def.label;
                    c.group_color = def.color;
                    c.category    = def.category;
                }
                if (LAW_LABELS[c.law_key]) {
                    c.law_label = LAW_LABELS[c.law_key];
                }
            });
        }

        const byDate = {};
        changes.forEach(function(c) {
            if (!c.activation_date) return;
            if (!byDate[c.activation_date]) byDate[c.activation_date] = [];
            byDate[c.activation_date].push(c);
        });
        const sortedDates = Object.keys(byDate).sort();

        function toMs(d) { return new Date(d).getTime(); }
        const startNum = toMs(sortedDates[0]);
        const endNum   = toMs(sortedDates[sortedDates.length - 1]);

        _lawState = {
            loaded: true,
            playthrough: countryState.currentPlaythrough,
            changes: changes,
            unknownLawKeys: data.unknown_law_keys || [],
            byDate: byDate,
            sortedDates: sortedDates,
            startNum: startNum,
            endNum: endNum,
            steps: 1000,
            currentDate: sortedDates[sortedDates.length - 1],
        };

        _renderLawTimeline(container);

    } catch (err) {
        console.error('Error loading laws:', err);
        container.innerHTML = `
            <div class="text-center text-danger py-4">
                <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                <p>Failed to load law history.</p>
            </div>`;
    }
}

/** Build and insert the timeline HTML, then wire the scrubber. */
function _renderLawTimeline(container) {
    const byDate = _lawState.byDate;
    const sortedDates = _lawState.sortedDates;
    const startNum = _lawState.startNum;
    const endNum = _lawState.endNum;
    const steps = _lawState.steps;
    const currentDate = _lawState.currentDate;
    const totalMs = endNum - startNum;
    const startDate = sortedDates[0];
    const endDate   = sortedDates[sortedDates.length - 1];

    const markersHtml = sortedDates.map(function(d) {
        const list = byDate[d];
        const pct  = totalMs > 0 ? ((new Date(d).getTime() - startNum) / totalMs * 100) : 0;

        const MAX_DOTS = 5;
        let dotsHtml;
        if (list.length <= MAX_DOTS) {
            dotsHtml = list.map(function(c) {
                return '<div class="law-marker-dot" style="background:' + c.group_color + '" title="' + c.group_label + ': ' + c.law_label + '"></div>';
            }).join('');
        } else {
            const color = list[0].group_color;
            dotsHtml = '<div class="law-marker-count" style="background:' + color + '">' + list.length + '</div>';
        }

        const tooltipText = list.map(function(c) { return c.group_label + ': ' + c.law_label; }).join('&#10;');
        return '<div class="law-marker" style="left:' + pct.toFixed(2) + '%" title="' + d + '&#10;' + tooltipText + '" data-date="' + d + '"><div class="law-marker-stack">' + dotsHtml + '</div></div>';
    }).join('');

    const currentMs = new Date(currentDate).getTime();
    const initialVal = totalMs > 0 ? Math.round((currentMs - startNum) / totalMs * steps) : steps;

    const unknownKeys = _lawState.unknownLawKeys || [];
    const unknownBannerHtml = unknownKeys.length
        ? '<div class="alert alert-warning d-flex gap-2 align-items-start mb-3" role="alert">' +
          '<i class="fas fa-puzzle-piece mt-1 flex-shrink-0"></i>' +
          '<div>' +
          '<strong>Unknown mod law' + (unknownKeys.length > 1 ? 's' : '') + ' detected</strong><br>' +
          'The following law ' + (unknownKeys.length > 1 ? 'keys are' : 'key is') + ' not in the built-in definitions:<br>' +
          '<code>' + unknownKeys.join('</code>, <code>') + '</code><br>' +
          '<small class="text-muted">To map ' + (unknownKeys.length > 1 ? 'them' : 'it') + ' to the correct group, add ' +
          (unknownKeys.length > 1 ? 'entries' : 'an entry') + ' to <code>victoria3_tracker/user_law_mods.json</code> and restart the app.</small>' +
          '</div></div>'
        : '';

    container.innerHTML =
        unknownBannerHtml +
        '<div class="mb-3">' +
        '<div class="d-flex justify-content-between align-items-center mb-1">' +
        '<small class="text-muted">' + startDate + '</small>' +
        '<span class="badge bg-primary fs-6" id="law-current-date">' + currentDate + '</span>' +
        '<small class="text-muted">' + endDate + '</small>' +
        '</div>' +
        '<div class="law-timeline-wrap">' +
        '<div class="law-timeline-track"><div class="law-markers-layer">' + markersHtml + '</div></div>' +
        '<input type="range" class="law-timeline-scrubber form-range" id="law-scrubber" min="0" max="' + steps + '" value="' + initialVal + '" step="1">' +
        '</div></div>' +
        '<hr class="my-2">' +
        '<div id="law-state-panel"></div>';

    document.getElementById('law-scrubber').addEventListener('input', function() {
        const frac = parseInt(this.value, 10) / steps;
        const ms   = startNum + frac * totalMs;
        const snapDate = _snapDate(ms);
        _lawState.currentDate = snapDate;
        document.getElementById('law-current-date').textContent = snapDate;
        _renderLawState();
    });

    _renderLawState();
}

/**
 * Find the closest date in sortedDates that is <= the given timestamp.
 */
function _snapDate(ms) {
    const sortedDates = _lawState.sortedDates;
    if (!sortedDates.length) return new Date(ms).toISOString().slice(0, 10);
    let best = sortedDates[0];
    for (let i = 0; i < sortedDates.length; i++) {
        const d = sortedDates[i];
        if (new Date(d).getTime() <= ms) best = d;
        else break;
    }
    return best;
}

/**
 * Render the law-state panel showing the active law per group at
 * _lawState.currentDate.
 */
function _renderLawState() {
    const panel = document.getElementById('law-state-panel');
    if (!panel) return;

    const changes = _lawState.changes;
    const currentDate = _lawState.currentDate;

    // For each law group, find the most recent entry with activation_date <= currentDate.
    // Changes were already normalised against live LAW_GROUPS in loadLawsTimeline,
    // so c.law_group is always the current canonical group key.
    const activeByGroup = {};
    changes.forEach(function(c) {
        if (!c.activation_date || c.activation_date > currentDate) return;
        const existing = activeByGroup[c.law_group];
        if (!existing || c.activation_date > existing.activation_date) {
            activeByGroup[c.law_group] = c;
        }
    });

    const CATEGORY_ORDER = ['power_structure', 'economy', 'human_rights'];
    const catData = {
        power_structure: { label: 'Power Structure', icon: 'fa-landmark',      groups: [] },
        economy:         { label: 'Economy',          icon: 'fa-industry',      groups: [] },
        human_rights:    { label: 'Human Rights',     icon: 'fa-balance-scale', groups: [] },
    };

    for (const groupKey of Object.keys(LAW_GROUPS)) {
        const law = activeByGroup[groupKey];
        if (!law) continue;
        if (catData[law.category]) catData[law.category].groups.push(law);
    }

    let catHtml = '';
    CATEGORY_ORDER.forEach(function(catKey) {
        const cat = catData[catKey];
        if (!cat.groups.length) return;
        let groupHtml = '';
        cat.groups.forEach(function(g) {
            groupHtml += '<div class="law-entry">' +
                '<span class="law-group-label">' + g.group_label + '</span>' +
                '<span class="law-badge" style="background:' + g.group_color + '1A;border-color:' + g.group_color + ';color:' + g.group_color + '" title="' + g.law_key + '">' + g.law_label + '</span>' +
                '</div>';
        });
        catHtml += '<div>' +
            '<div class="law-category-header"><i class="fas ' + cat.icon + '"></i> ' + cat.label + '</div>' +
            '<div class="law-entries">' + groupHtml + '</div>' +
            '</div>';
    });

    panel.innerHTML = catHtml
        ? '<div class="law-state-grid">' + catHtml + '</div>'
        : '<p class="text-muted text-center">No laws recorded before ' + currentDate + '.</p>';
}
