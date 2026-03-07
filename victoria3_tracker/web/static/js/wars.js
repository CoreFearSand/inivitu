/**
 * War Statistics JavaScript for Victoria 3 Game Tracker
 *
 * Handles all war-related UI: overview cards, charts, wars table,
 * battles table, timeline, country performance, and war detail modal.
 */

// ─── Flag URL cache (tag → {url, alt}) populated from /api/countries ─────────
const _warFlagUrls = {};

// ─── Page state ──────────────────────────────────────────────────────────────
const warsState = {
    charts: {},
    currentFilters: {
        playthrough_id: '',
        country: '',
        status: ''
    },
    // Cached data for client-side sorting
    warsData: [],
    battlesData: [],
    // Current sort for each table: col=null means no active sort (use API order)
    // First click on any column always sorts descending (highest first).
    warsSort:    { col: null, dir: 'desc' },
    battlesSort: { col: null, dir: 'desc' },
    // (country name lookup is handled by the shared V3CountryNames / getCountryName in api.js)
};

// ─── Colour palette shared between charts ────────────────────────────────────
const CHART_COLORS = [
    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
    '#FF9F40', '#C9CBCF', '#7CFC00', '#FF69B4', '#20B2AA'
];

// ─── Boot ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
    initWarsPage();
});

async function initWarsPage() {
    await loadCountryNamesCSV();   // Load static name map before everything else
    await loadPlaythroughs();
    await loadCountriesForFilter();
    setupEventHandlers();
    await loadAllWarData();
}

// ─── Filter dropdowns ─────────────────────────────────────────────────────────

async function loadPlaythroughs() {
    try {
        const data = await apiRequest('/api/playthroughs');
        const select = document.getElementById('playthrough-select');
        if (!select) return;

        (data.playthroughs || []).forEach(pt => {
            const opt = document.createElement('option');
            opt.value = pt.playthrough_id;
            opt.textContent = pt.playthrough_id;
            select.appendChild(opt);
        });
    } catch (err) {
        console.warn('Could not load playthroughs:', err);
    }
}

async function loadCountriesForFilter() {
    try {
        // Main filter: uses Countries table (countries with metric data)
        const data = await apiRequest('/api/countries?limit=1000');
        const countrySelect = document.getElementById('country-select');

        const countries = data.countries || [];
        countries.sort((a, b) => (a.name || a.country_tag).localeCompare(b.name || b.country_tag));

        // Populate flag URL cache for use in war/battle rows
        countries.forEach(c => {
            if (c.flag_url) {
                _warFlagUrls[c.country_tag.toUpperCase()] = {
                    url: c.flag_url,
                    alt: c.flag_url_alt || ''
                };
            }
        });

        countries.forEach(c => {
            const label = `${c.name || c.country_tag} (${c.country_tag})`;
            if (countrySelect) {
                const opt = document.createElement('option');
                opt.value = c.country_tag;
                opt.textContent = label;
                countrySelect.appendChild(opt);
            }
        });
    } catch (err) {
        console.warn('Could not load countries for filter:', err);
    }

    // Performance tab: sourced from WarParticipants — works even without metrics
    try {
        const perfSelect = document.getElementById('performance-country-select');
        if (!perfSelect) return;

        const warData = await apiRequest('/api/wars/participant-countries');
        const warCountries = warData.countries || [];

        warCountries.forEach(c => {
            // Only overwrite the CSV-sourced name if the DB has something better
            // (i.e. country_name is non-empty and different from the raw tag).
            const dbName = c.country_name;
            if (dbName && dbName.toUpperCase() !== c.country_tag.toUpperCase()) {
                V3CountryNames[c.country_tag.toUpperCase()] = dbName;
            }

            const opt = document.createElement('option');
            opt.value = c.country_tag;
            opt.textContent = getCountryName(c.country_tag);
            perfSelect.appendChild(opt);
        });

        if (warCountries.length === 0) {
            const opt = document.createElement('option');
            opt.disabled = true;
            opt.textContent = 'No war data yet';
            perfSelect.appendChild(opt);
        }
    } catch (err) {
        console.warn('Could not load war participant countries:', err);
    }
}

// ─── Event handlers ──────────────────────────────────────────────────────────

function setupEventHandlers() {
    document.getElementById('apply-filters')?.addEventListener('click', applyFilters);
    document.getElementById('refresh-data')?.addEventListener('click', loadAllWarData);
    document.getElementById('export-data')?.addEventListener('click', exportWarsCSV);

    document.getElementById('performance-country-select')?.addEventListener('change', function () {
        if (this.value) loadCountryPerformance(this.value);
    });

    // Lazy-load tab content on first show
    document.querySelectorAll('#war-tabs button[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', function (e) {
            const target = e.target.getAttribute('data-bs-target');
            if (target === '#battles-pane') loadBattles();
            if (target === '#timeline-pane') loadTimeline();
        });
    });

    // Sortable headers — wars table (pass state object directly, not a string key)
    setupTableSort('wars-table', warsState.warsSort, renderWarsTable);

    // Sortable headers — battles table
    setupTableSort('battles-table', warsState.battlesSort, renderBattlesTable);
}

function applyFilters() {
    warsState.currentFilters.playthrough_id =
        document.getElementById('playthrough-select')?.value || '';
    warsState.currentFilters.country =
        document.getElementById('country-select')?.value || '';
    warsState.currentFilters.status =
        document.getElementById('status-select')?.value || '';

    loadAllWarData();
}

// ─── Sort infrastructure ──────────────────────────────────────────────────────

/**
 * Bind sort handlers to every th[data-sort] inside a table using onclick.
 * Assigning onclick replaces any previous handler — calling this function
 * multiple times is safe because there is never more than one handler per TH.
 *
 * @param {string}   tableId     - id of the <table> element
 * @param {object}   sortState   - { col, dir } object to mutate (passed by ref)
 * @param {Function} renderFn    - called after state is updated to redraw the tbody
 */
function setupTableSort(tableId, sortState, renderFn) {
    const ths = document.querySelectorAll(`#${tableId} th[data-sort]`);

    ths.forEach(th => {
        th.onclick = function () {
            const col = this.dataset.sort;

            // Toggle if same column; otherwise start descending (highest first)
            if (sortState.col === col) {
                sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
            } else {
                sortState.col = col;
                sortState.dir = 'desc';
            }

            // Update all icons in this table
            ths.forEach(t => t.classList.remove('sort-asc', 'sort-desc'));
            this.classList.add(sortState.dir === 'asc' ? 'sort-asc' : 'sort-desc');

            renderFn();
        };
    });
}

/**
 * Restore sort icons after a data reload (e.g. filter apply / page load).
 * Called by loadWarsTable / loadBattles after data is cached.
 */
function updateSortIcons(tableId, activeCol, dir) {
    const table = document.getElementById(tableId);
    if (!table) return;

    table.querySelectorAll('th[data-sort]').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.sort === activeCol) {
            th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    });
}

/**
 * Sort an array of objects by a key.
 * Handles numbers, strings, null/undefined (nulls always last).
 */
function sortData(arr, col, dir) {
    return [...arr].sort((a, b) => {
        let va = a[col];
        let vb = b[col];

        // Nulls always go to the bottom regardless of direction
        if (va == null && vb == null) return 0;
        if (va == null) return 1;
        if (vb == null) return -1;

        // Numeric comparison
        if (typeof va === 'number' && typeof vb === 'number') {
            return dir === 'asc' ? va - vb : vb - va;
        }

        // String comparison
        va = String(va).toLowerCase();
        vb = String(vb).toLowerCase();
        if (va < vb) return dir === 'asc' ? -1 : 1;
        if (va > vb) return dir === 'asc' ?  1 : -1;
        return 0;
    });
}

// ─── Master load function ─────────────────────────────────────────────────────

async function loadAllWarData() {
    await Promise.all([
        loadWarStatsSummary(),
        loadWarsTable()
    ]);
}

// ─── Overview cards + charts ──────────────────────────────────────────────────

async function loadWarStatsSummary() {
    try {
        const params = buildFilterParams();
        const qs = new URLSearchParams(params).toString();
        const data = await apiRequest(`/api/wars/statistics${qs ? '?' + qs : ''}`);

        updateOverviewCards(data.overall_statistics || {}, data.battle_statistics || {});
        renderCasualtyChart(data.most_active_countries || []);
        renderWarCostChart(data.most_active_countries || []);

    } catch (err) {
        console.error('Error loading war statistics summary:', err);
        showAlert('Failed to load war statistics', 'danger');
    }
}

function updateOverviewCards(stats, battleStats) {
    setText('total-wars',      stats.total_wars ?? '-');
    setText('ongoing-wars',    stats.ongoing_wars ?? '-');
    setText('total-casualties', formatCasualties(stats.total_casualties ?? 0));
    setText('total-battles',   battleStats.total_battles ?? '-');
}

function renderCasualtyChart(countries) {
    const canvas = document.getElementById('casualties-chart');
    if (!canvas) return;

    if (warsState.charts.casualties) warsState.charts.casualties.destroy();

    const top = countries.slice(0, 10);
    warsState.charts.casualties = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: top.map(c => getCountryName(c.country_tag)),
            datasets: [{
                label: 'Total Casualties',
                data: top.map(c => c.total_casualties || 0),
                backgroundColor: CHART_COLORS.slice(0, top.length)
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => `Casualties: ${formatCasualties(ctx.parsed.y)}`
                    }
                }
            },
            scales: {
                y: { beginAtZero: true, ticks: { callback: v => formatCasualties(v) } }
            }
        }
    });
}

function renderWarCostChart(countries) {
    const canvas = document.getElementById('war-costs-chart');
    if (!canvas) return;

    if (warsState.charts.warCosts) warsState.charts.warCosts.destroy();

    const top = countries.slice(0, 10);
    warsState.charts.warCosts = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: top.map(c => getCountryName(c.country_tag)),
            datasets: [{
                label: 'Total War Cost (£)',
                data: top.map(c => c.total_war_cost || 0),
                backgroundColor: CHART_COLORS.map(c => c + 'CC').slice(0, top.length)
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: { label: ctx => `Cost: £${formatNumber(ctx.parsed.y)}` }
                }
            },
            scales: {
                y: { beginAtZero: true, ticks: { callback: v => '£' + formatNumber(v) } }
            }
        }
    });
}

// ─── Wars table ───────────────────────────────────────────────────────────────

async function loadWarsTable() {
    const tbody = document.getElementById('wars-table-body');
    if (!tbody) return;

    tbody.innerHTML = tableSpinnerHTML(8);

    try {
        const params = buildFilterParams();
        params.limit = 100;
        const qs = new URLSearchParams(params).toString();
        const data = await apiRequest(`/api/wars?${qs}`);

        // Pre-compute derived sort key and cache
        warsState.warsData = (data.wars || []).map(w => ({
            ...w,
            _total_cost: (w.total_materiel_cost || 0) + (w.total_wage_cost || 0)
        }));

        // Restore sort icons if a column is already active (e.g. after filter re-apply)
        const ws = warsState.warsSort;
        if (ws.col) updateSortIcons('wars-table', ws.col, ws.dir);
        renderWarsTable();

    } catch (err) {
        console.error('Error loading wars:', err);
        tbody.innerHTML = '<tr><td colspan="8" class="text-danger text-center">Error loading wars</td></tr>';
    }
}

/** Sort cached wars data and rebuild the tbody. */
function renderWarsTable() {
    const tbody = document.getElementById('wars-table-body');
    if (!tbody) return;

    const { col, dir } = warsState.warsSort;
    // If no column is active yet, preserve the API's natural order
    const sorted = col ? sortData(warsState.warsData, col, dir) : [...warsState.warsData];

    if (sorted.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No wars found</td></tr>';
        return;
    }

    tbody.innerHTML = sorted.map(w => createWarRow(w)).join('');
    // onclick handlers are inlined in createWarRow — no extra binding needed
}

/**
 * Return a small flag <img> for a country tag, with two-step URL fallback.
 */
function warFlagImg(tag) {
    if (!tag) return '';
    const entry = _warFlagUrls[tag.toUpperCase()];
    const src    = entry?.url || '';
    const altSrc = entry?.alt || '';
    if (!src) return '';
    return `<img src="${src}" data-alt="${altSrc}" title="${getCountryName(tag)}"
                 style="width:20px;height:14px;object-fit:cover;border-radius:2px;border:1px solid #dee2e6;flex-shrink:0;vertical-align:middle;"
                 onerror="var a=this.dataset.alt;if(a){this.src=a;this.dataset.alt=''}else{this.style.display='none'}">`;
}

/**
 * Build the participants cell for a war row — attacker flags vs defender flags.
 * Falls back to the plain participant count if no tags are available.
 */
function participantFlags(w) {
    const attTags = [];
    if (w.main_attacker_tag) attTags.push(w.main_attacker_tag);
    if (w.gp_attacker_tags) {
        w.gp_attacker_tags.split(',').forEach(t => {
            const tag = t.trim();
            if (tag && tag !== w.main_attacker_tag) attTags.push(tag);
        });
    }

    const defTags = [];
    if (w.main_defender_tag) defTags.push(w.main_defender_tag);
    if (w.gp_defender_tags) {
        w.gp_defender_tags.split(',').forEach(t => {
            const tag = t.trim();
            if (tag && tag !== w.main_defender_tag) defTags.push(tag);
        });
    }

    if (!attTags.length && !defTags.length) return w.participant_count ?? '-';

    const attHtml = attTags.map(warFlagImg).join('');
    const defHtml = defTags.map(warFlagImg).join('');
    const shown   = attTags.length + defTags.length;
    const extra   = (w.participant_count || 0) - shown;

    return `<div class="d-flex align-items-center justify-content-center gap-1 flex-wrap">
        ${attHtml}
        <span class="text-muted" style="font-size:0.7rem;line-height:1;">vs</span>
        ${defHtml}
        ${extra > 0 ? `<span class="text-muted" style="font-size:0.7rem;">+${extra}</span>` : ''}
    </div>`;
}

function createWarRow(w) {
    const warLabel     = generateWarName(w);          // fancy generated name
    const rawType      = w.war_type || 'unknown';     // kept as subtitle
    const warDbId      = w.war_db_id || w.id || '';
    const casualties   = formatCasualties(w.total_casualties || 0);
    const cost         = '£' + formatNumber(w._total_cost || 0);
    const participants = participantFlags(w);
    const clickAttr    = warDbId ? `onclick="openWarModal(${warDbId})" style="cursor:pointer"` : '';

    return `
        <tr class="war-row" ${clickAttr}>
            <td>
                <span class="fw-bold">${warLabel}</span>
                <br><small class="text-muted">${rawType}</small>
                ${w.strategic_region ? `<br><small class="text-muted">📍 ${formatRegion(w.strategic_region)}</small>` : ''}
            </td>
            <td>${warStatusBadge(w.status)}</td>
            <td>${formatGameDate(w.started_on)}</td>
            <td>${w.ended_on ? formatGameDate(w.ended_on) : '<span class="text-muted">Ongoing</span>'}</td>
            <td class="text-center">${participants}</td>
            <td class="text-end">${casualties}</td>
            <td class="text-end">${cost}</td>
            <td>
                ${warDbId ? `<button class="btn btn-sm btn-outline-primary" onclick="event.stopPropagation(); openWarModal(${warDbId})">
                    <i class="fas fa-info-circle"></i> Details
                </button>` : ''}
            </td>
        </tr>`;
}

// ─── Battles table ────────────────────────────────────────────────────────────

async function loadBattles() {
    const tbody = document.getElementById('battles-table-body');
    if (!tbody) return;

    // Only fetch if we haven't cached data yet (or filters changed)
    if (warsState.battlesData.length === 0) {
        tbody.innerHTML = tableSpinnerHTML(8);

        try {
            const params = {};
            if (warsState.currentFilters.country) params.country = warsState.currentFilters.country;
            params.limit = 100;

            const qs = new URLSearchParams(params).toString();
            const data = await apiRequest(`/api/battles?${qs}`);

            // Pre-compute derived sort key
            warsState.battlesData = (data.battles || []).map(b => ({
                ...b,
                _total_casualties: (b.attacker_casualties || 0) + (b.defender_casualties || 0)
            }));

        } catch (err) {
            console.error('Error loading battles:', err);
            tbody.innerHTML = '<tr><td colspan="8" class="text-danger text-center">Error loading battles</td></tr>';
            return;
        }
    }

    const bs = warsState.battlesSort;
    if (bs.col) updateSortIcons('battles-table', bs.col, bs.dir);
    renderBattlesTable();
}

/** Sort cached battles data and rebuild the tbody. */
function renderBattlesTable() {
    const tbody = document.getElementById('battles-table-body');
    if (!tbody) return;

    const { col, dir } = warsState.battlesSort;
    // If no column is active yet, preserve the API's natural order
    const sorted = col ? sortData(warsState.battlesData, col, dir) : [...warsState.battlesData];

    if (sorted.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No battles recorded</td></tr>';
        return;
    }

    tbody.innerHTML = sorted.map(b => createBattleRow(b)).join('');
}

function createBattleRow(b) {
    const winner = b.winner_tag
        ? `${warFlagImg(b.winner_tag)}<span class="badge bg-success ms-1">${b.winner_tag}</span>`
        : '<span class="text-muted">—</span>';
    const warLabel = formatWarType(b.war_type);

    return `
        <tr>
            <td>${b.name || '<span class="text-muted">Unnamed</span>'}</td>
            <td>${formatGameDate(b.occurred_on)}</td>
            <td>${b.location_province_id || '—'}</td>
            <td>${warFlagImg(b.attacker_tag)}<span class="badge bg-danger ms-1">${b.attacker_tag}</span> (${b.attacker_casualties || 0})</td>
            <td>${warFlagImg(b.defender_tag)}<span class="badge bg-primary ms-1">${b.defender_tag}</span> (${b.defender_casualties || 0})</td>
            <td>${winner}</td>
            <td class="text-end">${formatCasualties(b._total_casualties || 0)}</td>
            <td><small class="text-muted">${warLabel}</small></td>
        </tr>`;
}

// ─── Timeline ─────────────────────────────────────────────────────────────────

async function loadTimeline() {
    const container = document.getElementById('war-timeline');
    if (!container) return;

    container.innerHTML = spinnerHTML();

    try {
        const params = buildFilterParams();
        params.limit = 200;
        const qs = new URLSearchParams(params).toString();
        const data = await apiRequest(`/api/wars/timeline?${qs}`);

        const events = data.timeline || [];
        if (events.length === 0) {
            container.innerHTML = '<div class="text-muted text-center py-4">No timeline events found</div>';
            return;
        }

        container.innerHTML = events.map(e => createTimelineItem(e)).join('');

    } catch (err) {
        console.error('Error loading timeline:', err);
        container.innerHTML = '<div class="text-danger text-center py-4">Error loading timeline</div>';
    }
}

function createTimelineItem(e) {
    const isStart  = e.event_type === 'war_start';
    const dotColor = isStart ? '#dc3545' : '#28a745';
    const icon     = isStart ? '⚔️ War Began' : '🏳️ War Ended';
    const warLabel = formatWarType(e.war_type);
    const cas = e.total_casualties > 0
        ? `<small class="text-muted"> · ${formatCasualties(e.total_casualties)} casualties</small>`
        : '';

    return `
        <div class="timeline-item" style="border-left-color: ${dotColor};">
            <div class="d-flex justify-content-between">
                <div>
                    <strong>${icon}</strong>
                    <span class="ms-2">${warLabel}</span>
                    ${cas}
                </div>
                <small class="text-muted">${formatGameDate(e.event_date)}</small>
            </div>
            <div>
                <small class="text-muted">
                    ${e.participant_count} participant(s)
                    · ${warStatusBadge(e.status)}
                </small>
            </div>
        </div>`;
}

// ─── Country performance ──────────────────────────────────────────────────────

async function loadCountryPerformance(countryTag) {
    const content = document.getElementById('performance-content');
    if (!content) return;

    content.innerHTML = spinnerHTML();

    try {
        const params = {};
        if (warsState.currentFilters.playthrough_id) {
            params.playthrough_id = warsState.currentFilters.playthrough_id;
        }
        const qs = new URLSearchParams(params).toString();
        const data = await apiRequest(
            `/api/countries/${countryTag}/war-performance${qs ? '?' + qs : ''}`
        );

        content.innerHTML = renderPerformancePanel(data);

    } catch (err) {
        console.error('Error loading performance:', err);
        content.innerHTML = '<div class="text-danger text-center py-4">Error loading performance data</div>';
    }
}

function renderPerformancePanel(data) {
    const p = data.performance || {};
    const recentWars = data.recent_wars || [];

    const winRate = p.battle_win_rate != null ? p.battle_win_rate.toFixed(1) + '%' : '—';

    const recentHtml = recentWars.length > 0
        ? recentWars.map(w => `
            <li class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                    <span class="fw-bold">${formatWarType(w.war_type)}</span>
                    ${w.side ? `<span class="badge ${w.side === 'attacker' ? 'bg-danger' : 'bg-primary'} ms-2">${w.side}</span>` : ''}
                    <br><small class="text-muted">${formatGameDate(w.started_on)}</small>
                </div>
                ${warStatusBadge(w.status)}
            </li>`).join('')
        : '<li class="list-group-item text-muted">No recent wars</li>';

    return `
        <div class="row g-3 mb-4">
            <div class="col-md-3">
                <div class="performance-metric">
                    <div class="fs-4 fw-bold">${p.total_wars || 0}</div>
                    <div class="text-muted small">Total Wars</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="performance-metric">
                    <div class="fs-4 fw-bold">${p.wars_as_attacker || 0} / ${p.wars_as_defender || 0}</div>
                    <div class="text-muted small">Attacker / Defender</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="performance-metric">
                    <div class="fs-4 fw-bold">${formatCasualties(p.total_casualties || 0)}</div>
                    <div class="text-muted small">Total Casualties</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="performance-metric">
                    <div class="fs-4 fw-bold">${winRate}</div>
                    <div class="text-muted small">Battle Win Rate</div>
                </div>
            </div>
        </div>

        <div class="row g-3 mb-4">
            <div class="col-md-4">
                <div class="performance-metric">
                    <div class="fs-5 fw-bold">${p.total_battles || 0}</div>
                    <div class="text-muted small">Battles Fought</div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="performance-metric">
                    <div class="fs-5 fw-bold">£${formatNumber(p.total_materiel_cost || 0)}</div>
                    <div class="text-muted small">Materiel Cost</div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="performance-metric">
                    <div class="fs-5 fw-bold">£${formatNumber(p.total_wage_cost || 0)}</div>
                    <div class="text-muted small">Wage Cost</div>
                </div>
            </div>
        </div>

        <h6 class="mt-3">Recent Wars</h6>
        <ul class="list-group list-group-flush">${recentHtml}</ul>`;
}

// ─── War detail modal ─────────────────────────────────────────────────────────

async function openWarModal(warDbId) {
    const modal = document.getElementById('war-details-modal');
    const title = document.getElementById('war-details-title');
    const body  = document.getElementById('war-details-body');
    if (!modal || !title || !body) return;

    body.innerHTML = spinnerHTML();

    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();

    try {
        const data      = await apiRequest(`/api/wars/${warDbId}`);
        const w         = data.war_info || {};
        const stats     = data.statistics || {};
        const attackers = data.participants?.attackers || [];
        const defenders = data.participants?.defenders || [];
        const battles   = data.battles || [];

        // Build a minimal war object for generateWarName() using participant data
        // (detail endpoint doesn't include prestige/GP fields, so we fall back to
        //  first attacker/defender by list order — good enough for the modal title)
        const nameObj = {
            war_type:          w.war_type,
            started_on:        w.started_on,
            strategic_region:  w.strategic_region,
            main_attacker_tag: attackers[0]?.country_tag || null,
            main_defender_tag: defenders[0]?.country_tag || null,
            gp_attacker_tags:  null,   // no prestige data in detail view
            gp_defender_tags:  null,
        };
        title.textContent = generateWarName(nameObj);

        body.innerHTML = `
            <div class="row mb-3">
                <div class="col-md-6">
                    <table class="table table-sm">
                        <tbody>
                            <tr><th>Type</th><td>${formatWarType(w.war_type)}</td></tr>
                            <tr><th>Status</th><td>${warStatusBadge(w.status)}</td></tr>
                            <tr><th>Started</th><td>${formatGameDate(w.started_on)}</td></tr>
                            <tr><th>Ended</th><td>${w.ended_on ? formatGameDate(w.ended_on) : '<em>Ongoing</em>'}</td></tr>
                            ${w.strategic_region ? `<tr><th>Region</th><td>${formatRegion(w.strategic_region)}</td></tr>` : ''}
                        </tbody>
                    </table>
                </div>
                <div class="col-md-6">
                    <div class="row text-center g-2">
                        <div class="col-6">
                            <div class="border rounded p-2">
                                <div class="fs-5 fw-bold">${stats.total_participants || 0}</div>
                                <div class="text-muted small">Participants</div>
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="border rounded p-2">
                                <div class="fs-5 fw-bold">${formatCasualties(stats.total_casualties || 0)}</div>
                                <div class="text-muted small">Casualties</div>
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="border rounded p-2">
                                <div class="fs-5 fw-bold">£${formatNumber(stats.total_war_cost || 0)}</div>
                                <div class="text-muted small">War Cost</div>
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="border rounded p-2">
                                <div class="fs-5 fw-bold">${stats.total_battles || 0}</div>
                                <div class="text-muted small">Battles</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="row">
                <div class="col-md-6">
                    <h6 class="text-danger">⚔️ Attackers</h6>
                    ${renderParticipantList(attackers)}
                </div>
                <div class="col-md-6">
                    <h6 class="text-primary">🛡️ Defenders</h6>
                    ${renderParticipantList(defenders)}
                </div>
            </div>

            ${battles.length > 0 ? `
            <hr>
            <h6>Battles</h6>
            <div class="table-responsive">
                <table class="table table-sm table-striped">
                    <thead>
                        <tr>
                            <th>Name</th><th>Date</th><th>Attacker</th>
                            <th>Defender</th><th>Winner</th><th>Casualties</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${battles.map(b => `
                        <tr>
                            <td>${b.name || '—'}</td>
                            <td>${formatGameDate(b.occurred_on)}</td>
                            <td>${b.attacker_tag} (${b.attacker_casualties || 0})</td>
                            <td>${b.defender_tag} (${b.defender_casualties || 0})</td>
                            <td>${b.winner_tag || '—'}</td>
                            <td>${(b.attacker_casualties || 0) + (b.defender_casualties || 0)}</td>
                        </tr>`).join('')}
                    </tbody>
                </table>
            </div>` : ''}
        `;

    } catch (err) {
        console.error('Error loading war details:', err);
        body.innerHTML = '<div class="text-danger">Error loading war details</div>';
    }
}

function renderParticipantList(participants) {
    if (!participants.length) {
        return '<p class="text-muted small">None recorded</p>';
    }
    return `
        <ul class="list-group list-group-flush">
            ${participants.map(p => `
            <li class="list-group-item px-0 py-1">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="d-flex align-items-center gap-2">
                        ${warFlagImg(p.country_tag)}
                        <span class="fw-bold">${getCountryName(p.country_tag)}
                            <small class="text-muted fw-normal">(${p.country_tag})</small>
                        </span>
                    </div>
                    <span class="badge bg-secondary ms-2">support ${p.war_support ?? '—'}</span>
                </div>
                <div class="text-muted small">
                    Casualties: ${formatCasualties(p.casualties || 0)}
                    · Mat: £${formatNumber(p.materiel_cost || 0)}
                    · Wage: £${formatNumber(p.wage_cost || 0)}
                </div>
            </li>`).join('')}
        </ul>`;
}

// ─── Export ───────────────────────────────────────────────────────────────────

async function exportWarsCSV() {
    try {
        const { col, dir } = warsState.warsSort;
        const sorted = sortData(warsState.warsData, col, dir);

        if (!sorted.length) {
            showAlert('No wars to export', 'warning');
            return;
        }

        const headers = ['War Type', 'Status', 'Started', 'Ended', 'Participants',
                         'Casualties', 'Materiel Cost', 'Wage Cost'];
        const rows = sorted.map(w => [
            w.war_type || '',
            w.status || '',
            w.started_on || '',
            w.ended_on || '',
            w.participant_count || 0,
            (w.total_casualties || 0).toFixed(3),
            (w.total_materiel_cost || 0).toFixed(2),
            (w.total_wage_cost || 0).toFixed(2)
        ]);

        const csv = [headers, ...rows]
            .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
            .join('\n');

        const blob = new Blob([csv], { type: 'text/csv' });
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = 'wars_export.csv';
        a.click();
        URL.revokeObjectURL(url);

    } catch (err) {
        console.error('Export error:', err);
        showAlert('Export failed', 'danger');
    }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Format a casualties value into human-readable form.
 * Victoria 3 stores casualties as fractional millions (1.0 = 1 000 000 soldiers).
 *   ≥ 1      →  "1.23M"
 *   ≥ 0.001  →  "1.2K"   (≈ 1 200 soldiers)
 *   > 0      →  "<1K"
 *   0        →  "0"
 */
function formatCasualties(n) {
    if (!n || n === 0) return '0';
    if (n >= 1)     return n.toFixed(2) + 'M';
    if (n >= 0.001) return (n * 1000).toFixed(1) + 'K';
    return '<1K';
}


function buildFilterParams() {
    const p = {};
    if (warsState.currentFilters.playthrough_id) p.playthrough_id = warsState.currentFilters.playthrough_id;
    if (warsState.currentFilters.country)        p.country        = warsState.currentFilters.country;
    if (warsState.currentFilters.status)         p.status         = warsState.currentFilters.status;
    return p;
}

/** Format a Victoria 3 diplomatic play type into a human-readable label. */
function formatWarType(warType) {
    if (!warType || warType === 'unknown') return 'Unknown War';
    return warType
        .replace(/^dp_/, '')
        .split('_')
        .map(w => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' ');
}

function warStatusBadge(status) {
    const map = {
        ongoing:     '<span class="badge bg-danger">Ongoing</span>',
        ended:       '<span class="badge bg-success">Ended</span>',
        white_peace: '<span class="badge bg-warning text-dark">White Peace</span>'
    };
    return map[status] || `<span class="badge bg-secondary">${status || '—'}</span>`;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

// ─── Exports ──────────────────────────────────────────────────────────────────
window.openWarModal          = openWarModal;
window.loadCountryPerformance = loadCountryPerformance;
