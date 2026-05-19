/**
 * Data export functionality for Victoria 3 Game Tracker
 */

/**
 * Export data to CSV format
 * @param {Array} data - Array of objects to export
 * @param {string} filename - Filename for the export
 * @param {Array} columns - Column definitions (optional)
 */
function exportToCSV(data, filename, columns = null) {
    if (!data || data.length === 0) {
        showAlert('No data to export', 'warning');
        return;
    }
    
    try {
        let csv = '';
        
        const cols = columns || Object.keys(data[0]);

        csv += cols.map(col => `"${col}"`).join(',') + '\n';

        data.forEach(row => {
            const values = cols.map(col => {
                let value = row[col];

                if (value === null || value === undefined) {
                    value = '';
                } else if (typeof value === 'object') {
                    value = JSON.stringify(value);
                } else {
                    value = String(value);
                }

                return `"${value.replace(/"/g, '""')}"`;
            });

            csv += values.join(',') + '\n';
        });

        downloadFile(csv, filename, 'text/csv');
        
        showAlert(`Exported ${data.length} records to ${filename}`, 'success');
        
    } catch (error) {
        console.error('Error exporting to CSV:', error);
        showAlert('Failed to export data', 'danger');
    }
}

/**
 * Export data to JSON format
 * @param {Array|Object} data - Data to export
 * @param {string} filename - Filename for the export
 */
function exportToJSON(data, filename) {
    if (!data) {
        showAlert('No data to export', 'warning');
        return;
    }
    
    try {
        const json = JSON.stringify(data, null, 2);
        downloadFile(json, filename, 'application/json');
        
        const count = Array.isArray(data) ? data.length : 1;
        showAlert(`Exported ${count} records to ${filename}`, 'success');
        
    } catch (error) {
        console.error('Error exporting to JSON:', error);
        showAlert('Failed to export data', 'danger');
    }
}

/**
 * Export chart data
 * @param {Chart} chart - Chart.js instance
 * @param {string} filename - Filename for the export
 * @param {string} format - Export format ('csv' or 'json')
 */
function exportChartData(chart, filename, format = 'csv') {
    if (!chart || !chart.data) {
        showAlert('No chart data to export', 'warning');
        return;
    }
    
    try {
        const chartData = chart.data;
        const datasets = chartData.datasets || [];
        const labels = chartData.labels || [];
        
        if (format === 'json') {
            exportToJSON({
                labels: labels,
                datasets: datasets.map(dataset => ({
                    label: dataset.label,
                    data: dataset.data
                }))
            }, filename);
        } else {
            const csvData = [];

            const header = ['Label'];
            datasets.forEach(dataset => {
                header.push(dataset.label || 'Dataset');
            });

            labels.forEach((label, index) => {
                const row = { Label: label };
                datasets.forEach(dataset => {
                    const dataPoint = dataset.data[index];
                    row[dataset.label || 'Dataset'] = typeof dataPoint === 'object' ? dataPoint.y : dataPoint;
                });
                csvData.push(row);
            });
            
            exportToCSV(csvData, filename, header);
        }
        
    } catch (error) {
        console.error('Error exporting chart data:', error);
        showAlert('Failed to export chart data', 'danger');
    }
}

/**
 * Export country rankings
 * @param {string} metric - Metric name
 * @param {string} format - Export format ('csv' or 'json')
 */
async function exportRankings(metric, format = 'csv') {
    try {
        showAlert('Preparing export...', 'info', 2000);
        
        const data = await getRankings(metric, { limit: 100 });
        
        if (!data.rankings || data.rankings.length === 0) {
            showAlert('No rankings data to export', 'warning');
            return;
        }
        
        const filename = `rankings_${metric}_${getCurrentDateString()}.${format}`;
        
        if (format === 'json') {
            exportToJSON({
                metric: metric,
                exported_at: new Date().toISOString(),
                rankings: data.rankings
            }, filename);
        } else {
            const csvData = data.rankings.map((country, index) => ({
                'Rank': index + 1,
                'Country Tag': country.country_tag,
                'Country Name': country.name || country.country_tag,
                'Value': country.amount,
                'Date': country.recorded_at
            }));
            
            exportToCSV(csvData, filename);
        }
        
    } catch (error) {
        console.error('Error exporting rankings:', error);
        showAlert('Failed to export rankings', 'danger');
    }
}

/**
 * Export country metrics
 * @param {string} countryTag - Country tag
 * @param {string} metric - Metric name (optional, exports all if not specified)
 * @param {string} format - Export format ('csv' or 'json')
 */
async function exportCountryMetrics(countryTag, metric = null, format = 'csv') {
    try {
        showAlert('Preparing export...', 'info', 2000);
        
        let data;
        if (metric) {
            data = await getCountryMetrics(countryTag, { metric: metric, limit: 1000 });
        } else {
            data = await getCountrySummary(countryTag);
        }
        
        if (!data || (data.metrics && data.metrics.length === 0)) {
            showAlert('No metrics data to export', 'warning');
            return;
        }
        
        const filename = `country_${countryTag}_${metric || 'all'}_${getCurrentDateString()}.${format}`;
        
        if (format === 'json') {
            exportToJSON({
                country_tag: countryTag,
                metric: metric,
                exported_at: new Date().toISOString(),
                data: data
            }, filename);
        } else {
            let csvData;
            
            if (metric) {
                csvData = data.metrics.map(entry => ({
                    'Country': countryTag,
                    'Metric': metric,
                    'Value': entry.amount,
                    'Date': entry.recorded_at,
                    'Game Date': entry.in_game_date
                }));
            } else {
                csvData = data.latest_metrics.map(entry => ({
                    'Country': countryTag,
                    'Metric': entry.metric_name,
                    'Display Name': entry.display_name,
                    'Value': entry.amount,
                    'Unit': entry.unit,
                    'Date': entry.recorded_at
                }));
            }
            
            exportToCSV(csvData, filename);
        }
        
    } catch (error) {
        console.error('Error exporting country metrics:', error);
        showAlert('Failed to export country metrics', 'danger');
    }
}

/**
 * Export processed saves list
 * @param {string} format - Export format ('csv' or 'json')
 */
async function exportSaves(format = 'csv') {
    try {
        showAlert('Preparing export...', 'info', 2000);
        
        const data = await getSaves({ limit: 1000 });
        
        if (!data.saves || data.saves.length === 0) {
            showAlert('No saves data to export', 'warning');
            return;
        }
        
        const filename = `saves_${getCurrentDateString()}.${format}`;
        
        if (format === 'json') {
            exportToJSON({
                exported_at: new Date().toISOString(),
                saves: data.saves
            }, filename);
        } else {
            const csvData = data.saves.map(save => ({
                'Filename': save.filename,
                'Save ID': save.save_id,
                'Game Date': save.in_game_date,
                'Countries': save.country_count,
                'Metrics': save.metric_count,
                'File Size (bytes)': save.file_size,
                'Processing Time (ms)': save.processing_time_ms,
                'Processed At': save.saved_at
            }));
            
            exportToCSV(csvData, filename);
        }
        
    } catch (error) {
        console.error('Error exporting saves:', error);
        showAlert('Failed to export saves', 'danger');
    }
}

/**
 * Export trend data
 * @param {string} metric - Metric name
 * @param {string} format - Export format ('csv' or 'json')
 */
async function exportTrends(metric, format = 'csv') {
    try {
        showAlert('Preparing export...', 'info', 2000);
        
        const data = await getTrends(metric, { countries: 20, points: 100 });
        
        if (!data.trends || Object.keys(data.trends).length === 0) {
            showAlert('No trend data to export', 'warning');
            return;
        }
        
        const filename = `trends_${metric}_${getCurrentDateString()}.${format}`;
        
        if (format === 'json') {
            exportToJSON({
                metric: metric,
                exported_at: new Date().toISOString(),
                trends: data.trends
            }, filename);
        } else {
            const csvData = [];
            
            Object.entries(data.trends).forEach(([countryTag, countryData]) => {
                countryData.data.forEach(point => {
                    csvData.push({
                        'Country Tag': countryTag,
                        'Country Name': countryData.name || countryTag,
                        'Metric': metric,
                        'Value': point.value,
                        'Date': point.date
                    });
                });
            });
            
            exportToCSV(csvData, filename);
        }
        
    } catch (error) {
        console.error('Error exporting trends:', error);
        showAlert('Failed to export trends', 'danger');
    }
}

/**
 * Download file to user's computer
 * @param {string} content - File content
 * @param {string} filename - Filename
 * @param {string} mimeType - MIME type
 */
function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = window.URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.style.display = 'none';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    window.URL.revokeObjectURL(url);
}

/**
 * Get current date string for filenames
 * @returns {string} Date string in YYYY-MM-DD format
 */
function getCurrentDateString() {
    const now = new Date();
    return now.toISOString().split('T')[0];
}

/**
 * Show export options modal
 * @param {string} dataType - Type of data to export
 * @param {Object} options - Export options
 */
function showExportModal(dataType, options = {}) {
    const modalHtml = `
        <div class="modal fade" id="exportModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Export ${dataType}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <label class="form-label">Format</label>
                            <div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="exportFormat" id="formatCSV" value="csv" checked>
                                    <label class="form-check-label" for="formatCSV">
                                        CSV (Comma Separated Values)
                                    </label>
                                </div>
                                <div class="form-check">
                                    <input class="form-check-input" type="radio" name="exportFormat" id="formatJSON" value="json">
                                    <label class="form-check-label" for="formatJSON">
                                        JSON (JavaScript Object Notation)
                                    </label>
                                </div>
                            </div>
                        </div>
                        
                        ${options.showMetricSelector ? `
                        <div class="mb-3">
                            <label class="form-label">Metric</label>
                            <select class="form-select" id="exportMetric">
                                <option value="gdp">GDP</option>
                                <option value="population">Population</option>
                                <option value="prestige">Prestige</option>
                                <option value="army_personnel">Army Personnel</option>
                                <option value="literacy">Literacy</option>
                                <option value="weekly_income">Weekly Income</option>
                            </select>
                        </div>
                        ` : ''}
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" onclick="executeExport('${dataType}', ${JSON.stringify(options).replace(/"/g, '&quot;')})">
                            <i class="fas fa-download"></i> Export
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    const existingModal = document.getElementById('exportModal');
    if (existingModal) {
        existingModal.remove();
    }

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = new bootstrap.Modal(document.getElementById('exportModal'));
    modal.show();
}

/**
 * Execute export based on modal selections
 * @param {string} dataType - Type of data to export
 * @param {Object} options - Export options
 */
function executeExport(dataType, options) {
    const format = document.querySelector('input[name="exportFormat"]:checked').value;
    const metric = document.getElementById('exportMetric')?.value;
    
    const modal = bootstrap.Modal.getInstance(document.getElementById('exportModal'));
    modal.hide();

    switch (dataType) {
        case 'rankings':
            exportRankings(metric || options.metric || 'gdp', format);
            break;
        case 'country':
            exportCountryMetrics(options.countryTag, metric, format);
            break;
        case 'saves':
            exportSaves(format);
            break;
        case 'trends':
            exportTrends(metric || options.metric || 'gdp', format);
            break;
        default:
            showAlert('Unknown export type', 'danger');
    }
}

window.exportToCSV = exportToCSV;
window.exportToJSON = exportToJSON;
window.exportChartData = exportChartData;
window.exportRankings = exportRankings;
window.exportCountryMetrics = exportCountryMetrics;
window.exportSaves = exportSaves;
window.exportTrends = exportTrends;
window.showExportModal = showExportModal;
window.executeExport = executeExport;