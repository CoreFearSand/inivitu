"""
Law history extraction for Victoria 3 Game Tracker.

Reads laws.database from the parsed save and builds a chronological
list of law changes per country. Since the save retains all historical
law entries (not just the currently active ones), a single extraction
gives the complete law history.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from .law_definitions import LAW_GROUPS, LAW_TO_GROUP, LAW_LABELS

logger = logging.getLogger(__name__)


@dataclass
class LawChange:
    country_tag: str
    law_key: str
    law_group: str
    law_label: str
    group_label: str
    group_color: str
    category: str
    activation_date: Optional[str]   # ISO YYYY-MM-DD
    replaced_law: Optional[str]
    is_active: bool


class LawExtractor:
    """Extract law change history from a parsed Victoria 3 save."""

    def extract(self, parsed_data: Dict[str, Any]) -> List[LawChange]:
        """Return all law changes across all countries, sorted by date."""
        id_to_tag = self._build_id_to_tag(parsed_data)
        laws_db = parsed_data.get('laws', {}).get('database', {})

        changes: List[LawChange] = []
        skipped_unknown = 0

        for entry in laws_db.values():
            if not isinstance(entry, dict):
                continue

            law_key = entry.get('law', '')
            if not law_key:
                continue

            group_key = LAW_TO_GROUP.get(law_key)

            country_id = entry.get('country')
            tag = id_to_tag.get(str(country_id)) if country_id is not None else None
            if not tag:
                continue

            raw_date = entry.get('activation_date')
            iso_date = self._fmt_date(raw_date)

            if group_key is None:
                skipped_unknown += 1
                logger.debug('Unknown law key (not in LAW_GROUPS): %s', law_key)
                changes.append(LawChange(
                    country_tag=tag,
                    law_key=law_key,
                    law_group='_unknown',
                    law_label=law_key,
                    group_label='Unknown',
                    group_color='#9E9E9E',
                    category='unknown',
                    activation_date=iso_date,
                    replaced_law=entry.get('replace'),
                    is_active=bool(entry.get('active', False)),
                ))
                continue

            group = LAW_GROUPS[group_key]

            changes.append(LawChange(
                country_tag=tag,
                law_key=law_key,
                law_group=group_key,
                law_label=LAW_LABELS.get(law_key, law_key),
                group_label=group['label'],
                group_color=group['color'],
                category=group['category'],
                activation_date=iso_date,
                replaced_law=entry.get('replace'),
                is_active=bool(entry.get('active', False)),
            ))

        if skipped_unknown:
            logger.info('Stored %d law entries with unrecognised keys as _unknown', skipped_unknown)

        changes.sort(key=lambda c: (c.activation_date or '', c.law_group))
        logger.info('Extracted %d law changes across %d countries',
                    len(changes),
                    len({c.country_tag for c in changes}))
        return changes

    def _build_id_to_tag(self, parsed_data: Dict[str, Any]) -> Dict[str, str]:
        countries_db = parsed_data.get('country_manager', {}).get('database', {})
        result = {}
        for cid, cdata in countries_db.items():
            if isinstance(cdata, dict):
                tag = cdata.get('definition', '')
                if tag and len(tag) == 3:
                    result[str(cid)] = tag.upper()
        return result

    @staticmethod
    def _fmt_date(raw: Any) -> Optional[str]:
        if not raw or not isinstance(raw, str):
            return None
        if '.' in raw:
            parts = raw.split('.')
            try:
                y, m, d = parts[0], parts[1], parts[2]
                return f'{y}-{m.zfill(2)}-{d.zfill(2)}'
            except IndexError:
                return None
        if '-' in raw:
            return raw
        return None
