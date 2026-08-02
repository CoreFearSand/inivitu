"""
Economic data API endpoints for Victoria 3 Game Tracker.

Provides endpoints for GDP-by-good data, trade balances, and GDP ownership.
"""

import logging
from flask import jsonify, request, abort

from .flag_utils import flag_url as _flag_url

logger = logging.getLogger(__name__)

# GDP figures are extracted as per-WEEK production value (output_qty × price).
# The UI shows ANNUAL GDP, so weekly figures are scaled by the average number of
# weeks in a year (365.25 / 7). This applies to production/GDP revenue and the
# quantities derived from it — NOT to trade flows, which stay as-is to match the
# in-game market trade screen.
WEEKS_PER_YEAR = 365.25 / 7  # ≈ 52.18


class EconomicEndpoints:
    """API endpoints for economic data (GDP by good, trade, ownership)."""

    def __init__(self, api_app):
        self.api = api_app
        self.app = api_app.app
        self.db_manager = api_app.db_manager
        self.data_access = api_app.data_access
        self._register_routes()
        logger.info("Economic API endpoints registered")

    def _register_routes(self):

        @self.app.route('/api/economics/saves')
        def get_economics_saves():
            """List saves that have GDP-by-good data, newest first."""
            rows = self.db_manager.execute_query("""
                SELECT s.save_id, s.filename, s.in_game_date, s.playthrough_id
                FROM Saves s
                WHERE EXISTS (
                    SELECT 1 FROM GDPByGood g WHERE g.save_id = s.save_id
                )
                ORDER BY s.in_game_date DESC, s.saved_at DESC
            """, ())
            return jsonify([dict(r) for r in rows])

        @self.app.route('/api/economics/gdp-by-good')
        def get_gdp_by_good():
            """Aggregated GDP by good for one save, sorted by revenue descending.

            Query params:
                save_id (required)
            """
            save_id = request.args.get('save_id', '').strip()
            if not save_id:
                abort(400, 'save_id required')
            rows = self.db_manager.execute_query("""
                SELECT
                    good_name,
                    MAX(building_group) AS building_group,
                    SUM(revenue)        AS total_revenue
                FROM GDPByGood
                WHERE save_id = ?
                GROUP BY good_name
                HAVING total_revenue > 0
                ORDER BY total_revenue DESC
            """, (save_id,))
            out = []
            for r in rows:
                d = dict(r)
                d['total_revenue'] = round((d['total_revenue'] or 0) * WEEKS_PER_YEAR, 2)
                out.append(d)
            return jsonify(out)

        @self.app.route('/api/economics/country/<country_tag>/saves')
        def get_country_economic_saves(country_tag: str):
            """List saves that have GDP-by-good data for a specific country, newest first."""
            if country_tag.upper() == 'D99':
                rows = self.db_manager.execute_query("""
                    SELECT s.save_id, s.filename, s.in_game_date
                    FROM Saves s
                    WHERE EXISTS (SELECT 1 FROM GDPByGood g WHERE g.save_id = s.save_id)
                    ORDER BY s.in_game_date DESC, s.saved_at DESC
                """, ())
            else:
                rows = self.db_manager.execute_query("""
                    SELECT s.save_id, s.filename, s.in_game_date
                    FROM Saves s
                    WHERE EXISTS (
                        SELECT 1 FROM GDPByGood g
                        WHERE g.save_id = s.save_id AND g.country_tag = ?
                    )
                    ORDER BY s.in_game_date DESC, s.saved_at DESC
                """, (country_tag,))
            return jsonify([dict(r) for r in rows])

        @self.app.route('/api/economics/country/<country_tag>/gdp-timeline')
        def get_country_gdp_timeline(country_tag: str):
            """Time-series GDP by good for a country across all saves in a playthrough.

            Query params:
                playthrough_id  (optional — auto-selects latest if omitted)

            Returns:
                {dates, goods:[{name,group,values,latest}], total_latest, latest_date, playthrough_id}
            """
            playthrough_id = request.args.get('playthrough_id', '').strip()
            is_global = country_tag.upper() == 'D99'

            if not playthrough_id:
                if is_global:
                    pt_rows = self.db_manager.execute_query("""
                        SELECT DISTINCT s.playthrough_id
                        FROM GDPByGood g JOIN Saves s ON s.save_id = g.save_id
                        ORDER BY s.in_game_date DESC LIMIT 1
                    """, ())
                else:
                    pt_rows = self.db_manager.execute_query("""
                        SELECT DISTINCT s.playthrough_id
                        FROM GDPByGood g
                        JOIN Saves s ON s.save_id = g.save_id
                        WHERE g.country_tag = ?
                        ORDER BY s.in_game_date DESC
                        LIMIT 1
                    """, (country_tag,))
                pt_list = list(pt_rows)
                if not pt_list:
                    return jsonify({'dates': [], 'goods': [], 'total_latest': 0,
                                    'latest_date': None, 'playthrough_id': None})
                playthrough_id = pt_list[0]['playthrough_id']

            if is_global:
                rows = self.db_manager.execute_query("""
                    SELECT s.in_game_date, g.good_name, MAX(g.building_group) AS building_group,
                           SUM(g.revenue) AS revenue, AVG(p.price) AS price
                    FROM GDPByGood g
                    JOIN Saves s ON s.save_id = g.save_id
                    JOIN (SELECT in_game_date AS d, MAX(saved_at) AS mx FROM Saves
                          WHERE playthrough_id = ? GROUP BY in_game_date) can
                         ON can.d = s.in_game_date AND can.mx = s.saved_at
                    LEFT JOIN GoodPrices p ON p.save_id = g.save_id AND p.good_name = g.good_name
                    WHERE s.playthrough_id = ?
                    GROUP BY s.in_game_date, g.good_name
                    ORDER BY s.in_game_date ASC
                """, (playthrough_id, playthrough_id))
            else:
                rows = self.db_manager.execute_query("""
                    SELECT s.in_game_date, g.good_name, g.building_group, g.revenue, p.price AS price
                    FROM GDPByGood g
                    JOIN Saves s ON s.save_id = g.save_id
                    JOIN (SELECT in_game_date AS d, MAX(saved_at) AS mx FROM Saves
                          WHERE playthrough_id = ? GROUP BY in_game_date) can
                         ON can.d = s.in_game_date AND can.mx = s.saved_at
                    LEFT JOIN GoodPrices p ON p.save_id = g.save_id AND p.good_name = g.good_name
                    WHERE s.playthrough_id = ? AND g.country_tag = ?
                    ORDER BY s.in_game_date ASC
                """, (playthrough_id, playthrough_id, country_tag))
            rows = [dict(r) for r in rows]

            if not rows:
                return jsonify({'dates': [], 'goods': [], 'total_latest': 0,
                                'latest_date': None, 'playthrough_id': playthrough_id})

            date_order, seen_dates, goods_data = [], set(), {}
            for row in rows:
                d = row['in_game_date']
                if d not in seen_dates:
                    date_order.append(d)
                    seen_dates.add(d)
                gn = row['good_name']
                if gn not in goods_data:
                    goods_data[gn] = {'group': row['building_group'], 'by_date': {}, 'qty_by_date': {}}
                goods_data[gn]['by_date'][d] = row['revenue']
                price = row.get('price') or 0
                goods_data[gn]['qty_by_date'][d] = round(row['revenue'] / price, 2) if price else 0

            latest_date = date_order[-1]
            goods_list = []
            for gn, gdata in goods_data.items():
                values = [round(gdata['by_date'].get(d, 0) * WEEKS_PER_YEAR, 2) for d in date_order]
                quantities = [round(gdata['qty_by_date'].get(d, 0) * WEEKS_PER_YEAR, 2) for d in date_order]
                goods_list.append({
                    'name': gn,
                    'group': gdata['group'],
                    'values': values,
                    'quantities': quantities,
                    'latest': round(gdata['by_date'].get(latest_date, 0) * WEEKS_PER_YEAR, 2)
                })
            goods_list.sort(key=lambda x: x['latest'], reverse=True)

            return jsonify({
                'dates': date_order,
                'goods': goods_list,
                'total_latest': round(sum(g['latest'] for g in goods_list), 2),
                'latest_date': latest_date,
                'playthrough_id': playthrough_id
            })

        @self.app.route('/api/economics/country/<country_tag>/gdp-by-good')
        def get_country_gdp_by_good(country_tag: str):
            """GDP by good for a specific country in one save, sorted by revenue descending.

            Query params:
                save_id (required)
            """
            save_id = request.args.get('save_id', '').strip()
            if not save_id:
                abort(400, 'save_id required')
            rows = self.db_manager.execute_query("""
                SELECT good_name, building_group, revenue
                FROM GDPByGood
                WHERE save_id = ? AND country_tag = ?
                ORDER BY revenue DESC
            """, (save_id, country_tag))
            out = []
            for r in rows:
                d = dict(r)
                d['revenue'] = round((d['revenue'] or 0) * WEEKS_PER_YEAR, 2)
                out.append(d)
            return jsonify(out)

        @self.app.route('/api/economics/country/<country_tag>/market-data')
        def get_country_market_data(country_tag: str):
            """Production, exports, imports data for a country — used by the Market treemap.

            Query params:
                playthrough_id  (optional — auto-selects latest)
                save_id         (optional — overrides playthrough_id)

            Returns:
                {save_id, in_game_date, production, exports, imports}
                production: [{good_name, building_group, revenue}]
                exports:    [{good_name, net_quantity, value}] (net_qty > 0)
                imports:    [{good_name, net_quantity, value}] (net_qty < 0, values positive)
            """
            save_id = request.args.get('save_id', '').strip()
            playthrough_id = request.args.get('playthrough_id', '').strip()
            db = self.db_manager

            is_global = country_tag.upper() == 'D99'

            if not save_id:
                # Resolve latest save for this playthrough (or globally latest)
                if is_global:
                    if playthrough_id:
                        pt_rows = db.execute_query("""
                            SELECT s.save_id, s.in_game_date FROM Saves s
                            WHERE s.playthrough_id = ?
                              AND EXISTS (SELECT 1 FROM GDPByGood g WHERE g.save_id = s.save_id)
                            ORDER BY s.in_game_date DESC LIMIT 1
                        """, (playthrough_id,))
                    else:
                        pt_rows = db.execute_query("""
                            SELECT s.save_id, s.in_game_date FROM Saves s
                            WHERE EXISTS (SELECT 1 FROM GDPByGood g WHERE g.save_id = s.save_id)
                            ORDER BY s.in_game_date DESC LIMIT 1
                        """, ())
                elif playthrough_id:
                    pt_rows = db.execute_query("""
                        SELECT s.save_id, s.in_game_date FROM Saves s
                        WHERE s.playthrough_id = ?
                          AND EXISTS (SELECT 1 FROM GDPByGood g WHERE g.save_id = s.save_id AND g.country_tag = ?)
                        ORDER BY s.in_game_date DESC LIMIT 1
                    """, (playthrough_id, country_tag))
                else:
                    pt_rows = db.execute_query("""
                        SELECT s.save_id, s.in_game_date FROM Saves s
                        WHERE EXISTS (SELECT 1 FROM GDPByGood g WHERE g.save_id = s.save_id AND g.country_tag = ?)
                        ORDER BY s.in_game_date DESC LIMIT 1
                    """, (country_tag,))
                pt_list = list(pt_rows)
                if not pt_list:
                    return jsonify({"save_id": None, "in_game_date": None,
                                    "production": [], "exports": [], "imports": []})
                save_id = pt_list[0]["save_id"]
                in_game_date = pt_list[0]["in_game_date"]
            else:
                d_rows = db.execute_query("SELECT in_game_date FROM Saves WHERE save_id = ?", (save_id,))
                in_game_date = list(d_rows)[0]["in_game_date"] if d_rows else None

            # Prices (same for both)
            price_map = {r["good_name"]: r["price"] for r in db.execute_query(
                "SELECT good_name, price FROM GoodPrices WHERE save_id = ?", (save_id,)
            )}

            if is_global:
                # Production: sum across all countries
                prod = [dict(r) for r in db.execute_query("""
                    SELECT good_name, MAX(building_group) AS building_group, SUM(revenue) AS revenue
                    FROM GDPByGood WHERE save_id = ?
                    GROUP BY good_name ORDER BY revenue DESC
                """, (save_id,))]

                # Gross global trade: sum positive side as exports, negative side as imports per good
                trade_rows = list(db.execute_query("""
                    SELECT good_name,
                           SUM(CASE WHEN net_quantity > 0 THEN net_quantity ELSE 0 END)        AS gross_exp,
                           SUM(CASE WHEN net_quantity < 0 THEN ABS(net_quantity) ELSE 0 END)   AS gross_imp
                    FROM TradeBalance WHERE save_id = ?
                    GROUP BY good_name
                """, (save_id,)))
                exports, imports = [], []
                for row in trade_rows:
                    gn = row["good_name"]
                    price = price_map.get(gn, 0.0)
                    if row["gross_exp"] > 0:
                        exports.append({"good_name": gn, "net_quantity": round(row["gross_exp"], 2),
                                        "value": round(row["gross_exp"] * price, 2)})
                    if row["gross_imp"] > 0:
                        imports.append({"good_name": gn, "net_quantity": round(row["gross_imp"], 2),
                                        "value": round(row["gross_imp"] * price, 2)})
            else:
                # Production
                prod = [dict(r) for r in db.execute_query("""
                    SELECT good_name, building_group, revenue
                    FROM GDPByGood WHERE save_id = ? AND country_tag = ?
                    ORDER BY revenue DESC
                """, (save_id, country_tag))]

                # Trade (use country_tag as market_tag)
                trade = list(db.execute_query("""
                    SELECT good_name, net_quantity FROM TradeBalance
                    WHERE save_id = ? AND market_tag = ?
                """, (save_id, country_tag)))
                exports, imports = [], []
                for row in trade:
                    gn = row["good_name"]
                    nq = row["net_quantity"]
                    price = price_map.get(gn, 0.0)
                    value = abs(nq) * price
                    if nq > 0:
                        exports.append({"good_name": gn, "net_quantity": round(nq, 2), "value": round(value, 2)})
                    elif nq < 0:
                        imports.append({"good_name": gn, "net_quantity": round(-nq, 2), "value": round(value, 2)})

            # Annualise production GDP (weekly → yearly); quantity is derived from
            # the annualised revenue so production units are also per-year. Trade
            # (exports/imports) is left weekly to match the in-game trade screen.
            for r in prod:
                r["revenue"] = round((r["revenue"] or 0) * WEEKS_PER_YEAR, 2)
                p = price_map.get(r["good_name"], 0.0)
                r["quantity"] = round(r["revenue"] / p, 2) if p > 0 else 0.0

            # Rank by traded QUANTITY, matching the in-game market screen (which
            # sizes goods by units traded, not by £ value).
            exports.sort(key=lambda r: r["net_quantity"], reverse=True)
            imports.sort(key=lambda r: r["net_quantity"], reverse=True)

            return jsonify({
                "save_id": save_id,
                "in_game_date": in_game_date,
                "production": prod,
                "exports": exports,
                "imports": imports,
            })

        @self.app.route('/api/economics/country/<country_tag>/trade-timeline')
        def get_country_trade_timeline(country_tag: str):
            """Time-series of traded QUANTITY per good for a country/market across a
            playthrough, split into export and import sides.

            Query params:
                playthrough_id  (optional — auto-selects latest with trade data)

            Returns:
                {dates, exports:[{name,values,latest}], imports:[{name,values,latest}],
                 latest_date, playthrough_id}
            """
            playthrough_id = request.args.get('playthrough_id', '').strip()
            is_global = country_tag.upper() == 'D99'
            db = self.db_manager

            if not playthrough_id:
                if is_global:
                    pt_rows = db.execute_query("""
                        SELECT DISTINCT s.playthrough_id
                        FROM TradeBalance t JOIN Saves s ON s.save_id = t.save_id
                        ORDER BY s.in_game_date DESC LIMIT 1
                    """, ())
                else:
                    pt_rows = db.execute_query("""
                        SELECT DISTINCT s.playthrough_id
                        FROM TradeBalance t JOIN Saves s ON s.save_id = t.save_id
                        WHERE t.market_tag = ?
                        ORDER BY s.in_game_date DESC LIMIT 1
                    """, (country_tag,))
                pt_list = list(pt_rows)
                if not pt_list:
                    return jsonify({'dates': [], 'exports': [], 'imports': [],
                                    'latest_date': None, 'playthrough_id': None})
                playthrough_id = pt_list[0]['playthrough_id']

            if is_global:
                rows = db.execute_query("""
                    SELECT s.in_game_date,
                           t.good_name,
                           SUM(CASE WHEN t.net_quantity > 0 THEN t.net_quantity ELSE 0 END)      AS exp_q,
                           SUM(CASE WHEN t.net_quantity < 0 THEN ABS(t.net_quantity) ELSE 0 END) AS imp_q,
                           AVG(p.price) AS price
                    FROM TradeBalance t JOIN Saves s ON s.save_id = t.save_id
                    JOIN (SELECT in_game_date AS d, MAX(saved_at) AS mx FROM Saves
                          WHERE playthrough_id = ? GROUP BY in_game_date) can
                         ON can.d = s.in_game_date AND can.mx = s.saved_at
                    LEFT JOIN GoodPrices p ON p.save_id = t.save_id AND p.good_name = t.good_name
                    WHERE s.playthrough_id = ?
                    GROUP BY s.in_game_date, t.good_name
                    ORDER BY s.in_game_date ASC
                """, (playthrough_id, playthrough_id))
            else:
                rows = db.execute_query("""
                    SELECT s.in_game_date,
                           t.good_name,
                           SUM(CASE WHEN t.net_quantity > 0 THEN t.net_quantity ELSE 0 END)      AS exp_q,
                           SUM(CASE WHEN t.net_quantity < 0 THEN ABS(t.net_quantity) ELSE 0 END) AS imp_q,
                           AVG(p.price) AS price
                    FROM TradeBalance t JOIN Saves s ON s.save_id = t.save_id
                    JOIN (SELECT in_game_date AS d, MAX(saved_at) AS mx FROM Saves
                          WHERE playthrough_id = ? GROUP BY in_game_date) can
                         ON can.d = s.in_game_date AND can.mx = s.saved_at
                    LEFT JOIN GoodPrices p ON p.save_id = t.save_id AND p.good_name = t.good_name
                    WHERE s.playthrough_id = ? AND t.market_tag = ?
                    GROUP BY s.in_game_date, t.good_name
                    ORDER BY s.in_game_date ASC
                """, (playthrough_id, playthrough_id, country_tag))
            rows = [dict(r) for r in rows]

            if not rows:
                return jsonify({'dates': [], 'exports': [], 'imports': [],
                                'latest_date': None, 'playthrough_id': playthrough_id})

            date_order, seen = [], set()
            exp_goods, imp_goods = {}, {}
            for row in rows:
                d = row['in_game_date']
                if d not in seen:
                    date_order.append(d); seen.add(d)
                gn = row['good_name']
                price = row.get('price') or 0
                if row['exp_q']:
                    exp_goods.setdefault(gn, {})[d] = (row['exp_q'], round(row['exp_q'] * price, 2))
                if row['imp_q']:
                    imp_goods.setdefault(gn, {})[d] = (row['imp_q'], round(row['imp_q'] * price, 2))

            latest_date = date_order[-1]

            def build(goods_map):
                out = []
                for gn, by_date in goods_map.items():
                    values = [by_date.get(d, (0, 0))[0] for d in date_order]
                    money  = [by_date.get(d, (0, 0))[1] for d in date_order]
                    out.append({'name': gn, 'values': values, 'money': money,
                                'latest': by_date.get(latest_date, (0, 0))[0]})
                out.sort(key=lambda x: x['latest'], reverse=True)
                return out

            return jsonify({
                'dates': date_order,
                'exports': build(exp_goods),
                'imports': build(imp_goods),
                'latest_date': latest_date,
                'playthrough_id': playthrough_id,
            })

        @self.app.route('/api/economics/country/<country_tag>/state-list')
        def get_country_state_list(country_tag: str):
            """List of states with total production for a country.

            Query params:
                save_id (required)
            """
            save_id = request.args.get('save_id', '').strip()
            if not save_id:
                abort(400, 'save_id required')
            rows = self.db_manager.execute_query("""
                SELECT state_id, state_name, SUM(revenue) AS total_revenue
                FROM StateProduction
                WHERE save_id = ? AND country_tag = ?
                GROUP BY state_id, state_name
                ORDER BY total_revenue DESC
            """, (save_id, country_tag))
            out = []
            for r in rows:
                d = dict(r)
                d['total_revenue'] = round((d['total_revenue'] or 0) * WEEKS_PER_YEAR, 2)
                out.append(d)
            return jsonify(out)

        @self.app.route('/api/economics/country/<country_tag>/state-production')
        def get_country_state_production(country_tag: str):
            """Production breakdown for one state.

            Query params:
                save_id  (required)
                state_id (required)
            """
            save_id = request.args.get('save_id', '').strip()
            state_id = request.args.get('state_id', '').strip()
            if not save_id or not state_id:
                abort(400, 'save_id and state_id required')
            rows = self.db_manager.execute_query("""
                SELECT sp.good_name, sp.building_group, sp.revenue, p.price AS price
                FROM StateProduction sp
                LEFT JOIN GoodPrices p ON p.save_id = sp.save_id AND p.good_name = sp.good_name
                WHERE sp.save_id = ? AND sp.country_tag = ? AND sp.state_id = ?
                ORDER BY sp.revenue DESC
            """, (save_id, country_tag, state_id))
            out = []
            for r in rows:
                d = dict(r)
                price = d.pop('price', None) or 0
                d['revenue'] = round((d['revenue'] or 0) * WEEKS_PER_YEAR, 2)
                d['quantity'] = round(d['revenue'] / price, 2) if price else 0.0
                out.append(d)
            return jsonify(out)

        @self.app.route('/api/economics/gdp-by-good/<good_name>/top-countries')
        def get_good_top_countries(good_name: str):
            """Top 10 countries by revenue for a specific good in one save.

            Query params:
                save_id (required)
            """
            save_id = request.args.get('save_id', '').strip()
            if not save_id:
                abort(400, 'save_id required')

            rows = self.db_manager.execute_query("""
                SELECT
                    g.country_tag,
                    COALESCE(c.name, g.country_tag) AS country_name,
                    g.revenue
                FROM GDPByGood g
                LEFT JOIN Countries c
                    ON c.country_tag = g.country_tag
                    AND c.save_id    = g.save_id
                WHERE g.save_id   = ?
                  AND g.good_name = ?
                ORDER BY g.revenue DESC
                LIMIT 10
            """, (save_id, good_name))

            result = []
            for r in rows:
                d = dict(r)
                d['revenue'] = round((d['revenue'] or 0) * WEEKS_PER_YEAR, 2)
                d['flag_url'] = _flag_url(d['country_tag'])
                result.append(d)
            return jsonify(result)
