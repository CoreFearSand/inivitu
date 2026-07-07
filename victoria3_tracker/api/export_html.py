"""
Generate self-contained HTML exports for individual country stats.

Called by the /api/export/country-html/<tag> endpoint.
Produces a single .html file with all data embedded inline (SVG charts,
base64-encoded flag image, inline CSS).  No back-calls to the server at
all — the file can be shared and opened offline.
"""

import base64
import html as _html_module
import logging
import urllib.request
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# (db_key, human label, line colour)
_METRIC_DEFS = [
    ('gdp',            'GDP',                '#4e9af1'),
    ('population',     'Population',         '#50c878'),
    ('prestige',       'Prestige',           '#f0c040'),
    ('army_personnel', 'Army Personnel',     '#e05c5c'),
    ('weekly_income',  'Weekly Income',      '#a78bfa'),
    ('literacy',       'Literacy %',         '#38bdf8'),
    ('avgsol',         'Std of Living',      '#fb923c'),
    ('money_holding',  'Net Treasury',       '#34d399'),
    ('infamy',         'Infamy',             '#f87171'),
    ('credit',         'Credit Limit',       '#818cf8'),
    ('culture_amount', 'Cultures',           '#e879f9'),
]

_PERCENT_METRICS = frozenset({'literacy'})

_IG_COLORS = [
    '#ef4444', '#f97316', '#eab308', '#22c55e',
    '#06b6d4', '#3b82f6', '#8b5cf6', '#ec4899',
]


def _esc(text) -> str:
    return _html_module.escape(str(text) if text is not None else '', quote=True)


def _fmt(v) -> str:
    """Compact human-readable number.  Returns '—' for None/invalid."""
    if v is None:
        return '—'
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '—'
    if abs(v) >= 1_000_000_000:
        return f'{v / 1e9:.2f}B'
    if abs(v) >= 1_000_000:
        return f'{v / 1e6:.2f}M'
    if abs(v) >= 1_000:
        return f'{v / 1e3:.1f}k'
    return f'{v:.1f}'


def _fmt_pct(v) -> str:
    """Format a 0-1 fraction as a whole-number percentage, e.g. 0.129 → '13%'."""
    if v is None:
        return '—'
    try:
        return f'{round(float(v) * 100)}%'
    except (TypeError, ValueError):
        return '—'


def _embed_flag(tag: str, url: str) -> str:
    """Fetch flag from the given URL and return an <img data-url> tag.
    Falls back to a styled <div> with the tag text if the fetch fails.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Victoria3Tracker/1.0)'},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
        b64  = base64.b64encode(raw).decode('ascii')
        mime = 'image/svg+xml' if url.endswith('.svg') else 'image/png'
        return (
            f'<img src="data:{mime};base64,{b64}" alt="{_esc(tag)}" '
            f'style="width:96px;height:64px;object-fit:cover;border-radius:4px;'
            f'border:2px solid rgba(255,255,255,.25);">'
        )
    except Exception as exc:
        logger.warning('Could not fetch flag %s from %s: %s', tag, url, exc)
        return (
            f'<div style="width:96px;height:64px;background:#1e3a5f;border-radius:4px;'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-weight:700;color:#8bb8e8;font-size:.9rem;letter-spacing:2px;">'
            f'{_esc(tag)}</div>'
        )


def _svg_chart(
    series_list: list,
    title: str = '',
    w: int = 700,
    h: int = 280,
    y_label_fn=None,
) -> str:
    """Return a standalone SVG line-chart string.

    series_list: [
        {'label': str, 'color': str,
         'data':  [{'date': str, 'value': float | None}, ...]}
    ]
    The SVG uses viewBox so it scales to any container width via
    ``style="width:100%"``.
    """
    PAD_L, PAD_R, PAD_T, PAD_B = 70, 22, 32, 52

    all_pts = [
        (p['date'], p['value'])
        for s in series_list
        for p in s.get('data', [])
        if p.get('value') is not None
    ]

    if not all_pts:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'style="width:100%;background:#1a2035;border-radius:6px;">'
            f'<text x="{w//2}" y="{h//2}" text-anchor="middle" '
            f'fill="#555" font-size="13">No data for this playthrough</text>'
            f'</svg>'
        )

    all_dates  = sorted(set(p[0] for p in all_pts))
    date_to_ix = {d: i for i, d in enumerate(all_dates)}
    vals       = [p[1] for p in all_pts]
    y_min, y_max = min(vals), max(vals)

    # Guard against flat lines (all same value)
    if y_min == y_max:
        pad   = max(abs(y_min) * 0.05, 1)
        y_min -= pad
        y_max += pad
    y_range = y_max - y_min

    cw = w - PAD_L - PAD_R
    ch = h - PAD_T - PAD_B
    nd = max(len(all_dates) - 1, 1)

    def xp(date):
        return PAD_L + date_to_ix.get(date, 0) / nd * cw

    def yp(val):
        return PAD_T + (1.0 - (val - y_min) / y_range) * ch

    buf = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'style="width:100%;background:#1a2035;border-radius:6px;">'
    ]

    if title:
        buf.append(
            f'<text x="{PAD_L}" y="20" fill="#b0bec5" '
            f'font-size="11" font-weight="600">{_esc(title)}</text>'
        )

    _ylbl = y_label_fn if y_label_fn is not None else _fmt
    N_GRID = 5
    for i in range(N_GRID + 1):
        v  = y_min + i / N_GRID * y_range
        yv = yp(v)
        buf.append(
            f'<line x1="{PAD_L}" y1="{yv:.1f}" '
            f'x2="{w - PAD_R}" y2="{yv:.1f}" '
            f'stroke="#243050" stroke-width="1"/>'
        )
        buf.append(
            f'<text x="{PAD_L - 4}" y="{yv + 4:.1f}" text-anchor="end" '
            f'fill="#78909c" font-size="9.5">{_ylbl(v)}</text>'
        )

    total   = len(all_dates)
    n_show  = min(6, total)
    step    = max(1, (total - 1) // max(n_show - 1, 1)) if n_show > 1 else 1
    x_idxs  = sorted(set(list(range(0, total, step)) + [total - 1]))
    bot     = h - PAD_B + 14
    for idx in x_idxs:
        xv  = PAD_L + idx / nd * cw
        lbl = all_dates[idx][:7]          # YYYY-MM
        buf.append(
            f'<text x="{xv:.1f}" y="{bot}" text-anchor="middle" '
            f'fill="#78909c" font-size="9" '
            f'transform="rotate(-25 {xv:.1f} {bot})">{_esc(lbl)}</text>'
        )

    cid = f'c{abs(hash(title + str(series_list[:1]))) % 999983}'
    buf.append(
        f'<defs><clipPath id="{cid}">'
        f'<rect x="{PAD_L}" y="{PAD_T}" width="{cw}" height="{ch}"/>'
        f'</clipPath></defs>'
    )

    buf.append(
        f'<line x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{PAD_T + ch}" '
        f'stroke="#37474f" stroke-width="1.5"/>'
    )
    buf.append(
        f'<line x1="{PAD_L}" y1="{PAD_T + ch}" x2="{PAD_L + cw}" y2="{PAD_T + ch}" '
        f'stroke="#37474f" stroke-width="1.5"/>'
    )

    show_dots = total <= 30
    for s in series_list:
        clr  = s.get('color', '#4e9af1')
        pts  = [
            p for p in s.get('data', [])
            if p.get('value') is not None and p.get('date') in date_to_ix
        ]
        if not pts:
            continue
        poly = ' '.join(f'{xp(p["date"]):.1f},{yp(p["value"]):.1f}' for p in pts)
        buf.append(
            f'<polyline points="{poly}" fill="none" stroke="{clr}" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round" '
            f'clip-path="url(#{cid})"/>'
        )
        if show_dots:
            for p in pts:
                buf.append(
                    f'<circle cx="{xp(p["date"]):.1f}" cy="{yp(p["value"]):.1f}" '
                    f'r="3" fill="{clr}" clip-path="url(#{cid})"/>'
                )

    if len(series_list) > 1:
        ly = h - 9
        lx = PAD_L
        for i, s in enumerate(series_list):
            clr = s.get('color', '#4e9af1')
            lbl = s.get('label', '')
            tx  = lx + i * 105
            if tx + 95 > w:
                break
            buf.append(
                f'<line x1="{tx}" y1="{ly}" x2="{tx + 14}" y2="{ly}" '
                f'stroke="{clr}" stroke-width="2"/>'
            )
            buf.append(
                f'<text x="{tx + 18}" y="{ly + 4}" fill="#90a4ae" font-size="9">'
                f'{_esc(lbl)}</text>'
            )

    buf.append('</svg>')
    return ''.join(buf)


def generate_country_html(
    db_manager,
    data_access,
    country_tag: str,
    playthrough_id: str,
) -> str:
    """Build a fully self-contained HTML export for one country + playthrough.

    Args:
        db_manager:    DatabaseManager instance (for raw queries)
        data_access:   DataAccessLayer instance (for higher-level queries)
        country_tag:   3-letter tag (e.g. 'FRA') or 'D99' for global
        playthrough_id: Playthrough UUID

    Returns:
        Complete HTML string ready to be written to a .html file.
    """
    from .flag_utils import flag_url as _flag_url

    tag = country_tag.upper()

    name_rows = db_manager.execute_query(
        """
        SELECT c.name FROM Countries c
        JOIN Saves s ON c.save_id = s.save_id
        WHERE c.country_tag = ? AND s.playthrough_id = ?
        ORDER BY s.in_game_date DESC LIMIT 1
        """,
        (tag, playthrough_id),
    )
    country_name = (name_rows[0]['name'] if name_rows else None) or tag

    pt_rows = db_manager.execute_query(
        """
        SELECT MIN(in_game_date) AS start_date,
               MAX(in_game_date) AS end_date,
               MIN(player_country) AS player_country
        FROM Saves WHERE playthrough_id = ?
        """,
        (playthrough_id,),
    )
    pt         = dict(pt_rows[0]) if pt_rows else {}
    start_date = pt.get('start_date') or '?'
    end_date   = pt.get('end_date')   or '?'

    flag_img = _embed_flag(tag, _flag_url(tag))

    charts_html       = ''
    metric_cards_html = ''

    is_global = (tag == 'D99')

    for metric_key, metric_label, color in _METRIC_DEFS:
        if is_global:
            rows     = data_access.get_global_metrics_history(metric_key, playthrough_id, 9999)
            data_pts = [{'date': r['in_game_date'], 'value': r['amount']} for r in rows]
        else:
            rows     = data_access.get_country_metrics_for_playthrough(
                tag, metric_key, playthrough_id, 9999
            )
            data_pts = [
                {'date': r.get('in_game_date') or r.get('recorded_at'), 'value': r['amount']}
                for r in rows
            ]

        latest_val = data_pts[-1]['value'] if data_pts else None

        is_pct = metric_key in _PERCENT_METRICS
        if is_pct:
            data_pts = [
                {'date': p['date'], 'value': (p['value'] * 100) if p['value'] is not None else None}
                for p in data_pts
            ]
            latest_val_scaled = (latest_val * 100) if latest_val is not None else None
            card_value = f'{round(latest_val_scaled)}%' if latest_val_scaled is not None else '—'
        else:
            card_value = _fmt(latest_val)

        metric_cards_html += (
            f'<div class="mcard">'
            f'<div class="mcard-label">{_esc(metric_label)}</div>'
            f'<div class="mcard-value">{card_value}</div>'
            f'</div>\n'
        )

        svg_kwargs = {'y_label_fn': lambda v: f'{round(v)}%'} if is_pct else {}
        svg          = _svg_chart(
            [{'label': metric_label, 'color': color, 'data': data_pts}],
            title=metric_label,
            **svg_kwargs,
        )
        charts_html += f'<div class="chart-cell">{svg}</div>\n'

    if is_global:
        ig_history = data_access.get_global_ig_history(playthrough_id)
        ig_latest  = []
    else:
        ig_history = data_access.get_interest_groups_history(tag, playthrough_id)
        ig_latest  = data_access.get_interest_groups_for_country(tag, playthrough_id)

    ig_clout_series    = []
    ig_approval_series = []
    for i, (ig_type, pts) in enumerate(ig_history.items()):
        clr = _IG_COLORS[i % len(_IG_COLORS)]
        lbl = ig_type.replace('ig_', '').replace('_', ' ').title()
        ig_clout_series.append({
            'label': lbl, 'color': clr,
            # Scale clout (0-1) to whole-percentage values for the chart
            'data': [{'date': p['date'], 'value': (p['clout'] * 100) if p.get('clout') is not None else None} for p in pts],
        })
        ig_approval_series.append({
            'label': lbl, 'color': clr,
            'data': [{'date': p['date'], 'value': p.get('approval')} for p in pts],
        })

    _pct_lbl = lambda v: f'{round(v)}%'
    ig_clout_svg    = _svg_chart(ig_clout_series,    title='IG Clout Over Time',    w=1000, h=300, y_label_fn=_pct_lbl) if ig_clout_series    else ''
    ig_approval_svg = _svg_chart(ig_approval_series, title='IG Approval Over Time', w=1000, h=300) if ig_approval_series else ''

    ig_table_rows = ''
    for ig in ig_latest:
        gov_badge = (
            '<span class="badge-gov">In Gov</span>'
            if ig.get('in_government') else ''
        )
        ig_table_rows += (
            f'<tr>'
            f'<td>{_esc(ig.get("ig_type", ""))}</td>'
            f'<td>{_fmt_pct(ig.get("clout"))}</td>'
            f'<td>{round(ig.get("approval") or 0):+d}%</td>'
            f'<td>{_fmt(ig.get("membership"))}</td>'
            f'<td>{gov_badge}</td>'
            f'</tr>\n'
        )

    law_history  = data_access.get_law_history(tag, playthrough_id)
    active_laws: dict = {}          # law_group → most-recent row
    for law in law_history:         # already ASC → last wins
        group = law.get('law_group') or ''
        active_laws[group] = law

    by_category: dict = {}
    for group, law in sorted(active_laws.items()):
        cat = law.get('category') or 'Other'
        by_category.setdefault(cat, []).append(law)

    law_rows_html = ''
    for cat in sorted(by_category):
        law_rows_html += (
            f'<tr class="cat-header"><td colspan="3">{_esc(cat)}</td></tr>\n'
        )
        for law in by_category[cat]:
            dot_color = law.get('group_color') or '#555'
            law_rows_html += (
                f'<tr>'
                f'<td>'
                f'<span class="law-dot" style="background:{_esc(dot_color)};"></span>'
                f'{_esc(law.get("group_label") or law.get("law_group", ""))}'
                f'</td>'
                f'<td>'
                f'<span class="law-badge" style="border-color:{_esc(dot_color)};color:{_esc(dot_color)};">'
                f'{_esc(law.get("law_label") or law.get("law_key", ""))}'
                f'</span>'
                f'</td>'
                f'<td style="color:#666;font-size:.82rem;">'
                f'{_esc(law.get("activation_date", ""))}'
                f'</td>'
                f'</tr>\n'
            )

    wars = data_access.get_war_statistics(
        country_tag=None if is_global else tag,
        playthrough_id=playthrough_id,
        limit=9999,
    )
    war_rows_html = ''
    for w in wars:
        status      = w.get('status') or ''
        s_cls       = 'badge-ongoing' if status == 'ongoing' else 'badge-ended'
        war_type    = (w.get('war_type') or '').replace('_', ' ').title()
        side        = (w.get('side') or w.get('attacker_count') and 'multi' or '').title()
        casualties  = w.get('casualties') or w.get('total_casualties')
        war_rows_html += (
            f'<tr>'
            f'<td>{_esc(war_type or "—")}</td>'
            f'<td>{_esc(w.get("started_on") or "—")}</td>'
            f'<td>{_esc(w.get("ended_on") or "—")}</td>'
            f'<td>{_esc(side or "—")}</td>'
            f'<td><span class="{s_cls}">{_esc(status)}</span></td>'
            f'<td>{_fmt(casualties)}</td>'
            f'</tr>\n'
        )

    export_ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    pt_short  = playthrough_id[:8] if playthrough_id else '?'

    ig_section = ''
    if ig_clout_series or ig_latest:
        ig_section = (
            '<h2>Interest Groups</h2>\n'
            + (f'<div class="chart-full">{ig_clout_svg}</div>\n' if ig_clout_svg else '')
            + (f'<div class="chart-full">{ig_approval_svg}</div>\n' if ig_approval_svg else '')
            + (
                '<table><thead><tr>'
                '<th>Interest Group</th><th>Clout</th>'
                '<th>Approval</th><th>Members</th><th>Status</th>'
                f'</tr></thead><tbody>{ig_table_rows}</tbody></table>\n'
                if ig_table_rows else ''
            )
        )

    law_section = ''
    if active_laws:
        law_section = (
            '<h2>Active Laws</h2>\n'
            '<table><thead><tr>'
            '<th>Law Group</th><th>Current Law</th><th>Since</th>'
            f'</tr></thead><tbody>{law_rows_html}</tbody></table>\n'
        )

    war_section = ''
    if wars:
        war_section = (
            '<h2>Wars</h2>\n'
            '<table><thead><tr>'
            '<th>Type</th><th>Started</th><th>Ended</th>'
            '<th>Side</th><th>Status</th><th>Casualties</th>'
            f'</tr></thead><tbody>{war_rows_html}</tbody></table>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(country_name)} — Victoria 3 Stats</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;padding:24px 20px;min-width:320px}}
h2{{font-size:1rem;font-weight:600;color:#8b949e;text-transform:uppercase;letter-spacing:.08em;margin:30px 0 14px;border-bottom:1px solid #21262d;padding-bottom:8px}}
.header{{display:flex;align-items:center;gap:20px;background:linear-gradient(135deg,#0d1f37 0%,#0a2d50 100%);border-radius:10px;padding:20px 24px;margin-bottom:24px;border:1px solid #1a3a5c}}
.header h1{{font-size:1.8rem;font-weight:700;margin-bottom:4px}}
.header-sub{{color:#8b949e;font-size:.88rem;margin-top:3px}}
.mcard-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:12px;margin-bottom:6px}}
.mcard{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;text-align:center}}
.mcard-label{{font-size:.72rem;color:#8b949e;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}}
.mcard-value{{font-size:1.35rem;font-weight:700;color:#4e9af1}}
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}}
@media(max-width:680px){{.chart-grid{{grid-template-columns:1fr}}}}
.chart-cell,.chart-full{{overflow:hidden;border-radius:6px}}
.chart-full{{margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;font-size:.87rem;background:#161b22;border-radius:8px;overflow:hidden;margin-bottom:16px}}
thead tr{{background:#1c2128}}
th{{padding:10px 13px;text-align:left;font-weight:600;color:#8b949e;font-size:.78rem;text-transform:uppercase;letter-spacing:.05em}}
td{{padding:8px 13px;border-top:1px solid #21262d;color:#c9d1d9;vertical-align:middle}}
tr:hover td{{background:#1c2128}}
.cat-header td{{background:#1c2128;color:#4e9af1;font-weight:600;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;padding:7px 13px}}
.badge-gov{{background:#0d2e0d;color:#3fb950;border:1px solid #3fb950;border-radius:4px;padding:2px 8px;font-size:.72rem;font-weight:600;white-space:nowrap}}
.badge-ongoing{{background:#0d1f36;color:#4e9af1;border:1px solid #4e9af1;border-radius:4px;padding:2px 8px;font-size:.72rem;white-space:nowrap}}
.badge-ended{{background:#1a1a1a;color:#6e7681;border:1px solid #30363d;border-radius:4px;padding:2px 8px;font-size:.72rem;white-space:nowrap}}
.law-dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px;vertical-align:middle;flex-shrink:0}}
.law-badge{{display:inline-block;border:1px solid;border-radius:12px;padding:2px 10px;font-size:.76rem;font-weight:500;white-space:nowrap}}
.footer{{margin-top:36px;padding-top:14px;border-top:1px solid #21262d;color:#3d444d;font-size:.78rem;text-align:center}}
</style>
</head>
<body>

<div class="header">
  <div style="flex-shrink:0">{flag_img}</div>
  <div>
    <h1>{_esc(country_name)}</h1>
    <div class="header-sub">Victoria 3 · {_esc(start_date)} → {_esc(end_date)}</div>
    <div class="header-sub" style="font-size:.78rem;color:#3d444d;margin-top:2px">Playthrough: {_esc(pt_short)}&hellip;</div>
  </div>
</div>

<h2>Current Metrics</h2>
<div class="mcard-grid">
{metric_cards_html}
</div>

<h2>Historical Trends</h2>
<div class="chart-grid">
{charts_html}
</div>

{ig_section}
{law_section}
{war_section}

<div class="footer">
  Exported {_esc(export_ts)} &middot; Victoria 3 Game Tracker &middot; Fully offline &mdash; no server connection required
</div>

</body>
</html>"""
