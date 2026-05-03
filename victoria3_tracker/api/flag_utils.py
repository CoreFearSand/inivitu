"""
Flag URL helpers for the Paradox wiki image CDN.

Shared between api/app.py and web/server.py — import from here, do not copy.
"""

import hashlib

_WIKI_FLAG_BASE = 'https://vic3.paradoxwikis.com/images'

# Tags that bypass the wiki CDN entirely and use a direct URL.
_DIRECT_FLAG_URLS: dict[str, str] = {
    'D99': 'https://www.flagdb.com/_next/image?url=https%3A%2F%2Fapi.flagdb.com%2Fflag%2Funited-nations&w=640&q=75',
}

# Country tags whose wiki flag filename differs from the standard Flag_{TAG}.png
_FLAG_EXCEPTIONS: dict[str, str] = {
    'GBR': 'GBR_uk',
    'AWS': 'red_flag',
    'VNZ': 'VNZ_monarchy',
    'NPU': 'PEU',
    'ZAI': 'YEM',
    'BCE': 'CEY',
}

# Country names where the wiki filename uses different capitalisation than the DB.
# Keys are lower-cased for case-insensitive lookup; values are the exact wiki stem.
_FLAG_NAME_OVERRIDES: dict[str, str] = {
    'hesse-kassel':         'Hesse-Kassel',
    'saxe-weimar':          'Saxe-Weimar',
    'dar al kuti':          'Dar_al_Kuti',
    'mecklenburg-strelitz': 'Mecklenburg-Strelitz',
    'saxe-meiningen':       'Saxe-Meiningen',
    'schaumburg-lippe':     'Schaumburg-Lippe',
    'saxe-coburg-gotha':    'Saxe-Coburg-Gotha',
}


def _wiki_url(filename: str) -> str:
    """Build a Paradox wiki CDN URL for *filename* using its MD5 path prefix."""
    md5 = hashlib.md5(filename.encode()).hexdigest()
    return f'{_WIKI_FLAG_BASE}/{md5[0]}/{md5[:2]}/{filename}'


def flag_url(tag: str) -> str:
    """Return the image URL for a country flag identified by its tag.

    Tags in _DIRECT_FLAG_URLS bypass the wiki CDN entirely.
    """
    if tag in _DIRECT_FLAG_URLS:
        return _DIRECT_FLAG_URLS[tag]
    suffix = _FLAG_EXCEPTIONS.get(tag, tag)
    return _wiki_url(f'Flag_{suffix}.png')


def flag_url_alt(name: str) -> str:
    """Return the wiki image URL for a country flag identified by its display name.

    Used as a fallback when tag-based lookup fails.  Checks _FLAG_NAME_OVERRIDES
    first to correct capitalisation quirks.
    """
    stem = _FLAG_NAME_OVERRIDES.get(name.lower(), name.replace(' ', '_'))
    return _wiki_url(f'{stem}.png')
