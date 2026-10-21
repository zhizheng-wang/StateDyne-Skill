"""Independent, source-grounded goal calibration.

Records hypotheses about objectives and distinct values, never silently
changes the user's requested output scope or presumes private motives.
"""
from __future__ import annotations
from copy import deepcopy
from .common import StateDyneError
from .schemas import SCHEMAS, validate


def register_goal_review(ws, jid: str) -> None:
    job = ws.job_request(jid)
    if job['role'] != 'goal_scout':
        raise StateDyneError('Goal calibration requires an independently designated worker')
    res = ws.result(jid)
    if res is None:
        raise StateDyneError('No actual goal calibration worker result')
    out = res['output']
    validate(out, SCHEMAS['goal_review'])
    if not out['current_target'].strip() or not out['observable_success'].strip():
        raise StateDyneError('Goal review requires a target and observable success condition')
    exposed = ws.exposed(jid, res)
    ws.check_evidence(out['source_evidence'], exposed=exposed)
    if out['basis'] == 'explicit' and not out['source_evidence']:
        raise StateDyneError('Explicit goal must quote an actual user source')
    if not out['alternatives'] and not out['gap_or_conflict'].strip() and not out['adequate_existing_goal_reason'].strip():
        raise StateDyneError('No alternatives must have a concrete adequate-goal reason')
    if out['basis'] == 'missing' and not out['unresolved'] and not out['gap_or_conflict'].strip():
        raise StateDyneError('Absent goal must leave a real objective question or declared constraint')
    seen = set()
    for dim in out['valued_dimensions']:
        ws.check_evidence(dim['evidence'], exposed=exposed)
        label = dim['label'].strip().casefold()
        if not label or label in seen or not dim['content'].strip():
            raise StateDyneError('Distinct value axes need unique labels and actual content')
        seen.add(label)
        if dim['basis'] == 'explicit' and not dim['evidence']:
            raise StateDyneError('Explicitly protected value requires original evidence')
        if dim['distinct_from'] and dim['distinct_from'].strip().casefold() == label:
            raise StateDyneError('A valued dimension cannot be distinct from itself')
        if dim['distinct_from'] and not dim['loss_if_collapsed'].strip():
            raise StateDyneError('Distinguished values require a reason they cannot be collapsed onto one scale')
    for alternative in out['alternatives']:
        if not all(alternative[k].strip() for k in ('target','potential_gain','tradeoff','evidence_or_test')):
            raise StateDyneError('Goal alternatives need gain, cost and evidence/choice conditions')
        if not alternative['needs_user_choice']:
            raise StateDyneError('A different personal objective cannot be silently selected by the system')
    # Put uncertain, discriminating goal questions into the shared frontier.
    staged_unknowns = {}
    for idx, row in enumerate(out['unresolved'], 1):
        if not row['question'].strip() or not row['why_it_matters'].strip():
            raise StateDyneError('Goal question must discriminate a meaningful difference')
        qid = f'{jid}:goal-{idx}'
        staged_unknowns[qid] = {'id': qid, 'question': row['question'],
            'why_it_matters': row['why_it_matters'], 'origin': 'goal',
            'route': row['route'], 'priority': row['priority'],
            'related_claims': [], 'state': 'open', 'origin_job': jid,
            'disposition_evidence': []}
    ws.state['unknowns'].update(staged_unknowns)
    # A serious alternative objective is a research opportunity now, not
    # merely a suggestion buried at the end. Reframe must compare the same
    # protected values and concrete consequences BEFORE declaring the original
    # goal/implementation optimal. A worker never gets to choose for the user.
    old_review = ws.state.get('goal_review')
    if old_review:
        ws.state.setdefault('goal_review_history', []).append(deepcopy(old_review))
        for item in ws.state.get('exploration_opportunities',{}).values():
            if item.get('origin_goal_review') == old_review['job_id'] and item.get('state') == 'open':
                item['state']='stale'
    new_opportunities={}
    for i, alt in enumerate(out['alternatives'], 1):
        oid=f'{jid}:goal-path-{i}'
        new_opportunities[oid]={
            'id':oid,
            'description':('Independently compare objective representation "' + alt['target'] +
                 '" against the currently protected goal; potential gain: ' + alt['potential_gain'] +
                 '; sacrifice: ' + alt['tradeoff'] + '; evidence or test: ' + alt['evidence_or_test']),
            'origin_job':jid, 'origin_goal_review':jid,
            'state':'open','attempts':0,'generation_opened':ws.state['generation'],
            'proposed_by':[jid], 'system_priority':'important',
            'needs_user_choice':True}
    ws.state.setdefault('exploration_opportunities',{}).update(new_opportunities)
    ws.state['goal_review'] = {'job_id': jid, **deepcopy(out)}
    ws.mark_result(jid)
    ws.save('independent_goal_values_and_alternatives_registered',
            {'job_id': jid, 'open_questions': list(staged_unknowns),
             'alternative_count': len(out['alternatives']),
             'distinct_value_axes': [x['label'] for x in out['valued_dimensions']],
             'alternative_research_opportunities': list(new_opportunities)})
