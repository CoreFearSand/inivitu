"""
Shared utilities for the parser package.

Centralises small helpers used across metrics_extractor, interest_group_extractor,
and data_processor so they are defined once and tested once.
"""

from typing import Any, Dict, List, Optional


# Vic3 country power-rank strings (from country_rankings.country_rankings) →
# numeric prestige tier (1 = most powerful) used by the 'prestige_tier' metric.
COUNTRY_RANK_TIER: Dict[str, int] = {
    'great_power': 1,
    'major_power': 2,
    'unrecognized_major_power': 2,
    'minor_power': 3,
    'unrecognized_regional_power': 3,
    'insignificant_power': 4,
    'unrecognized_power': 4,
    'decentralized_power': 5,
}

# Human-readable label for each rank string.
COUNTRY_RANK_LABEL: Dict[str, str] = {
    'great_power': 'Great Power',
    'major_power': 'Major Power',
    'unrecognized_major_power': 'Unrecognized Major Power',
    'minor_power': 'Minor Power',
    'unrecognized_regional_power': 'Unrecognized Regional Power',
    'insignificant_power': 'Insignificant Power',
    'unrecognized_power': 'Unrecognized Power',
    'decentralized_power': 'Decentralized Power',
}


def build_country_rank_map(parsed_data: Dict) -> Dict[str, str]:
    """Map numeric country id (str) → game power-rank string.

    Sourced from country_rankings.country_rankings (the game's own ranking),
    so ranks are authoritative rather than approximated from prestige.
    """
    ranks = navigate_path(parsed_data, ['country_rankings', 'country_rankings'])
    result: Dict[str, str] = {}
    if isinstance(ranks, list):
        for entry in ranks:
            if isinstance(entry, dict) and entry.get('country') is not None and entry.get('rank'):
                result[str(entry['country'])] = entry['rank']
    return result


def navigate_path(data: Dict, path: List[str]) -> Any:
    """Return the value at *path* inside a nested dict, or None on any miss."""
    try:
        current = data
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        return current
    except (KeyError, TypeError):
        return None


def parse_game_date(raw: Any) -> Optional[str]:
    """Normalise a Victoria 3 game date to ISO format (YYYY-MM-DD).

    Accepts 'YYYY.MM.DD' (V3 native) or 'YYYY-MM-DD' (already ISO).
    Returns None on any failure.
    """
    if not isinstance(raw, str):
        return None
    if '.' in raw:
        try:
            y, m, d = raw.split('.')
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        except ValueError:
            return None
    if '-' in raw:
        return raw
    return None


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert *value* to float, returning *default* on failure or None input."""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Convert *value* to int, returning *default* on failure or None input."""
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default
