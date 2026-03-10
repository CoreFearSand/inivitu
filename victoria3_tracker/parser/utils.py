"""
Shared utilities for the parser package.

Centralises small helpers used across metrics_extractor, interest_group_extractor,
and data_processor so they are defined once and tested once.
"""

from typing import Any, Dict, List, Optional


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
