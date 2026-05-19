/**
 * API client for Victoria 3 Game Tracker
 */

const API_BASE_URL = window.location.origin;
const API_TIMEOUT = 10000; // 10 seconds

/**
 * Make an API request
 * @param {string} endpoint - API endpoint (e.g., '/api/countries')
 * @param {Object} options - Request options
 * @returns {Promise} - Promise that resolves to response data
 */
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        },
        timeout: API_TIMEOUT,
        ...options
    };
    
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), defaultOptions.timeout);
        
        const response = await fetch(url, {
            ...defaultOptions,
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        return data;
        
    } catch (error) {
        if (error.name === 'AbortError') {
            throw new Error('Request timeout');
        }
        throw error;
    }
}

/**
 * Get health status
 */
async function getHealth() {
    return apiRequest('/api/health');
}

/**
 * Get all countries
 * @param {Object} params - Query parameters
 */
async function getCountries(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const endpoint = `/api/countries${queryString ? '?' + queryString : ''}`;
    return apiRequest(endpoint);
}

/**
 * Get country metrics
 * @param {string} countryTag - Country tag (e.g., 'ENG')
 * @param {Object} params - Query parameters
 */
async function getCountryMetrics(countryTag, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const endpoint = `/api/countries/${countryTag}/metrics${queryString ? '?' + queryString : ''}`;
    return apiRequest(endpoint);
}

/**
 * Get country summary
 * @param {string} countryTag - Country tag
 */
async function getCountrySummary(countryTag) {
    return apiRequest(`/api/countries/${countryTag}/summary`);
}

/**
 * Get rankings for a metric
 * @param {string} metricName - Metric name
 * @param {Object} params - Query parameters
 */
async function getRankings(metricName, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const endpoint = `/api/rankings/${metricName}${queryString ? '?' + queryString : ''}`;
    return apiRequest(endpoint);
}

/**
 * Get metric trends
 * @param {string} metricName - Metric name
 * @param {Object} params - Query parameters
 */
async function getTrends(metricName, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const endpoint = `/api/trends/${metricName}${queryString ? '?' + queryString : ''}`;
    return apiRequest(endpoint);
}

/**
 * Compare countries
 * @param {Array} countries - Array of country tags
 * @param {string} metric - Metric to compare
 * @param {Object} options - Additional options
 */
async function compareCountries(countries, metric = 'gdp', options = {}) {
    return apiRequest('/api/compare/countries', {
        method: 'POST',
        body: JSON.stringify({
            countries,
            metric,
            ...options
        })
    });
}

/**
 * Search countries
 * @param {string} query - Search query
 * @param {Object} params - Query parameters
 */
async function searchCountries(query, params = {}) {
    const allParams = { q: query, ...params };
    const queryString = new URLSearchParams(allParams).toString();
    return apiRequest(`/api/search/countries?${queryString}`);
}

/**
 * Get available metrics
 */
async function getMetrics() {
    return apiRequest('/api/metrics');
}

/**
 * Get metric statistics
 * @param {string} metricName - Metric name
 * @param {Object} params - Query parameters
 */
async function getMetricStats(metricName, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const endpoint = `/api/metrics/${metricName}/stats${queryString ? '?' + queryString : ''}`;
    return apiRequest(endpoint);
}

/**
 * Get processed saves
 * @param {Object} params - Query parameters
 */
async function getSaves(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const endpoint = `/api/saves${queryString ? '?' + queryString : ''}`;
    return apiRequest(endpoint);
}

/**
 * Get application statistics
 */
async function getStats() {
    return apiRequest('/api/stats');
}

/**
 * Get available playthroughs/campaigns
 */
async function getPlaythroughs() {
    return apiRequest('/api/playthroughs');
}

/**
 * Get list of wars with optional filtering
 * @param {Object} params - { country, playthrough_id, status, limit }
 */
async function getWars(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return apiRequest(`/api/wars${qs ? '?' + qs : ''}`);
}

/**
 * Get detailed information about a specific war by its DB id
 * @param {number} warDbId - Wars.id (integer PK)
 */
async function getWarDetails(warDbId) {
    return apiRequest(`/api/wars/${warDbId}`);
}

/**
 * Get overall war statistics summary
 * @param {Object} params - { playthrough_id }
 */
async function getWarStatistics(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return apiRequest(`/api/wars/statistics${qs ? '?' + qs : ''}`);
}

/**
 * Get war timeline events
 * @param {Object} params - { playthrough_id, start_date, end_date, limit }
 */
async function getWarTimeline(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return apiRequest(`/api/wars/timeline${qs ? '?' + qs : ''}`);
}

/**
 * Get battles with optional filtering
 * @param {Object} params - { war_id, country, limit }
 */
async function getBattles(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return apiRequest(`/api/battles${qs ? '?' + qs : ''}`);
}

/**
 * Get war performance statistics for a country
 * @param {string} countryTag - 3-letter country tag
 * @param {Object} params - { playthrough_id }
 */
async function getCountryWarPerformance(countryTag, params = {}) {
    const qs = new URLSearchParams(params).toString();
    return apiRequest(`/api/countries/${countryTag}/war-performance${qs ? '?' + qs : ''}`);
}

/**
 * Format numbers for display
 * @param {number} value - Number to format
 * @param {Object} options - Formatting options
 */
function formatNumber(value, options = {}) {
    if (value === null || value === undefined) {
        return '-';
    }
    
    const defaults = {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
        notation: 'compact',
        compactDisplay: 'short'
    };
    
    const formatOptions = { ...defaults, ...options };
    
    try {
        return new Intl.NumberFormat('en-US', formatOptions).format(value);
    } catch (error) {
        return value.toString();
    }
}

/**
 * Format dates for display
 * @param {string} dateString - ISO date string
 * @param {Object} options - Formatting options
 */
function formatDate(dateString, options = {}) {
    if (!dateString) {
        return '-';
    }
    
    const defaults = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    
    const formatOptions = { ...defaults, ...options };
    
    try {
        const date = new Date(dateString);
        return new Intl.DateTimeFormat('en-US', formatOptions).format(date);
    } catch (error) {
        return dateString;
    }
}

/**
 * Format game dates (YYYY-MM-DD format)
 * @param {string} dateString - Game date string
 */
function formatGameDate(dateString) {
    if (!dateString) {
        return '-';
    }
    
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    } catch (error) {
        return dateString;
    }
}

/**
 * Show alert message
 * @param {string} message - Alert message
 * @param {string} type - Alert type (success, danger, warning, info)
 * @param {number} duration - Auto-dismiss duration in ms (0 = no auto-dismiss)
 */
function showAlert(message, type = 'info', duration = 5000) {
    const alertsContainer = document.getElementById('alerts-container');
    if (!alertsContainer) {
        console.warn('Alerts container not found');
        return;
    }
    
    const alertId = 'alert-' + Date.now();
    const alertHtml = `
        <div id="${alertId}" class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    alertsContainer.insertAdjacentHTML('beforeend', alertHtml);
    
    if (duration > 0) {
        setTimeout(() => {
            const alert = document.getElementById(alertId);
            if (alert) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        }, duration);
    }
}

/**
 * Show loading state
 * @param {HTMLElement} element - Element to show loading in
 * @param {string} message - Loading message
 */
function showLoading(element, message = 'Loading...') {
    if (!element) return;
    
    element.innerHTML = `
        <div class="text-center">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">${message}</span>
            </div>
            <div class="mt-2">${message}</div>
        </div>
    `;
}

/**
 * Hide loading state
 * @param {HTMLElement} element - Element to hide loading from
 */
function hideLoading(element) {
    if (!element) return;
    
    const spinner = element.querySelector('.spinner-border');
    if (spinner) {
        spinner.closest('.text-center').remove();
    }
}

/**
 * Debounce function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in ms
 * @param {boolean} immediate - Execute immediately
 */
function debounce(func, wait, immediate) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            timeout = null;
            if (!immediate) func(...args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func(...args);
    };
}

/**
 * Fetch a two-column Tag,Value CSV and populate targetMap.
 * First column (tag) is always upper-cased before storage.
 * An optional valueTransform function is applied to each value before storing
 * (e.g. toTitleCase for country names, identity for pre-cased adjectives).
 *
 * @param {string}   url            - URL of the CSV file to fetch
 * @param {Object}   targetMap      - Map to populate {TAG: value}
 * @param {Function} [valueTransform] - Optional transform for the value column
 * @returns {Promise<number>}  Number of entries loaded
 */
async function _loadCSVMap(url, targetMap, valueTransform = null) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const lines = (await r.text()).split('\n');
    let count = 0;
    for (let i = 1; i < lines.length; i++) {   // skip header row
        const line = lines[i].trim();
        if (!line) continue;
        const comma = line.indexOf(',');
        if (comma === -1) continue;
        const tag = line.substring(0, comma).trim().toUpperCase();
        const val = line.substring(comma + 1).trim();
        if (tag && val) {
            targetMap[tag] = valueTransform ? valueTransform(val) : val;
            count++;
        }
    }
    return count;
}

/**
 * Shared Victoria 3 country tag → English display name map.
 * Populated from /static/country_names.csv on first call to loadCountryNamesCSV().
 */
const V3CountryNames = {};
let _csvLoaded = false;

/** Capitalise the first letter of every word: "great britain" → "Great Britain". */
function toTitleCase(str) {
    return str.replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Return the English display name for a Victoria 3 country tag.
 * Falls back to the uppercased raw tag when no name is known.
 * @param {string} tag - 3-letter country tag (case-insensitive)
 */
function getCountryName(tag) {
    if (!tag) return '—';
    return V3CountryNames[tag.toUpperCase()] || tag.toUpperCase();
}

/**
 * Fetch /static/country_names.csv and populate V3CountryNames.
 * Idempotent — subsequent calls return immediately without re-fetching.
 */
async function loadCountryNamesCSV() {
    if (_csvLoaded) return;
    try {
        const count = await _loadCSVMap('/static/country_names.csv', V3CountryNames, toTitleCase);
        _csvLoaded = true;
        console.debug(`[V3] Loaded ${count} country names from CSV`);
    } catch (err) {
        console.warn('Could not load country_names.csv:', err);
    }
}

/**
 * Shared Victoria 3 country tag → war adjective map.
 * e.g.  GBR → "British",  RUS → "Russo",  CHI → "Sino"
 * Populated from /static/war_adjectives.csv on first call to loadWarAdjectivesCSV().
 */
const V3WarAdjectives = {};
let _warAdjCsvLoaded = false;

/**
 * Fetch /static/war_adjectives.csv and populate V3WarAdjectives.
 * Idempotent — subsequent calls return immediately without re-fetching.
 */
async function loadWarAdjectivesCSV() {
    if (_warAdjCsvLoaded) return;
    try {
        // No transform needed — adjectives are already correctly cased in the CSV
        const count = await _loadCSVMap('/static/war_adjectives.csv', V3WarAdjectives);
        _warAdjCsvLoaded = true;
        console.debug(`[V3] Loaded ${count} war adjectives from CSV`);
    } catch (err) {
        console.warn('Could not load war_adjectives.csv:', err);
    }
}

/**
 * Return the war-naming adjective for a country tag.
 * Priority: war_adjectives.csv → last word of full country name → raw tag.
 * @param {string} tag - 3-letter country tag (case-insensitive)
 */
function getWarAdjective(tag) {
    if (!tag) return 'Unknown';
    const upper = tag.toUpperCase();
    // Placeholder/rebellion tags (D00, D01, D02, ...) represent rebel movements
    // with no real adjective — treat as Unknown to trigger Revolution naming
    if (/^D\d+$/.test(upper)) return 'Unknown';
    if (V3WarAdjectives[upper]) return V3WarAdjectives[upper];
    // Fallback: last word of the country's full name
    const fullName = V3CountryNames[upper];
    if (fullName) {
        const words = fullName.trim().split(/\s+/);
        return words[words.length - 1];
    }
    return upper;   // final fallback: raw tag
}

/**
 * Convert a V3 strategic_region string into a human-readable place name.
 * e.g. "region_central_america" → "Central America"
 *
 * Kept as a dedicated function so future enhancements (custom region CSV,
 * abbreviation overrides, etc.) only require changes here.
 *
 * @param {string} regionStr - Raw region string from the API
 */
function formatRegion(regionStr) {
    if (!regionStr) return 'Unknown Region';
    return regionStr
        .replace(/^region_/, '')          // strip leading 'region_'
        .replace(/_/g, ' ')               // underscores → spaces
        .replace(/\b\w/g, c => c.toUpperCase()); // title-case
}

/**
 * Generate a historically-flavoured war name from a war object.
 *
 * The war object must contain (at minimum):
 *   war_type, started_on, strategic_region,
 *   main_attacker_tag, main_defender_tag,
 *   gp_attacker_tags  (comma-separated string or null),
 *   gp_defender_tags  (comma-separated string or null)
 *
 * @param {Object} war - War data object (from API or constructed manually)
 * @returns {string} Generated war name, e.g. "British-Russo War of 1840"
 */
function generateWarName(war) {
    const year = war.started_on ? war.started_on.substring(0, 4) : '????';
    const type = (war.war_type || 'unknown').toLowerCase();

    // Parse GP tag lists (API returns comma-separated strings)
    const gpAtt = war.gp_attacker_tags
        ? war.gp_attacker_tags.split(',').map(t => t.trim()).filter(Boolean)
        : [];
    const gpDef = war.gp_defender_tags
        ? war.gp_defender_tags.split(',').map(t => t.trim()).filter(Boolean)
        : [];

    /**
     * Build the display label for one side.
     * – If 2+ GPs: join all their adjectives with '-'  ("British-Franco")
     * – If 1 GP: use that GP's adjective
     * – Otherwise: use the main participant's adjective
     */
    function sideLabel(gpTags, mainTag) {
        if (gpTags.length >= 2) return gpTags.map(getWarAdjective).join('-');
        const tag = gpTags.length === 1 ? gpTags[0] : mainTag;
        return tag ? getWarAdjective(tag) : 'Unknown';
    }

    const att = sideLabel(gpAtt, war.main_attacker_tag);
    const def = sideLabel(gpDef, war.main_defender_tag);

    // For revolution/secession use the primary participant directly (not GP aggregation)
    const attMain = war.main_attacker_tag ? getWarAdjective(war.main_attacker_tag) : att;
    const defMain = war.main_defender_tag ? getWarAdjective(war.main_defender_tag) : def;

    // If both sides are unknown (e.g. Paradox wars with 0 participants),
    // fall back to a type+region+year label instead of "Unknown-Unknown War of YYYY"
    if (att === 'Unknown' && def === 'Unknown') {
        if (war.strategic_region) {
            return `Conflict over ${formatRegion(war.strategic_region)} (${year})`;
        }
        const typeLabel = type !== 'unknown' ? formatWarType(type) : 'Conflict';
        return `${typeLabel} of ${year}`;
    }

    switch (type) {
        case 'dp_independence':
            return `${att} War of Independence of ${year}`;
        case 'dp_return_state':
            return `War for ${formatRegion(war.strategic_region)} of ${year}`;
        case 'dp_annex':
            return `${att} Annexation of ${def} (${year})`;
        case 'dp_conquer':
            return `${att}-${def} Conquest War of ${year}`;
        case 'dp_humiliate':
            return `${att}-${def} Humiliation War of ${year}`;
        case 'dp_liberate':
            return `${att} Liberation War of ${year}`;
        case 'dp_open_market':
            return `${att} Trade War with ${def} of ${year}`;
        case 'dp_form_puppet':
        case 'dp_make_tributary':
            return `${att}-${def} Subjugation War of ${year}`;
        case 'dp_transfer_subject':
            return `War over ${def} of ${year}`;
        case 'dp_native_uprising':
            return `${att} Uprising of ${year}`;
        case 'revolution':
        case 'dp_revolution':
            // Use primary defender (not GP aggregation) — the gov't being challenged
            return `${defMain} Revolutionary War of ${year}`;
        case 'secession':
        case 'dp_secession':
            // Use primary attacker (not GP aggregation) — the seceding nation
            return `${attMain} War of Independence of ${year}`;
        default:
            // If the attacker is unidentified (e.g. a rebellion with no recorded tag),
            // treat it as a Revolutionary War against the primary defender government
            if (att === 'Unknown') return `${defMain} Revolutionary War of ${year}`;
            return `${att}-${def} War of ${year}`;
    }
}

/**
 * Bootstrap spinner wrapped in a centred div — use inside any container element.
 * @param {string} msg - Screen-reader label (default 'Loading…')
 */
function spinnerHTML(msg = 'Loading…') {
    return `
        <div class="text-center py-3">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">${msg}</span>
            </div>
        </div>`;
}

/**
 * Bootstrap spinner wrapped in a full-width table row — use inside <tbody>.
 * @param {number} colspan  - Number of columns the cell should span
 * @param {string} msg      - Screen-reader label (default 'Loading…')
 */
function tableSpinnerHTML(colspan, msg = 'Loading…') {
    return `
        <tr><td colspan="${colspan}" class="text-center py-3">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">${msg}</span>
            </div>
        </td></tr>`;
}

/**
 * Rank badge for top-N lists.
 *   index 0 → gold (bg-warning)
 *   index 1 → silver (bg-secondary)
 *   index 2 → bronze (bg-info)
 *   index 3+ → plain (bg-light text-dark)
 *
 * @param {number} index       - 0-based position
 * @param {string} extraClasses - Optional extra CSS classes (e.g. 'me-2')
 */
function rankBadge(index, extraClasses = '') {
    const cls = index === 0 ? 'bg-warning'
              : index === 1 ? 'bg-secondary'
              : index === 2 ? 'bg-info'
              : 'bg-light text-dark';
    const extra = extraClasses ? ' ' + extraClasses : '';
    return `<span class="badge ${cls}${extra}">${index + 1}</span>`;
}

/** Set Chart.js global font/colour defaults. Safe to call before charts exist. */
function setupChartDefaults() {
    if (typeof Chart === 'undefined') return;
    Chart.defaults.font.family = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";
    Chart.defaults.color       = '#666';
    Chart.defaults.borderColor = '#e0e0e0';
}

document.addEventListener('DOMContentLoaded', () => {
    loadCountryNamesCSV();
    loadWarAdjectivesCSV();
    setupChartDefaults();
});

window.apiRequest = apiRequest;
window.getHealth = getHealth;
window.getCountries = getCountries;
window.getCountryMetrics = getCountryMetrics;
window.getCountrySummary = getCountrySummary;
window.getRankings = getRankings;
window.getTrends = getTrends;
window.compareCountries = compareCountries;
window.searchCountries = searchCountries;
window.getMetrics = getMetrics;
window.getMetricStats = getMetricStats;
window.getSaves = getSaves;
window.getStats = getStats;
window.getPlaythroughs = getPlaythroughs;
window.formatNumber = formatNumber;
window.formatDate = formatDate;
window.formatGameDate = formatGameDate;
window.showAlert = showAlert;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
window.debounce = debounce;

window.V3CountryNames        = V3CountryNames;
window.toTitleCase           = toTitleCase;
window.getCountryName        = getCountryName;
window.loadCountryNamesCSV   = loadCountryNamesCSV;

window.V3WarAdjectives       = V3WarAdjectives;
window.loadWarAdjectivesCSV  = loadWarAdjectivesCSV;
window.getWarAdjective       = getWarAdjective;
window.formatRegion          = formatRegion;
window.generateWarName       = generateWarName;

window.spinnerHTML           = spinnerHTML;
window.tableSpinnerHTML      = tableSpinnerHTML;
window.rankBadge             = rankBadge;
window.setupChartDefaults    = setupChartDefaults;

window.getWars = getWars;
window.getWarDetails = getWarDetails;
window.getWarStatistics = getWarStatistics;
window.getWarTimeline = getWarTimeline;
window.getBattles = getBattles;
window.getCountryWarPerformance = getCountryWarPerformance;