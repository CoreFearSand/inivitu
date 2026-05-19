"""
Interest group extraction for Victoria 3 Game Tracker.

Extracts political faction (interest group) data from parsed save data.
Victoria 3 stores interest groups in interest_groups.database, keyed
by numeric IG ID.  Each entry references its owner country via a numeric
country ID which is resolved to a 3-letter tag using country_manager.database.

Save structure (confirmed):
  interest_groups.database[n] = {
    'name': 'ig_armed_forces',      # instance name (may differ from definition)
    'definition': 'ig_armed_forces', # canonical IG type key ← use this
    'country': 1,                    # numeric country ID → resolve via id_to_tag
    'clout': 0.129,                  # political clout (float)
    'approval': 5,                   # approval rating (int)
    'in_government': True,           # only present when True
    'pops': [...],                   # list of pop IDs → len() = membership
  }
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from .utils import navigate_path, safe_float, safe_int

logger = logging.getLogger(__name__)


@dataclass
class InterestGroupData:
    """Container for a single interest group record."""
    country_tag: str          # 3-letter country tag
    ig_type: str              # e.g. 'ig_industrialists'
    clout: float = 0.0        # political clout 0-100
    approval: float = 0.0     # approval rating -100 to 100
    membership: int = 0       # number of pops in this IG
    in_government: bool = False


class InterestGroupExtractor:
    """Extracts interest group data from parsed Victoria 3 save data."""

    def __init__(self):
        self.extraction_stats: Dict[str, int] = {
            'igs_processed': 0,
            'igs_extracted': 0,
            'extraction_errors': 0,
        }

    def extract_all_interest_groups(
        self, parsed_data: Dict[str, Any]
    ) -> List[InterestGroupData]:
        """Extract all interest groups from parsed save data.

        Args:
            parsed_data: Top-level parsed save dictionary.

        Returns:
            List of InterestGroupData objects (one per country × IG type).
        """
        self.extraction_stats = {
            'igs_processed': 0,
            'igs_extracted': 0,
            'extraction_errors': 0,
        }

        results: List[InterestGroupData] = []

        try:
            id_to_tag = self._build_id_to_tag_map(parsed_data)
            if not id_to_tag:
                logger.warning("InterestGroupExtractor: could not build country ID map")
                return results

            # Fall back to legacy key names for compatibility.
            ig_manager = (
                parsed_data.get('interest_groups')
                or parsed_data.get('interest_group_manager')
                or parsed_data.get('ig_manager')
            )
            ig_db = {}
            if isinstance(ig_manager, dict):
                ig_db = ig_manager.get('database') or ig_manager.get('data') or {}

            if not ig_db:
                top_keys = [k for k in parsed_data.keys() if 'interest' in k.lower()
                            or 'ig_' in k.lower() or k.startswith('political')]
                logger.warning(
                    "InterestGroupExtractor: 'interest_groups' not found "
                    f"or empty. Keys with 'interest/ig/political': {top_keys}. "
                    f"All top-level keys (first 30): {list(parsed_data.keys())[:30]}"
                )
                return results

            logger.info(f"Extracting interest groups from {len(ig_db)} entries")

            for ig_id, ig_data in ig_db.items():
                try:
                    self.extraction_stats['igs_processed'] += 1

                    if not isinstance(ig_data, dict):
                        continue

                    country_numeric_id = (
                        ig_data.get('country')
                        or ig_data.get('owner')
                        or ig_data.get('country_id')
                        or ig_data.get('nation')
                    )
                    if country_numeric_id is None:
                        logger.debug(f"IG {ig_id}: no country field, keys={list(ig_data.keys())}")
                        continue
                    country_tag = id_to_tag.get(str(country_numeric_id))
                    if not country_tag:
                        continue

                    # IG type — 'definition' is the canonical field in V3 saves;
                    # fall back to legacy field names for compatibility.
                    ig_type = (
                        ig_data.get('definition')
                        or ig_data.get('type')
                        or ig_data.get('ig_type')
                        or ig_data.get('kind')
                    )
                    if not ig_type or not isinstance(ig_type, str):
                        logger.debug(f"IG {ig_id}: no type field, keys={list(ig_data.keys())}")
                        continue

                    clout    = safe_float(ig_data.get('clout', 0))
                    # approval is an int in the save but we store as float
                    approval = safe_float(
                        ig_data.get('approval', 0)
                        if ig_data.get('approval') is not None
                        else ig_data.get('country_approval', 0)
                    )
                    # pops is a list of pop IDs; len() gives membership count
                    pops = ig_data.get('pops', [])
                    membership = len(pops) if isinstance(pops, list) else safe_int(
                        ig_data.get('membership') or ig_data.get('member_count', 0)
                    )
                    # in_government is only present in the dict when True
                    in_gov = bool(ig_data.get('in_government', False))

                    results.append(InterestGroupData(
                        country_tag=country_tag,
                        ig_type=ig_type,
                        clout=clout,
                        approval=approval,
                        membership=membership,
                        in_government=in_gov,
                    ))
                    self.extraction_stats['igs_extracted'] += 1

                except Exception as e:
                    self.extraction_stats['extraction_errors'] += 1
                    logger.warning(f"Error extracting interest group {ig_id}: {e}")
                    continue

            logger.info(
                f"Interest group extraction complete: {len(results)} IGs extracted "
                f"({self.extraction_stats['igs_processed']} processed, "
                f"{self.extraction_stats['extraction_errors']} errors)"
            )

        except Exception as e:
            logger.error(f"Error during interest group extraction: {e}")

        return results

    def get_extraction_stats(self) -> Dict[str, int]:
        """Return statistics from the most recent extraction run."""
        return self.extraction_stats.copy()

    def _build_id_to_tag_map(self, parsed_data: Dict[str, Any]) -> Dict[str, str]:
        """Build a mapping from numeric country database-ID to 3-letter tag."""
        mapping: Dict[str, str] = {}
        try:
            db = navigate_path(parsed_data, ['country_manager', 'database']) or {}
            for numeric_id, country_data in db.items():
                if not isinstance(country_data, dict):
                    continue
                tag = country_data.get('definition')
                if tag and isinstance(tag, str) and len(tag) == 3 and tag.isalnum():
                    mapping[str(numeric_id)] = tag
        except Exception as e:
            logger.warning(f"InterestGroupExtractor: error building ID map: {e}")
        return mapping
