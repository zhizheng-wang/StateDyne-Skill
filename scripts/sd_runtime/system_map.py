"""Objective-scoped whole-system coverage. A map is a search hypothesis, not the world.

Do not mistake a filled field for real investigation. The independent model must
identify what is known, unknown, or immaterial for this *specific* user goal.
"""
from __future__ import annotations
import re
from .common import StateDyneError
from .schemas import SYSTEM_DIMENSIONS, validate, SCHEMAS


def register_system_map(ws, jid: str) -> None:
    job = ws.job_request(jid)
    if job['role'] not in ('system_map', 'system_reconcile'):
        raise StateDyneError('A whole-system map requires an actual designated mapping worker')
    result = ws.result(jid)
    if result is None:
        raise StateDyneError('A missing worker cannot provide system coverage')
    out = result['output']
    validate(out, SCHEMAS['system_map'])
    slots = {c['dimension']: c for c in out['coverage']}
    if len(slots) != len(out['coverage']) or not set(SYSTEM_DIMENSIONS).issubset(slots):
        raise StateDyneError('Every core system dimension must be represented, open or explicitly not material; additional meaningful dimensions are allowed')
    if any(not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', dim) for dim in slots):
        raise StateDyneError('System dimension identifiers must use short nonempty snake_case labels')
    if not all(out[k].strip() for k in ('goal_text', 'success_condition', 'working_boundary', 'boundary_reason')):
        raise StateDyneError('System map requires an actual objective, success criterion and bounded reality')
    exposed = ws.exposed(jid, result)
    ws.check_evidence(out['goal_evidence'], exposed=exposed)
    if out['goal_basis'] == 'explicit' and not out['goal_evidence']:
        raise StateDyneError('An explicitly claimed user goal must cite the original user request')
    represented = set()
    for dim, slot in slots.items():
        if not slot['why_material'].strip():
            raise StateDyneError(f'System dimension {dim} needs a relevance/coverage reason')
        ws.check_evidence(slot['evidence'], exposed=exposed)
        if slot['state'] == 'open':
            if not slot['missing'].strip():
                raise StateDyneError(f'An open system dimension needs a concrete missing relation: {dim}')
        elif slot['state'] == 'represented':
            if not slot['observed_or_hypothesized'].strip():
                raise StateDyneError(f'A represented dimension needs actual content: {dim}')
            represented.add(dim)
        elif slot['basis'] != 'not_applicable':
            raise StateDyneError('An immaterial dimension cannot be represented as an observed fact')
        if slot['basis'] == 'reported' and not slot['evidence']:
            raise StateDyneError(f'User-reported system facts require a real source quote: {dim}')
    for edge in out['links']:
        ws.check_evidence(edge['evidence'], exposed=exposed)
        if not edge['link'].strip():
            raise StateDyneError('A system relationship needs a concrete interface, not merely a line')
        if edge['from_dimension'] not in slots or edge['to_dimension'] not in slots:
            raise StateDyneError('A system link must refer to two actually declared dimensions')
        if slots[edge['from_dimension']]['state']=='not_material' or slots[edge['to_dimension']]['state']=='not_material':
            raise StateDyneError('Links cannot claim substantive relations with irrelevant dimensions')
    material = [x for x in slots.values() if x['state']=='open' and x['priority'] in ('blocking','important')]
    if not material and not out['no_material_gap_reason'].strip():
        raise StateDyneError('A whole-system search with no material missing relation needs a specific null reason')
    staged_questions = {}
    staged_opportunities = {}
    for slot in material:
        dim=slot['dimension']; qid=f'{jid}:sys-{dim}'
        staged_questions[qid] = {
            'id':qid, 'question':slot['missing'], 'why_it_matters':slot['why_material'],
            'origin':'system_map', 'route':slot['route'], 'priority':slot['priority'],
            'related_claims':[], 'state':'open', 'origin_job':jid, 'disposition_evidence':[],
            'system_dimension':dim}
        if dim!='goal' and slot['route'] != 'user':
            oid=f'{jid}:coverage-{dim}'
            staged_opportunities[oid]={
                'id':oid, 'description':f'System coverage: investigate {dim}: {slot["missing"]} / {slot["why_material"]}',
                'origin_job':jid, 'state':'open', 'attempts':0,
                'generation_opened':ws.state['generation'], 'proposed_by':[jid],
                'system_dimension':dim, 'system_priority':slot['priority']}
    # Reconciled maps supersede *coverage questions*, not independent prior
    # observations; stale gaps must not keep firing after the system changes.
    old_map=ws.state.get('system_map')
    if old_map and old_map['job_id'] != jid:
        for item in ws.state['unknowns'].values():
            if item.get('origin')=='system_map' and item.get('state')=='open':
                item['state']='stale'
        for item in ws.state.get('exploration_opportunities',{}).values():
            if item.get('system_dimension') and item.get('state')=='open':
                item['state']='stale'
    # Validate all references before mutations. A new version supersedes
    # the old map but not the old recorded evidence or hypotheses.
    ws.state['unknowns'].update(staged_questions)
    ws.state.setdefault('exploration_opportunities',{}).update(staged_opportunities)
    ws.state.setdefault('system_map_history',[]).append({'job_id':jid,
        'goal_text':out['goal_text'],'goal_basis':out['goal_basis'],
        'coverage': {d: slot['state'] for d, slot in slots.items()}})
    ws.state['system_map']={'job_id':jid, 'goal_text':out['goal_text'],
        'goal_basis':out['goal_basis'], 'success_condition':out['success_condition'],
        'protected_constraints':out['protected_constraints'],
        'working_boundary':out['working_boundary'], 'boundary_reason':out['boundary_reason'],
        'coverage':out['coverage'], 'links':out['links'],
        'whole_model_gap':out['whole_model_gap'],
        'no_material_gap_reason':out['no_material_gap_reason']}
    ws.mark_result(jid)
    ws.save('independent_goal_bounded_system_coverage_registered',{'job_id':jid,
        'open_dimensions':[x['dimension'] for x in material],
        'information_ids':list(staged_questions),'opportunity_ids':list(staged_opportunities)})


def pending_coverage_opportunities(ws):
    return [oid for oid, entry in ws.state.get('exploration_opportunities',{}).items()
        if entry.get('system_dimension') and entry.get('system_priority') in ('blocking','important')
        and entry['state']=='open' and entry['attempts']==0]
