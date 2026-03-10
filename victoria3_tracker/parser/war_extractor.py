"""
War data extraction for Victoria 3 Game Tracker.

Extracts war information from parsed save data using the actual save file structure:
- Wars come from war_manager.database (keyed by numeric war ID)
- Attacker/defender split comes from diplomatic_plays.database (initiator vs target/targets)
- Country numeric IDs are resolved to 3-letter tags via country_manager.database[id]['definition']
- Casualties/costs come from the diplomatic play's casualties and country_records arrays
- Battles come from battle_manager.database (entries that are not the string "none")
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ONGOING_DATE = '1.1.1'
NULL_ID = 4294967295  # 0xFFFFFFFF = invalid/null in Victoria 3


@dataclass
class WarParticipant:
    """Container for a single country's participation in a war."""
    country_tag: str
    side: str               # 'attacker' or 'defender'
    war_support: int        # -100 to 100
    casualties: float       # fractional attrition deaths
    materiel_cost: float    # sum of goods consumed (from country_records)
    wage_cost: float        # wage cost of war (from country_records)


@dataclass
class Battle:
    """Container for a single battle record."""
    battle_id: str
    attacker_tag: str
    defender_tag: str
    occurred_on: Optional[str] = None
    ended_on: Optional[str] = None
    location_province_id: Optional[str] = None
    attacker_casualties: float = 0.0
    defender_casualties: float = 0.0
    attacker_battalions_lost: int = 0
    defender_battalions_lost: int = 0
    winner_tag: Optional[str] = None
    name: Optional[str] = None
    battle_type: str = 'land'
    status: str = 'unknown'


@dataclass
class WarData:
    """Container for a complete war record."""
    save_war_id: str                    # numeric war ID from save file
    war_type: str                       # diplomatic play type, e.g. 'dp_native_uprising'
    started_on: str                     # formatted YYYY-MM-DD
    status: str                         # 'ongoing', 'ended', 'white_peace'
    participants: List[WarParticipant] = field(default_factory=list)
    battles: List[Battle] = field(default_factory=list)
    strategic_region: Optional[str] = None
    diplomatic_play_id: Optional[str] = None
    objective_state_id: Optional[str] = None
    escalation: int = 0
    initiator_maneuvers: int = 0
    target_maneuvers: int = 0
    ended_on: Optional[str] = None


class WarExtractor:
    """Extracts war data from parsed Victoria 3 save data."""

    def __init__(self):
        self.extraction_stats = {
            'wars_processed': 0,
            'wars_extracted': 0,
            'participants_extracted': 0,
            'battles_extracted': 0,
            'extraction_errors': 0
        }

    def extract_all_wars(self, parsed_data: Dict[str, Any]) -> List[WarData]:
        """Extract all wars from parsed save data.

        Args:
            parsed_data: Full parsed save data dictionary

        Returns:
            List of WarData objects
        """
        self.extraction_stats = {
            'wars_processed': 0,
            'wars_extracted': 0,
            'participants_extracted': 0,
            'battles_extracted': 0,
            'extraction_errors': 0
        }

        # Build country numeric ID -> 3-letter tag mapping
        id_to_tag = self._build_id_to_tag(parsed_data)
        logger.debug(f"Built ID-to-tag map with {len(id_to_tag)} entries")

        war_manager = parsed_data.get('war_manager', {})
        wars_db = war_manager.get('database', {})

        if not wars_db:
            logger.info("No war data found in save file")
            return []

        plays_db = parsed_data.get('diplomatic_plays', {}).get('database', {})
        battles_db = parsed_data.get('battle_manager', {}).get('database', {})

        wars = []
        for war_key, war_data in wars_db.items():
            self.extraction_stats['wars_processed'] += 1
            try:
                if not isinstance(war_data, dict):
                    continue

                war_info = self._extract_war(war_key, war_data, plays_db, battles_db, id_to_tag)
                if war_info:
                    wars.append(war_info)
                    self.extraction_stats['wars_extracted'] += 1
                    self.extraction_stats['participants_extracted'] += len(war_info.participants)
                    self.extraction_stats['battles_extracted'] += len(war_info.battles)

            except Exception as e:
                self.extraction_stats['extraction_errors'] += 1
                logger.warning(f"Error extracting war {war_key}: {e}", exc_info=True)

        logger.info(f"Extracted {len(wars)} wars "
                    f"({self.extraction_stats['participants_extracted']} participants, "
                    f"{self.extraction_stats['battles_extracted']} battles)")
        return wars

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_id_to_tag(self, parsed_data: Dict[str, Any]) -> Dict[str, str]:
        """Build numeric country ID -> 3-letter tag mapping."""
        countries_db = parsed_data.get('country_manager', {}).get('database', {})
        result = {}
        for cid, cdata in countries_db.items():
            if isinstance(cdata, dict):
                tag = cdata.get('definition')
                if tag and isinstance(tag, str) and len(tag) == 3:
                    result[str(cid)] = tag.upper()
        return result

    def _fmt_date(self, raw: Any) -> Optional[str]:
        """Convert 'YYYY.M.D[.H]' to 'YYYY-MM-DD'. Returns None for invalid/ongoing dates."""
        if not raw or raw == ONGOING_DATE:
            return None
        try:
            if isinstance(raw, str) and '.' in raw:
                parts = raw.split('.')
                year, month, day = parts[0], parts[1], parts[2]  # ignore hours if present
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            if isinstance(raw, str) and '-' in raw:
                return raw
        except Exception:
            pass
        return None

    def _extract_war(self, war_key: str, war_data: Dict[str, Any],
                     plays_db: Dict[str, Any], battles_db: Dict[str, Any],
                     id_to_tag: Dict[str, str]) -> Optional[WarData]:
        """Extract a single war record."""
        started_on = self._fmt_date(war_data.get('start_date'))
        if not started_on:
            return None

        peace_raw = war_data.get('peace_date', ONGOING_DATE)
        is_ongoing = (not peace_raw or peace_raw == ONGOING_DATE)
        ended_on = None if is_ongoing else self._fmt_date(peace_raw)
        status = 'ongoing' if is_ongoing else 'ended'

        # Diplomatic play data
        play_id = str(war_data.get('diplomatic_play', ''))
        play_data = plays_db.get(play_id, {}) if play_id else {}

        war_type = play_data.get('type') or 'unknown'
        strategic_region = play_data.get('strategic_region')
        state_val = play_data.get('state')
        objective_state_id = str(state_val) if state_val is not None else None
        escalation = int(play_data.get('escalation', 0))
        initiator_maneuvers = int(play_data.get('initiator_maneuvers', 0))
        target_maneuvers = int(play_data.get('target_maneuvers', 0))

        # Attacker/defender sets (numeric string IDs)
        initiator_id = str(play_data.get('initiator', ''))
        target_id = str(play_data.get('target', ''))
        extra_targets = [str(t) for t in play_data.get('targets', [])]

        attacker_ids = {initiator_id} if initiator_id else set()
        defender_ids = {target_id} if target_id else set()
        defender_ids.update(extra_targets)

        participants = self._extract_participants(
            war_data, play_data, attacker_ids, defender_ids, id_to_tag
        )
        battles = self._extract_battles(war_key, battles_db, id_to_tag)

        return WarData(
            save_war_id=war_key,
            war_type=war_type,
            strategic_region=strategic_region,
            diplomatic_play_id=play_id or None,
            objective_state_id=objective_state_id,
            escalation=min(100, max(0, escalation)),
            initiator_maneuvers=initiator_maneuvers,
            target_maneuvers=target_maneuvers,
            started_on=started_on,
            ended_on=ended_on,
            status=status,
            participants=participants,
            battles=battles,
        )

    def _extract_participants(self, war_data: Dict[str, Any], play_data: Dict[str, Any],
                              attacker_ids: set, defender_ids: set,
                              id_to_tag: Dict[str, str]) -> List[WarParticipant]:
        """Extract participant list from war_participants + diplomatic play costs."""
        # Casualties by country ID: sum attrition across all fronts
        casualties_map: Dict[str, float] = {}
        for entry in play_data.get('casualties', []):
            if not isinstance(entry, dict):
                continue
            cid = str(entry.get('country', ''))
            total = sum(
                entry.get('casualties_from_attrition_by_front', {}).values()
            )
            if cid:
                casualties_map[cid] = casualties_map.get(cid, 0.0) + float(total)

        # Materiel and wage costs by country ID
        materiel_map: Dict[str, float] = {}
        wage_map: Dict[str, float] = {}
        for rec in play_data.get('country_records', []):
            if not isinstance(rec, dict):
                continue
            cid = str(rec.get('country', ''))
            if not cid:
                continue
            goods = rec.get('materiel_cost_of_war', {}).get('goods', {})
            total_mat = sum(
                v.get('value', 0) for v in goods.values() if isinstance(v, dict)
            )
            materiel_map[cid] = float(total_mat)
            wage_map[cid] = float(rec.get('wage_cost_of_war', 0))

        raw = war_data.get('war_participants', [])
        if isinstance(raw, dict):
            raw = list(raw.values())

        seen: set = set()
        participants = []
        for p in raw:
            if not isinstance(p, dict):
                continue
            cid = str(p.get('country', ''))
            if not cid or cid in seen:
                continue
            seen.add(cid)

            tag = id_to_tag.get(cid)
            if not tag:
                logger.debug(f"No tag found for country ID {cid} — skipping participant")
                continue

            if cid in attacker_ids:
                side = 'attacker'
            elif cid in defender_ids:
                side = 'defender'
            else:
                logger.debug(f"Country {tag} ({cid}) not in attacker or defender sets — skipping")
                continue

            participants.append(WarParticipant(
                country_tag=tag,
                side=side,
                war_support=int(p.get('war_support', 0)),
                casualties=casualties_map.get(cid, 0.0),
                materiel_cost=materiel_map.get(cid, 0.0),
                wage_cost=wage_map.get(cid, 0.0),
            ))

        return participants

    def _extract_battles(self, war_key: str, battles_db: Dict[str, Any],
                         id_to_tag: Dict[str, str]) -> List[Battle]:
        """Extract battles belonging to this war from battle_manager.database.

        Battle structure (confirmed from save inspection):
          battle.war                           -> numeric war ID
          battle.battle_data.attacker.country  -> numeric country ID of attacker
          battle.battle_data.defender.country  -> numeric country ID of defender
          battle.battle_data.attacker.statistics -> [{num_dead, num_wounded, ...}]
          battle.status   -> 'attacker_victory' / 'defender_victory' / 'fighting'
          battle.start_date / battle.end_date  -> date strings
          battle.province -> province ID
          battle.name     -> {key, variables: [{key, value}]}
          battle.type     -> 'land' or 'naval'
        """
        war_id_int = None
        try:
            war_id_int = int(war_key)
        except (ValueError, TypeError):
            pass

        battles = []
        for battle_key, battle_data in battles_db.items():
            if not isinstance(battle_data, dict):
                continue

            # Only battles belonging to this war
            if war_id_int is not None and battle_data.get('war') != war_id_int:
                continue

            bd = battle_data.get('battle_data', {})
            att_info = bd.get('attacker', {}) if isinstance(bd, dict) else {}
            def_info = bd.get('defender', {}) if isinstance(bd, dict) else {}

            att_tag = id_to_tag.get(str(att_info.get('country', '')))
            def_tag = id_to_tag.get(str(def_info.get('country', '')))

            if not att_tag or not def_tag or att_tag == def_tag:
                continue

            # Casualties: sum num_dead across culture groups
            att_dead = sum(
                s.get('num_dead', 0) for s in att_info.get('statistics', [])
                if isinstance(s, dict)
            )
            def_dead = sum(
                s.get('num_dead', 0) for s in def_info.get('statistics', [])
                if isinstance(s, dict)
            )

            # Battalion losses
            att_bat_lost = max(0,
                (battle_data.get('attacker_start_battalions') or 0) -
                (battle_data.get('attacker_ending_battalions') or 0))
            def_bat_lost = max(0,
                (battle_data.get('defender_start_battalions') or 0) -
                (battle_data.get('defender_ending_battalions') or 0))

            # Winner from status
            status = battle_data.get('status', 'unknown')
            if status == 'attacker_victory':
                winner_tag = att_tag
            elif status == 'defender_victory':
                winner_tag = def_tag
            else:
                winner_tag = None

            # Province location
            loc = battle_data.get('province')
            location_province_id = str(loc) if loc is not None else None

            # Battle name: extract state/city from localisation key variables
            # BATTLE_IN -> STATE_REGION_NAME variable (e.g. 'STATE_ONTARIO')
            # BATTLE_FOR -> CITY_NAME variable (e.g. 'HUB_NAME_STATE_BASQUE_COUNTRY_wood')
            name_data = battle_data.get('name', {})
            battle_name = None
            if isinstance(name_data, dict):
                name_vars = name_data.get('variables', [])
                for nv in name_vars:
                    if not isinstance(nv, dict):
                        continue
                    if nv.get('key') == 'STATE_REGION_NAME':
                        battle_name = nv.get('value') or None
                        break
                    if nv.get('key') == 'CITY_NAME':
                        # Extract state portion: HUB_NAME_STATE_X_type -> STATE_X
                        city_val = nv.get('value', '')
                        parts = city_val.split('_')
                        state_idx = next(
                            (i for i, p in enumerate(parts) if p == 'STATE'), -1
                        )
                        if state_idx >= 0:
                            battle_name = '_'.join(parts[state_idx:-1]) or city_val
                        else:
                            battle_name = city_val or None
                        break

            battles.append(Battle(
                battle_id=f"{war_key}_{battle_key}",
                attacker_tag=att_tag,
                defender_tag=def_tag,
                occurred_on=self._fmt_date(battle_data.get('start_date')),
                ended_on=self._fmt_date(battle_data.get('end_date')),
                location_province_id=location_province_id,
                attacker_casualties=round(float(att_dead), 6),
                defender_casualties=round(float(def_dead), 6),
                attacker_battalions_lost=att_bat_lost,
                defender_battalions_lost=def_bat_lost,
                winner_tag=winner_tag,
                name=battle_name,
                battle_type=battle_data.get('type', 'land'),
                status=status,
            ))

        return battles
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Return statistics from the last extraction run."""
        stats = self.extraction_stats.copy()
        total = stats['wars_processed']
        stats['success_rate'] = (
            (stats['wars_extracted'] / total * 100) if total > 0 else 0.0
        )
        return stats
