from typing import Dict, Any

LAW_GROUPS: Dict[str, Dict[str, Any]] = {
    # ── POWER STRUCTURE ──────────────────────────────────────────────────────
    'governance': {
        'label': 'Governance Principles', 'category': 'power_structure', 'color': '#7B4F9E',
        'laws': {
            'law_monarchy': 'Monarchy',
            'law_colonial_administration': 'Colonial Administration',
            'law_presidential_republic': 'Presidential Republic',
            'law_parliamentary_republic': 'Parliamentary Republic',
            'law_theocracy': 'Theocracy',
            'law_council_republic': 'Council Republic',
            'law_corporate_state': 'Corporate State',
            'law_chiefdom': 'Chiefdom',
        },
    },
    'distribution_of_power': {
        'label': 'Distribution of Power', 'category': 'power_structure', 'color': '#9966FF',
        'laws': {
            'law_autocracy': 'Autocracy',
            'law_technocracy': 'Technocracy',
            'law_oligarchy': 'Oligarchy',
            'law_landed_voting': 'Landed Voting',
            'law_wealth_voting': 'Wealth Voting',
            'law_census_voting': 'Census Suffrage',
            'law_universal_suffrage': 'Universal Suffrage',
            'law_single_party_state': 'Single-Party State',
            'law_anarchy': 'Anarchy',
            'law_elder_council': 'Elder Council',
            # variants
            'law_neo_absolutism': 'Neo-Absolutism',
            'law_organic_regulation': 'Organic Regulation',
            'law_bakufu': 'Bakufu',
            'law_social_monarchy': 'Social Monarchy',
        },
    },
    'citizenship': {
        'label': 'Citizenship', 'category': 'power_structure', 'color': '#E91E63',
        'laws': {
            'law_subjecthood': 'Subjecthood',
            'law_ethnostate': 'Ethnostate',
            'law_national_supremacy': 'National Supremacy',
            'law_racial_segregation': 'Racial Segregation',
            'law_cultural_exclusion': 'Cultural Exclusion',
            'law_multicultural': 'Multiculturalism',
        },
    },
    'caste_hegemony': {
        'label': 'Caste Hegemony', 'category': 'power_structure', 'color': '#FF6F00',
        'laws': {
            'law_hindu_caste_enforced': 'Caste System Enforced',
            'law_hindu_caste_codified': 'Caste System Codified',
            'law_hindu_caste_not_enforced': 'Caste Not Enforced',
            'law_affirmative_action': 'Affirmative Action',
        },
    },
    'church_and_state': {
        'label': 'Church and State', 'category': 'power_structure', 'color': '#FF9800',
        'laws': {
            'law_state_religion': 'State Religion',
            'law_freedom_of_conscience': 'Freedom of Conscience',
            'law_total_separation': 'Total Separation',
            'law_state_atheism': 'State Atheism',
            # variants
            'law_people_of_the_book': 'People of the Book',
            'law_millet_system': 'Millet System',
        },
    },
    'bureaucracy': {
        'label': 'Bureaucracy', 'category': 'power_structure', 'color': '#607D8B',
        'laws': {
            'law_hereditary_bureaucrats': 'Hereditary Bureaucrats',
            'law_appointed_bureaucrats': 'Appointed Bureaucrats',
            'law_elected_bureaucrats': 'Elected Bureaucrats',
            # variant
            'law_crownland_diets': 'Crownland Diets',
        },
    },
    'army_model': {
        'label': 'Army Model', 'category': 'power_structure', 'color': '#795548',
        'laws': {
            'law_peasant_levies': 'Peasant Levies',
            'law_professional_army': 'Professional Army',
            'law_national_militia': 'National Militia',
            'law_mass_conscription': 'Mass Conscription',
            # variants
            'law_warrior_caste': 'Warrior Caste',
        },
    },
    'navy_model': {
        'label': 'Navy Model', 'category': 'power_structure', 'color': '#1565C0',
        'laws': {
            'law_merchant_navy': 'Merchant Navy',
            'law_professional_navy': 'Professional Navy',
            # variants
            'law_diplomatic_navy': 'Diplomatic Navy',
            'law_jeune_ecole': 'Jeune École',
        },
    },
    'internal_security': {
        'label': 'Internal Security', 'category': 'power_structure', 'color': '#424242',
        'laws': {
            'law_no_home_affairs': 'No Home Affairs',
            'law_national_guard': 'National Guard',
            'law_secret_police': 'Secret Police',
            'law_guaranteed_liberties': 'Guaranteed Liberties',
        },
    },

    # ── ECONOMY ──────────────────────────────────────────────────────────────
    'economic_system': {
        'label': 'Economic System', 'category': 'economy', 'color': '#FF8C00',
        'laws': {
            'law_traditionalism': 'Traditionalism',
            'law_interventionism': 'Interventionism',
            'law_agrarianism': 'Agrarianism',
            'law_industry_banned': 'Industry Banned',
            'law_extraction_economy': 'Extraction Economy',
            'law_laissez_faire': 'Laissez-Faire',
            'law_command_economy': 'Command Economy',
            'law_cooperative_ownership': 'Cooperative Ownership',
        },
    },
    'trade_policy': {
        'label': 'Trade Policy', 'category': 'economy', 'color': '#2196F3',
        'laws': {
            'law_mercantilism': 'Mercantilism',
            'law_protectionism': 'Protectionism',
            'law_free_trade': 'Free Trade',
            'law_isolationism': 'Isolationism',
            # variant
            'law_canton_system': 'Canton System',
        },
    },
    'edo_system': {
        'label': 'Edo System', 'category': 'economy', 'color': '#B71C1C',
        'laws': {
            'law_sakoku': 'Sakoku',
            'law_strict_edo_system': 'Strict Edo System',
            'law_intermediate_edo_system': 'Intermediate Edo System',
            'law_lax_edo_system': 'Lax Edo System',
        },
    },
    'taxation': {
        'label': 'Taxation', 'category': 'economy', 'color': '#00897B',
        'laws': {
            'law_consumption_based_taxation': 'Consumption-Based Taxation',
            'law_land_based_taxation': 'Land-Based Taxation',
            'law_per_capita_based_taxation': 'Per-Capita Taxation',
            'law_proportional_taxation': 'Proportional Taxation',
            'law_graduated_taxation': 'Graduated Taxation',
        },
    },
    'land_reform': {
        'label': 'Land Reform', 'category': 'economy', 'color': '#8BC34A',
        'laws': {
            'law_serfdom': 'Serfdom',
            'law_tenant_farmers': 'Tenant Farmers',
            'law_commercialized_agriculture': 'Commercialized Agriculture',
            'law_homesteading': 'Homesteading',
            'law_collectivized_agriculture': 'Collectivized Agriculture',
            # variants
            'law_manorialism': 'Manorialism',
            'law_latifundias': 'Latifundias',
            'law_expanded_latifundias': 'Expanded Latifundias',
            'law_peasant_proprietorship': 'Peasant Proprietorship',
        },
    },
    'colonization': {
        'label': 'Colonization', 'category': 'economy', 'color': '#A1887F',
        'laws': {
            'law_no_colonial_affairs': 'No Colonial Affairs',
            'law_colonial_resettlement': 'Colonial Resettlement',
            'law_frontier_colonization': 'Frontier Colonization',
            'law_colonial_exploitation': 'Colonial Exploitation',
        },
    },
    'policing': {
        'label': 'Policing', 'category': 'economy', 'color': '#546E7A',
        'laws': {
            'law_no_police': 'No Police',
            'law_local_police': 'Local Police Force',
            'law_dedicated_police': 'Dedicated Police Force',
            'law_militarized_police': 'Militarized Police Force',
            # variant
            'law_shinsengumi': 'Shinsengumi',
        },
    },
    'education_system': {
        'label': 'Education System', 'category': 'economy', 'color': '#FFC107',
        'laws': {
            'law_no_schools': 'No Schools',
            'law_religious_schools': 'Religious Schools',
            'law_private_schools': 'Private Schools',
            'law_public_schools': 'Public Schools',
            # variant
            'law_terakoya': 'Terakoya',
        },
    },
    'health_system': {
        'label': 'Health System', 'category': 'economy', 'color': '#F44336',
        'laws': {
            'law_no_health_system': 'No Health System',
            'law_charitable_health_system': 'Charity Hospitals',
            'law_private_health_insurance': 'Private Health Insurance',
            'law_public_health_insurance': 'Public Health Insurance',
        },
    },

    # ── HUMAN RIGHTS ─────────────────────────────────────────────────────────
    'free_speech': {
        'label': 'Free Speech', 'category': 'human_rights', 'color': '#00BCD4',
        'laws': {
            'law_outlawed_dissent': 'Outlawed Dissent',
            'law_censorship': 'Censorship',
            'law_right_of_assembly': 'Right of Assembly',
            'law_protected_speech': 'Protected Speech',
        },
    },
    'labor_rights': {
        'label': 'Labor Rights', 'category': 'human_rights', 'color': '#FF5722',
        'laws': {
            'law_no_workers_rights': "No Workers' Rights",
            'law_regulatory_bodies': 'Regulatory Bodies',
            'law_worker_protections': "Workers' Protections",
        },
    },
    'childrens_rights': {
        'label': "Children's Rights", 'category': 'human_rights', 'color': '#FF80AB',
        'laws': {
            'law_child_labor_allowed': 'Child Labor Allowed',
            'law_restricted_child_labor': 'Restricted Child Labor',
            'law_compulsory_primary_school': 'Compulsory Primary School',
        },
    },
    'rights_of_women': {
        'label': 'Rights of Women', 'category': 'human_rights', 'color': '#C2185B',
        'laws': {
            'law_no_womens_rights': 'Legal Guardianship',
            'law_women_own_property': 'Propertied Women',
            'law_women_in_the_workplace': 'Women in the Workplace',
            'law_womens_suffrage': "Women's Suffrage",
            # variant
            'law_women_in_the_fields': 'Women in the Fields',
        },
    },
    'welfare': {
        'label': 'Welfare', 'category': 'human_rights', 'color': '#4CAF50',
        'laws': {
            'law_no_social_security': 'No Social Security',
            'law_poor_laws': 'Poor Laws',
            'law_wage_subsidies': 'Wage Subsidies',
            'law_old_age_pension': 'Old Age Pension',
            # variant
            'law_chiefs_distribute_aid': 'Sef Paternalism',
        },
    },
    'migration': {
        'label': 'Migration', 'category': 'human_rights', 'color': '#26C6DA',
        'laws': {
            'law_no_migration_controls': 'No Migration Controls',
            'law_migration_controls': 'Migration Controls',
            'law_closed_borders': 'Closed Borders',
        },
    },
    'slavery': {
        'label': 'Slavery', 'category': 'human_rights', 'color': '#6D4C41',
        'laws': {
            'law_slavery_banned': 'Slavery Banned',
            'law_colonial_slavery': 'Colonial Slavery',
            'law_debt_slavery': 'Debt Slavery',
            'law_slave_trade': 'Slave Trade',
            'law_legacy_slavery': 'Legacy Slavery',
        },
    },
    'labor_associations': {
        'label': 'Labor Associations', 'category': 'human_rights', 'color': '#E64A19',
        'laws': {
            'law_guild_system': 'Guild System',
            'law_combination_acts': 'Combination Acts',
            'law_anti_strike_laws': 'Anti-Strike Laws',
            'law_right_to_associate': 'Right to Associate',
            'law_corporatized_unions': 'Corporatized Unions',
            'law_factory_councils': 'Factory Councils',
        },
    },
}

LAW_TO_GROUP = {lk: gk for gk, g in LAW_GROUPS.items() for lk in g['laws']}
LAW_LABELS = {lk: lbl for g in LAW_GROUPS.values() for lk, lbl in g['laws'].items()}
CATEGORY_LABELS = {
    'power_structure': 'Power Structure',
    'economy': 'Economy',
    'human_rights': 'Human Rights',
}


def _load_user_mods() -> None:
    """Load user_law_mods.json and merge any defined laws into LAW_GROUPS / lookups."""
    import json as _json
    import os as _os
    import logging as _logging

    mods_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'user_law_mods.json')
    if not _os.path.exists(mods_path):
        return
    try:
        with open(mods_path, 'r', encoding='utf-8') as _f:
            mods = _json.load(_f)
    except Exception as _e:
        _logging.getLogger(__name__).warning('Failed to read user_law_mods.json: %s', _e)
        return

    added = 0
    for law_key, info in mods.items():
        if law_key.startswith('_') or not isinstance(info, dict):
            continue
        group_key = info.get('group', '')
        if not group_key or group_key not in LAW_GROUPS:
            _logging.getLogger(__name__).warning(
                'user_law_mods.json: unknown group %r for law %r — skipping', group_key, law_key
            )
            continue
        label = info.get('label', law_key)
        LAW_GROUPS[group_key]['laws'][law_key] = label
        LAW_TO_GROUP[law_key] = group_key
        LAW_LABELS[law_key] = label
        added += 1

    if added:
        _logging.getLogger(__name__).info('Loaded %d law mod(s) from user_law_mods.json', added)


_load_user_mods()
