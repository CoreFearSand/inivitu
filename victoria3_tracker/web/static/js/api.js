/**
 * API client for Victoria 3 Game Tracker
 */

// API Configuration
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

// Utility functions

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
    
    // Auto-dismiss if duration is set
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

// Export functions for use in other scripts
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