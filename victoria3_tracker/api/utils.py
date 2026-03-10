"""
Shared utilities for API endpoint classes.
"""

from flask import abort


def validate_tag(tag: str) -> str:
    """Validate a country tag and return it uppercased, or abort(400).

    Accepts 2-4 alphanumeric characters (covers standard 3-letter tags and
    any modded 2- or 4-letter tags).
    """
    if not tag or not tag.isalnum() or len(tag) > 4:
        abort(400)
    return tag.upper()
