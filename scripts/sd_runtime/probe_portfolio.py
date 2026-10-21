"""Independent hypothesis tournament: route testable probes into real next work.

This module checks provenance, difference, source routing and follow-through.
It cannot prove semantic novelty, hidden causation or the merits of a hypothesis.
"""
from __future__ import annotations
import re
from .common import StateDyneError


def normalized(text: str) -> str:
    return re.sub(r'[\W_]+', ' ', text.casefold(), flags=re.UNICODE).strip()


def _reported(ws, prediction: str) -> bool:
    """Only veto verbatim/near-literal reused observations; don't claim semantics."""
    key = normalized(prediction)
    if not key:
        return True
    for src in ws.state['sources'].values():
        if src.get('is_task') and key in normalized(src['text']):
            return True
    return False


def verify_exploration_attempts(product: dict) -> None:
    """Require an observable attempt outside incumbent models, never a forced discovery.

    This proves a typed effort was supplied, not that it was truly independent,
    novel, or complete. A negative search is legitimate when its tested basis
    and failure to distinguish are stated concretely.
    """
    attempts=product['exploration_attempts']
    if not attempts:
        raise StateDyneError('Independent portfolio needs an actual alternative-representation exploration receipt')
    ids={p['local_id']:p for p in product['probes']}
    visited=set(); covered=set()
    for attempt in attempts:
        aid=attempt['local_id']
        if aid in visited or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', aid):
            raise StateDyneError('Exploration receipt IDs must be unique and valid')
        visited.add(aid);covered.add(attempt['focus'])
        if not all(attempt[key].strip() for key in ('incumbent_limit','alternative_representation',
                   'evidence_route','reason')):
            raise StateDyneError('Alternative search needs the old limit, real alternative and evidence route')
        pred=normalized(attempt['distinct_prediction'])
        rival=normalized(attempt['rival_prediction'])
        if attempt['outcome']=='null_after_search':
            if attempt['probe_local_ids'] or len(attempt['reason'].strip()) < 32:
                raise StateDyneError('Null exploration cannot claim new probes and needs a concrete negative-search explanation')
        else:
            if not pred or not rival or pred==rival:
                raise StateDyneError('Promoted or deferred exploration needs a genuinely discriminating predicted result')
            if not attempt['probe_local_ids']:
                raise StateDyneError('A productive exploration receipt must link to at least one actual portfolio probe')
        if len(set(attempt['probe_local_ids']))!=len(attempt['probe_local_ids']):
            raise StateDyneError('Duplicate probe IDs in exploration receipt')
        for pid in attempt['probe_local_ids']:
            if pid not in ids:
                raise StateDyneError('Exploration receipt cites a probe that does not exist')
            if attempt['outcome']=='advanced' and not ids[pid]['advance']:
                raise StateDyneError('Advanced exploration must point to a probe really admitted into next work')
            if attempt['outcome']=='deferred' and ids[pid]['advance']:
                raise StateDyneError('Deferred exploration must point to an explicitly deferred probe')
    if not covered.intersection({'outside_current_model','upstream_environment',
                                  'selection_or_measurement','counterfactual_baseline'}):
        raise StateDyneError('Portfolio did not attempt a search beyond its incumbent representation')
    # Probes can come from incumbent model testing without outside receipts;
    # outside exploration can legitimately end with an honest null result.


def register_portfolio(ws, job_id: str) -> None:
    """Admit an independent search allocation: actionable evidence or model expansion.

    New candidate-linked probes become *real* unknowns, with explicit evidence
    provenance. A probe for an as-yet unrepresented causal family becomes a
    reframe opportunity. Neither is merely a paragraph in the review report.
    """
    job = ws.job_request(job_id)
    if job['role'] != 'probe_portfolio':
        raise StateDyneError('Only a genuine portfolio worker may register independent probes')
    result = ws.result(job_id)
    if result is None:
        raise StateDyneError('Portfolio registration requires an actual completed worker')
    product = result['output']
    probes = product['probes']
    verify_exploration_attempts(product)
    if not probes and len(product['null_search_reason'].strip()) < 28:
        raise StateDyneError('Empty portfolio must describe concrete alternative searches and their failure to add value')
    active = ws.active_claims()
    seen, staged_unknowns, staged_opps, staged_items = set(), {}, {}, []
    existing = {normalized(q['question']) for q in ws.state['unknowns'].values() if q.get('state') != 'stale'}
    for index, item in enumerate(probes, 1):
        key = normalized(item['question'])
        if not key or key in seen:
            raise StateDyneError('Portfolio has duplicate/empty discriminating questions')
        seen.add(key)
        referenced = item['claim_ids']
        if len(set(referenced)) != len(referenced) or not set(referenced).issubset(active):
            raise StateDyneError('A portfolio probe cites an unknown/stale/repeated hypothesis')
        for field in ('unreported_outcome', 'rival_outcome', 'why_distinguishes', 'reason'):
            if not item[field].strip():
                raise StateDyneError('Probe needs independent prediction, rival outcome and concrete causal discriminator')
        if _reported(ws, item['unreported_outcome']):
            raise StateDyneError('A verbatim reported phenomenon cannot become a newly predicted outcome')
        if normalized(item['unreported_outcome']) == normalized(item['rival_outcome']):
            raise StateDyneError('Rival predictions cannot be identical')
        if item['advance'] and item['route'] == 'user':
            # A probe must help someone recognise an unreported occurrence
            # WITHOUT presenting that occurrence as an established memory.
            prompt, counter = item['recognition_prompt'].strip(), item['counter_cue'].strip()
            if not prompt or not counter or len(prompt) < 15:
                raise StateDyneError('A user-routed probe needs a natural recognition prompt and a concrete counter-cue')
            if not any(mark in prompt for mark in ('?', '？')):
                raise StateDyneError('A recognition prompt must be a question rather than an asserted hidden fact')
            if normalized(prompt) in (normalized(item['unreported_outcome']), normalized(item['question'])):
                raise StateDyneError('The recognition prompt must expand a technical discriminator, not recite it')
            if normalized(counter) in (normalized(prompt), normalized(item['unreported_outcome'])):
                raise StateDyneError('A counter-cue must describe a genuinely different possible outcome')
        if not referenced and not item['model_gap'].strip():
            raise StateDyneError('A probe without an admitted model must describe which new relation is missing')
        if referenced and item['model_gap'].strip():
            raise StateDyneError('Use an empty model_gap when an admitted hypothesis can already be tested')
        local = item['local_id']
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', local):
            raise StateDyneError('Portfolio item ID is invalid')
        identity = (job_id, local)
        if identity in {(r['job_id'], r['local_id']) for r in staged_items}:
            raise StateDyneError('Portfolio item IDs must be unique')
        state = 'pursue' if item['advance'] else 'deferred'
        annotation = {**item, 'job_id': job_id, 'id': f'{job_id}:{local}', 'state': state}
        staged_items.append(annotation)
        if not item['advance']:
            continue
        if not referenced:
            oid = f'{job_id}:P{index}'
            staged_opps[oid] = {'id': oid, 'description': ('Find a previously unrepresented generative mechanism: '
                                         + item['model_gap'] + ' Discriminator: ' + item['question']),
                                 'origin_job': job_id, 'state': 'open', 'attempts': 0,
                                 'generation_opened': ws.state['generation'], 'proposed_by': [job_id],
                                 'portfolio_priority': item['importance'], 'portfolio_probe_id': annotation['id']}
        elif key not in existing:
            qid = f'{job_id}:Q{index}'
            staged_unknowns[qid] = {
                'id': qid, 'question': item['question'], 'why_it_matters': item['why_distinguishes'],
                'origin': 'prediction', 'route': item['route'], 'related_claims': list(referenced),
                'priority': ('blocking' if item['importance'] == 'critical' else item['importance']),
                'recognition_prompt': item['recognition_prompt'],
                'counter_cue': item['counter_cue'],
                'state': 'open', 'origin_job': job_id, 'disposition_evidence': [],
                'portfolio_probe_id': annotation['id']}
    # Fully validate before any workspace mutation.
    if (ws.state.get('probe_portfolio') or {}).get('job_id') == job_id:
        return
    ws.state['unknowns'].update(staged_unknowns)
    ws.state.setdefault('exploration_opportunities', {}).update(staged_opps)
    ws.state['probe_portfolio'] = {'job_id': job_id, 'probes': staged_items,
                                   'exploration_attempts': product['exploration_attempts'],
                                   'null_search_reason': product['null_search_reason'],
                                   'covered_representation': product['covered_representation']}
    ws.mark_result(job_id)
    ws.save('independent_portfolio_became_executable_search', {
        'job_id': job_id, 'new_unknown_ids': list(staged_unknowns),
        'new_reframe_opportunity_ids': list(staged_opps),
        'unselected_probe_ids': [x['id'] for x in staged_items if x['state'] == 'deferred']})


def pending_model_expansion(ws) -> list[str]:
    """High-value unrepresented relation families not yet searched."""
    return [oid for oid, obj in ws.state.get('exploration_opportunities', {}).items()
            if obj.get('portfolio_priority') in ('critical', 'important')
            and obj.get('state') == 'open' and obj.get('attempts', 0) == 0]
