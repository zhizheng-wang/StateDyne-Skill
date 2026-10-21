"""Strict structural check for claims requiring a conjunction on the same unit.

A status field, audit receipt or numeric multiplication cannot prove an
actual joint outcome; the independent reviewer must still check reality.
"""
from __future__ import annotations
from .common import StateDyneError


def validate_objective_joins(ws, draft: dict):
    joins=draft['objective_joins']
    indexed={j['local_id']:j for j in joins}
    if len(indexed)!=len(joins) or any(not name.strip() for name in indexed):
        raise StateDyneError('Objective joins require distinct nonempty IDs')
    quantity_ids={q['local_id'] for q in draft['pivotal_quantities']}
    chosen=set(draft['used_claim_ids'])
    eligible={q['local_id'] for q in draft['pivotal_quantities']
              if q['measure_kind']=='eligible_net_increment'}
    covered=set()
    for j in joins:
        if not j['target_entity_or_cohort'].strip() or not j['same_entity_basis'].strip() or not j['missing_join_or_displacement'].strip():
            raise StateDyneError('Objective conjunction needs same-entity scope, linkage basis and displacement check')
        if not j['quantity_ids'] and not j['claim_ids']:
            raise StateDyneError('An objective conjunction must support an actual claim or quantity')
        if (len(j['quantity_ids'])!=len(set(j['quantity_ids'])) or
            not set(j['quantity_ids']).issubset(quantity_ids) or
            len(j['claim_ids'])!=len(set(j['claim_ids'])) or
            not set(j['claim_ids']).issubset(chosen)):
            raise StateDyneError('Objective conjunction references invalid or repeated selected results')
        conditions=j['necessary_conditions']
        if len(conditions)<2 or len({x['name'].strip() for x in conditions})!=len(conditions):
            raise StateDyneError('Objective conjunction requires at least two distinct necessary predicates')
        if any(not x['name'].strip() or not x['evidence_or_assumption'].strip() for x in conditions):
            raise StateDyneError('Every objective condition requires actual evidence or a declared assumption')
        anchor=j['visible_joint_anchor'].strip()
        if not anchor or anchor not in draft['answer']:
            raise StateDyneError('Conjunctive user goal must be reflected in the actual visible answer')
        state=j['joint_status']
        if state=='observed_intersection':
            if any(c['status']!='observed_same_entities' for c in conditions):
                raise StateDyneError('Cannot claim observed joint success from estimated or unrelated marginals')
            if j['same_entity_basis'].strip().lower() in {'not linked', 'not verified', 'unknown', 'unverified', '未验证', '没有交集数据'}:
                raise StateDyneError('Observed joint outcome needs positive same-entity evidence')
        else:
            limit=j['visible_uncertainty_anchor'].strip()
            if not limit or limit not in draft['answer']:
                raise StateDyneError('Unverified joint satisfaction must be visibly conditional')
            if state=='unresolved' and draft['status']=='complete':
                raise StateDyneError('Cannot claim complete verified target success with unresolved joint prerequisites')
        covered.update(j['quantity_ids'])
    if not eligible.issubset(covered):
        raise StateDyneError('Eligible net incremental outcomes need a same-entity multi-condition joint bridge')


def validate_objective_join_review(audit: dict, draft: dict):
    joins=draft['objective_joins']
    seen={r['local_id']:r for r in audit['objective_join_reviews']}
    if len(seen)!=len(audit['objective_join_reviews']) or set(seen)!={j['local_id'] for j in joins}:
        raise StateDyneError('Independent audit must review each adopted joint outcome')
    if not audit['objective_join_coverage_reason'].strip():
        raise StateDyneError('Independent audit must investigate omitted multi-condition target outcomes')
    for item in joins:
        check=seen[item['local_id']]
        if any(not check[f].strip() for f in ('entity_and_time_match',
                                             'strongest_non_joint_alternative',
                                             'evidence_or_missing_join',
                                             'consequence_for_conclusion')):
            raise StateDyneError('Joint review must inspect entity/time alignment, strongest rival and effect')
        if check['verdict']=='needs_revision' and audit['verdict']=='pass':
            raise StateDyneError('Cannot pass an independently rejected objective conjunction')
        if item['joint_status']=='observed_intersection' and check['verdict']=='conditional_only' and audit['verdict']=='pass':
            raise StateDyneError('Observed success not established by a conditional conjunction review')
        if item['joint_status']!='observed_intersection' and check['verdict']=='joint_verified':
            raise StateDyneError('A conditional result cannot be certified as an observed joint outcome')
