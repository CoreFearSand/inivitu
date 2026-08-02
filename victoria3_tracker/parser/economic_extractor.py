"""
Economic data extractor for Victoria 3 Game Tracker.

Extracts GDP-by-good, trade balance per market, and GDP ownership data from
parsed save data.

Data paths (from rakaly json output):
  GDP by good:  building_manager.database[N].output_goods.goods[good_id_str].value × price
  Trade:        states.database[N].trade.goods[good_id_str].value  (net quantity)
  Ownership:    building_ownership_manager.database[N].{identity, building, levels}
"""

import logging
from collections import defaultdict
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .utils import navigate_path, safe_float, safe_int

logger = logging.getLogger(__name__)

# Good ID → canonical name. 0-based index into 00_goods.txt.
GOOD_ID_TO_NAME: Dict[int, str] = {
    0: "ammunition", 1: "small_arms", 2: "artillery", 3: "tanks",
    4: "aeroplanes", 5: "manowars", 6: "ironclads", 7: "grain",
    8: "fish", 9: "fabric", 10: "wood", 11: "groceries",
    12: "clothes", 13: "furniture", 14: "paper", 15: "services",
    16: "transportation", 17: "electricity", 18: "merchant_marine",
    19: "clippers", 20: "steamers", 21: "silk", 22: "dye",
    23: "sulfur", 24: "coal", 25: "iron", 26: "lead",
    27: "hardwood", 28: "rubber", 29: "oil", 30: "engines",
    31: "steel", 32: "glass", 33: "fertilizer", 34: "tools",
    35: "explosives", 36: "porcelain", 37: "meat", 38: "fruit",
    39: "liquor", 40: "wine", 41: "tea", 42: "coffee",
    43: "sugar", 44: "tobacco", 45: "opium", 46: "automobiles",
    47: "telephones", 48: "radios", 49: "luxury_clothes",
    50: "luxury_furniture", 51: "gold", 52: "fine_art",
}

# Building type → building group (vanilla V3 1.x).
# Anything not in this dict falls back to "bg_unknown".
BUILDING_TO_GROUP: Dict[str, str] = {
    # Agriculture
    "building_wheat_farm": "bg_agriculture",
    "building_rye_farm": "bg_agriculture",
    "building_maize_farm": "bg_agriculture",
    "building_rice_farm": "bg_agriculture",
    "building_millet_farm": "bg_agriculture",
    "building_banana_plantation": "bg_agriculture",
    "building_cotton_plantation": "bg_agriculture",
    "building_dye_plantation": "bg_agriculture",
    "building_opium_plantation": "bg_agriculture",
    "building_silk_plantation": "bg_agriculture",
    "building_tobacco_plantation": "bg_agriculture",
    "building_sugar_plantation": "bg_agriculture",
    "building_coffee_plantation": "bg_agriculture",
    "building_tea_plantation": "bg_agriculture",
    "building_vineyard": "bg_agriculture",
    "building_rubber_plantation": "bg_agriculture",
    "building_fishing_wharf": "bg_agriculture",
    # Ranching
    "building_livestock_ranch": "bg_ranching",
    # Mining
    "building_coal_mine": "bg_mining",
    "building_iron_mine": "bg_mining",
    "building_lead_mine": "bg_mining",
    "building_gold_mine": "bg_mining",
    "building_gold_field": "bg_mining",
    "building_sulfur_mine": "bg_mining",
    "building_oil_rig": "bg_mining",
    # Logging / Whaling
    "building_logging_camp": "bg_logging",
    "building_whaling_station": "bg_whaling",
    # Light industry
    "building_textile_mill": "bg_light_industry",
    "building_furniture_manufactory": "bg_light_industry",
    "building_paper_mill": "bg_light_industry",
    "building_glassworks": "bg_light_industry",
    "building_tooling_workshop": "bg_light_industry",
    "building_food_industry": "bg_light_industry",
    # Heavy industry
    "building_steel_mill": "bg_heavy_industry",
    "building_munition_plant": "bg_heavy_industry",
    "building_artillery_foundry": "bg_heavy_industry",
    "building_arms_industry": "bg_heavy_industry",
    "building_shipyard": "bg_heavy_industry",
    "building_motor_industry": "bg_heavy_industry",
    "building_explosives_factory": "bg_heavy_industry",
    "building_chemical_plant": "bg_heavy_industry",
    # Urban / services
    "building_urban_center": "bg_urban_center",
    "building_power_plant": "bg_power",
    # Infrastructure
    "building_port": "bg_infrastructure",
    "building_railway": "bg_infrastructure",
    "building_construction_sector": "bg_infrastructure",
    # Military
    "building_barrack": "bg_military",
    "building_conscription_center": "bg_military",
    "building_naval_fortification": "bg_military",
    "building_army_logistics_center": "bg_military",
    "building_naval_logistics_center": "bg_military",
    "building_naval_administration": "bg_military",
    # Institutions / education
    "building_university": "bg_arts_institutions",
    "building_art_academy": "bg_arts_institutions",
    "building_government_administration": "bg_government",
    # Finance / trade
    "building_financial_district": "bg_financial",
    "building_trade_center": "bg_trade",
    # Subsistence
    "building_manor_house": "bg_subsistence",
    "building_subsistence_farm": "bg_subsistence",
    "building_subsistence_fishing_village": "bg_subsistence",
    "building_subsistence_orchard": "bg_subsistence",
    "building_subsistence_pasture": "bg_subsistence",
    "building_subsistence_rice_farm": "bg_subsistence",
    # Monuments (treated as misc)
    "building_monument": "bg_monuments",
}


def _iter_db(db: Any) -> Iterator[Tuple[str, Any]]:
    """Yield (id_str, entry) pairs from a vic3 'database' value (dict or list)."""
    if isinstance(db, dict):
        yield from db.items()
    elif isinstance(db, list):
        for i, item in enumerate(db):
            if item is not None:
                yield str(i), item


def _iter_goods(goods: Any) -> Iterator[Tuple[int, float]]:
    """Yield (good_id, quantity) from output_goods.goods or trade.goods.

    The rakaly format is: {good_id_str: {value: qty, ...}, ...}
    The good_id is the DICT KEY, not a field inside the value object.
    """
    if not isinstance(goods, dict):
        return
    for gid_str, entry in goods.items():
        if isinstance(entry, dict):
            val = entry.get("value")
            if val is not None:
                yield safe_int(gid_str), safe_float(val)


class EconomicExtractor:
    """Extracts GDPByGood, TradeBalance, and GDPOwnership from parsed Vic3 save data."""

    def __init__(self) -> None:
        self._country_id_to_tag: Dict[str, str] = {}

    def extract_all(self, parsed_data: Dict[str, Any]) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict], List[Dict]]:
        """Extract all economic datasets.

        Returns:
            (gdp_by_good_rows, trade_balance_rows, gdp_ownership_rows,
             state_production_rows, good_price_rows)
        """
        logger.info("Building economic lookup tables…")
        self._country_id_to_tag = self._build_country_id_to_tag(parsed_data)
        state_to_country_id, state_names = self._build_state_to_country_id(parsed_data)
        country_id_to_market_tag = self._build_country_to_market_tag(parsed_data)
        prices = self._extract_prices(parsed_data)

        building_db = navigate_path(parsed_data, ["building_manager", "database"]) or {}
        building_cache = self._build_building_cache(building_db, state_to_country_id)
        ownership_db = navigate_path(parsed_data, ["building_ownership_manager", "database"]) or {}

        logger.info("Extracting GDP by good…")
        gdp_by_good = self._extract_gdp_by_good(building_db, building_cache, prices)

        logger.info("Extracting trade balances…")
        trade_balance = self._extract_trade_balance(
            parsed_data, state_to_country_id, country_id_to_market_tag
        )

        logger.info("Extracting GDP ownership…")
        gdp_ownership = self._extract_gdp_ownership(building_cache, ownership_db)

        logger.info("Extracting state production…")
        state_production = self._extract_state_production(
            building_db, building_cache, prices, state_names
        )

        good_prices = [
            {"good_name": GOOD_ID_TO_NAME[gid], "price": round(p, 4)}
            for gid, p in prices.items()
            if gid in GOOD_ID_TO_NAME
        ]

        logger.info(
            f"Economic extraction complete: {len(gdp_by_good)} GDP-by-good, "
            f"{len(trade_balance)} trade, {len(gdp_ownership)} ownership, "
            f"{len(state_production)} state-prod, {len(good_prices)} prices."
        )
        return gdp_by_good, trade_balance, gdp_ownership, state_production, good_prices

    # ------------------------------------------------------------------
    # Lookup table builders
    # ------------------------------------------------------------------

    def _build_country_id_to_tag(self, parsed_data: Dict) -> Dict[str, str]:
        db = navigate_path(parsed_data, ["country_manager", "database"]) or {}
        result: Dict[str, str] = {}
        for cid, cdata in _iter_db(db):
            if not isinstance(cdata, dict):
                continue
            tag = cdata.get("definition")
            if isinstance(tag, str) and len(tag) == 3:
                result[cid] = tag
        return result

    def _build_state_to_country_id(self, parsed_data: Dict) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Returns (state_id → country_id, state_id → display_name)."""
        db = navigate_path(parsed_data, ["states", "database"]) or {}
        state_to_country: Dict[str, str] = {}
        state_names: Dict[str, str] = {}
        for sid, sdata in _iter_db(db):
            if not isinstance(sdata, dict):
                continue
            cid = sdata.get("country")
            if cid is not None:
                state_to_country[sid] = str(cid)
            defn = sdata.get("definition")
            if isinstance(defn, str) and defn:
                # "STATE_BERNE" → "Berne"
                name = defn.replace("STATE_", "").replace("_", " ").title()
            else:
                name = f"State {sid}"
            state_names[sid] = name
        return state_to_country, state_names

    def _build_country_to_market_tag(self, parsed_data: Dict) -> Dict[str, str]:
        """country_id → market owner tag."""
        country_db = navigate_path(parsed_data, ["country_manager", "database"]) or {}
        market_db = navigate_path(parsed_data, ["market_manager", "database"]) or {}

        market_owner: Dict[str, str] = {}
        for mid, mdata in _iter_db(market_db):
            if not isinstance(mdata, dict):
                continue
            owner_id = mdata.get("owner")
            if owner_id is not None:
                tag = self._country_id_to_tag.get(str(owner_id))
                if tag:
                    market_owner[mid] = tag

        result: Dict[str, str] = {}
        for cid, cdata in _iter_db(country_db):
            if not isinstance(cdata, dict):
                continue
            market_id = cdata.get("market")
            if market_id is not None:
                owner_tag = market_owner.get(str(market_id))
                if owner_tag:
                    result[cid] = owner_tag
        return result

    def _extract_prices(self, parsed_data: Dict) -> Dict[int, float]:
        """good_id → price. Combines world_market price_trend with prices imputed
        from single-good buildings (goods_sales / output_quantity)."""
        channels = navigate_path(
            parsed_data,
            ["market_manager", "world_market", "price_trend", "channels"],
        )
        # Seed with any available world_market channel prices.
        # channels is a dict: {good_id_str: {index: <internal const>, values: [...]}}
        # The dict KEY is the good_id. The 'index' field is an internal constant
        # (e.g. 547) shared across all channels — it is NOT the good_id.
        prices: Dict[int, float] = {}
        if isinstance(channels, dict):
            for gid_str, channel in channels.items():
                if not isinstance(channel, dict):
                    continue
                values = channel.get("values")
                if isinstance(values, list) and values:
                    prices[safe_int(gid_str)] = safe_float(values[-1])
        elif isinstance(channels, list):
            for i, channel in enumerate(channels):
                if isinstance(channel, dict):
                    values = channel.get("values")
                    if isinstance(values, list) and values:
                        prices[safe_int(i)] = safe_float(values[-1])

        # The world_market channel price is the game's authoritative reference price
        # (it matches the in-game "World Market" figure). Only impute a price from
        # buildings for goods that have NO world_market channel — the non-tradeables
        # services (15), transportation (16), electricity (17), gold (51).
        #
        # We deliberately do NOT override world_market with a building average:
        # goods_sales/quantity averaged across every producer worldwide is skewed by
        # oversupplied colonial estates (e.g. sugar plantations dumping at £7.50),
        # which dragged prices far below the true market value.
        building_db = navigate_path(parsed_data, ["building_manager", "database"]) or {}
        imputed: Dict[int, List[float]] = defaultdict(list)
        for _, bdata in _iter_db(building_db):
            if not isinstance(bdata, dict):
                continue
            gs = safe_float(bdata.get("goods_sales", 0.0))
            if gs <= 0:
                continue
            goods_node = navigate_path(bdata, ["output_goods", "goods"])
            if not goods_node:
                continue
            goods = list(_iter_goods(goods_node))
            if len(goods) == 1:
                gid, qty = goods[0]
                if qty > 0:
                    imputed[gid].append(gs / qty)

        for gid, price_list in imputed.items():
            # Fallback only: fill goods the world market does not price.
            if gid not in prices:
                prices[gid] = sum(price_list) / len(price_list)

        return prices

    def _build_building_cache(
        self,
        building_db: Any,
        state_to_country_id: Dict[str, str],
    ) -> Dict[str, Dict]:
        """building_index_str → {country_tag, building_type, building_group, total_level, goods_sales}"""
        cache: Dict[str, Dict] = {}
        for bid, bdata in _iter_db(building_db):
            if not isinstance(bdata, dict):
                continue
            state_id = str(bdata.get("state", ""))
            country_id = state_to_country_id.get(state_id, "")
            country_tag = self._country_id_to_tag.get(country_id, "")
            # Field name in rakaly output is 'building' (string), NOT 'building_type'
            btype = bdata.get("building", "")
            bgroup = BUILDING_TO_GROUP.get(str(btype), "bg_unknown")
            # Field is 'levels' (plural), NOT 'level'
            total_level = safe_int(bdata.get("levels", 0))
            goods_sales = safe_float(bdata.get("goods_sales", 0.0))
            cache[bid] = {
                "country_tag": country_tag,
                "state_id": state_id,
                "building_type": str(btype),
                "building_group": bgroup,
                "total_level": total_level,
                "goods_sales": goods_sales,
            }
        return cache

    # ------------------------------------------------------------------
    # Extractors
    # ------------------------------------------------------------------

    def _extract_gdp_by_good(
        self,
        building_db: Any,
        building_cache: Dict[str, Dict],
        prices: Dict[int, float],
    ) -> List[Dict]:
        # Accumulate: (country_tag, good_name) → (total_revenue, dominant_bgroup)
        # We aggregate by (country_tag, good_name) to respect the UNIQUE constraint.
        rev_acc: Dict[Tuple[str, str], float] = defaultdict(float)
        grp_acc: Dict[Tuple[str, str, str], float] = defaultdict(float)  # for dominant group

        for bid, bdata in _iter_db(building_db):
            if not isinstance(bdata, dict):
                continue
            bc = building_cache.get(bid, {})
            country_tag = bc.get("country_tag", "")
            if not country_tag:
                continue
            bgroup = bc.get("building_group", "bg_unknown")

            goods_node = navigate_path(bdata, ["output_goods", "goods"])
            if not goods_node:
                continue

            for good_id, qty in _iter_goods(goods_node):
                good_name = GOOD_ID_TO_NAME.get(good_id)
                if not good_name or qty <= 0:
                    continue
                price = prices.get(good_id, 0.0)
                revenue = qty * price
                if revenue > 0:
                    rev_acc[(country_tag, good_name)] += revenue
                    grp_acc[(country_tag, good_name, bgroup)] += revenue

        # Determine dominant building group per (country, good)
        result = []
        for (ct, gn), rev in rev_acc.items():
            if rev <= 0:
                continue
            # Pick building group that contributed the most revenue for this good
            best_grp = max(
                (g for (c, n, g) in grp_acc if c == ct and n == gn),
                key=lambda g: grp_acc[(ct, gn, g)],
                default="bg_unknown",
            )
            result.append({
                "country_tag": ct,
                "good_name": gn,
                "building_group": best_grp,
                "revenue": round(rev, 4),
            })
        return result

    def _extract_trade_balance(
        self,
        parsed_data: Dict,
        state_to_country_id: Dict[str, str],
        country_id_to_market_tag: Dict[str, str],
    ) -> List[Dict]:
        state_db = navigate_path(parsed_data, ["states", "database"]) or {}
        acc: Dict[Tuple[str, str], float] = defaultdict(float)

        for sid, sdata in _iter_db(state_db):
            if not isinstance(sdata, dict):
                continue
            country_id = state_to_country_id.get(sid, "")
            market_tag = country_id_to_market_tag.get(country_id, "")
            if not market_tag:
                continue

            trade_node = sdata.get("trade", {})
            if not isinstance(trade_node, dict):
                continue
            goods_node = trade_node.get("goods")
            for good_id, net_qty in _iter_goods(goods_node):
                good_name = GOOD_ID_TO_NAME.get(good_id)
                if not good_name or net_qty == 0.0:
                    continue
                acc[(market_tag, good_name)] += net_qty

        return [
            {
                "market_tag": mt,
                "good_name": gn,
                "net_quantity": round(nq, 4),
            }
            for (mt, gn), nq in acc.items()
            if nq != 0.0
        ]

    def _extract_state_production(
        self,
        building_db: Any,
        building_cache: Dict[str, Dict],
        prices: Dict[int, float],
        state_names: Dict[str, str],
    ) -> List[Dict]:
        """Per-state production: (country_tag, state_id, good_name) → revenue."""
        rev_acc: Dict[Tuple[str, str, str], float] = defaultdict(float)
        grp_acc: Dict[Tuple[str, str, str, str], float] = defaultdict(float)

        for bid, bdata in _iter_db(building_db):
            if not isinstance(bdata, dict):
                continue
            bc = building_cache.get(bid, {})
            country_tag = bc.get("country_tag", "")
            state_id = bc.get("state_id", "")
            if not country_tag or not state_id:
                continue
            bgroup = bc.get("building_group", "bg_unknown")

            goods_node = navigate_path(bdata, ["output_goods", "goods"])
            if not goods_node:
                continue

            for good_id, qty in _iter_goods(goods_node):
                good_name = GOOD_ID_TO_NAME.get(good_id)
                if not good_name or qty <= 0:
                    continue
                price = prices.get(good_id, 0.0)
                revenue = qty * price
                if revenue > 0:
                    key = (country_tag, state_id, good_name)
                    rev_acc[key] += revenue
                    grp_acc[(country_tag, state_id, good_name, bgroup)] += revenue

        result = []
        for (ct, sid, gn), rev in rev_acc.items():
            if rev <= 0:
                continue
            best_grp = max(
                (g for (c, s, n, g) in grp_acc if c == ct and s == sid and n == gn),
                key=lambda g: grp_acc[(ct, sid, gn, g)],
                default="bg_unknown",
            )
            result.append({
                "country_tag": ct,
                "state_id": sid,
                "state_name": state_names.get(sid, f"State {sid}"),
                "good_name": gn,
                "building_group": best_grp,
                "revenue": round(rev, 4),
            })
        return result

    def _extract_gdp_ownership(
        self,
        building_cache: Dict[str, Dict],
        ownership_db: Any,
    ) -> List[Dict]:
        """Iterate building_ownership_manager.database to assign GDP shares to investors.

        Each ownership entry has:
          - 'building': index of the owned productive building (in building_manager.database)
          - 'levels': how many levels this investor owns
          - 'identity': {'country': int} for state ownership OR {'building': int} for private
        """
        acc: Dict[Tuple[str, str, str], float] = defaultdict(float)

        for _, odata in _iter_db(ownership_db):
            if not isinstance(odata, dict):
                continue

            # Resolve the owned productive building
            owned_bid = str(odata.get("building", ""))
            owned_bc = building_cache.get(owned_bid, {})
            host_tag = owned_bc.get("country_tag", "")
            total_level = owned_bc.get("total_level", 0)
            goods_sales = owned_bc.get("goods_sales", 0.0)
            bgroup = owned_bc.get("building_group", "bg_unknown")

            if not host_tag or total_level <= 0 or goods_sales <= 0:
                continue

            owned_levels = safe_int(odata.get("levels", 0))
            if owned_levels <= 0:
                continue

            # Resolve investor country tag from identity
            identity = odata.get("identity", {})
            if not isinstance(identity, dict):
                continue

            if "country" in identity:
                # State/government ownership — investor is directly a country
                investor_tag = self._country_id_to_tag.get(str(identity["country"]), "")
            elif "building" in identity:
                # Private ownership via a financial district building
                fin_bid = str(identity["building"])
                fin_bc = building_cache.get(fin_bid, {})
                investor_tag = fin_bc.get("country_tag", "")
            else:
                continue

            if not investor_tag:
                continue

            gdp_share = (owned_levels / total_level) * goods_sales
            acc[(host_tag, investor_tag, bgroup)] += gdp_share

        return [
            {
                "country_tag": ht,
                "investor_tag": it,
                "building_group": bg,
                "gdp_owned": round(gdp, 4),
            }
            for (ht, it, bg), gdp in acc.items()
            if gdp > 0
        ]
