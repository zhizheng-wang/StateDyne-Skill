"""Independent, outcome-based competition of claims from real workers.

A tournament is a *real, separately executed* synthesis judgment, not a
majority vote, a novelty score, or proof of the underlying science.
It prevents meaningful dissent from disappearing at composition time.
"""
from __future__ import annotations
from .common import StateDyneError, digest
import re
from .load_bearing import snapshot_signature
from .schemas import SCHEMAS, validate

PIVOTAL = frozenset({'preferred', 'serious_rival'})


def tournament_signature(ws):
    """Invalidates jury when actual claim CONTENT, evidence or objectives change."""
    return digest({'load_signature': snapshot_signature(ws),
                   'active_claims': ws.active_claims(),
                   'goal_review': ws.state.get('goal_review')})


def register_tournament(ws, job_id: str) -> bool:
    req = ws.job_request(job_id)
    if req['role'] != 'decision_tournament':
        raise StateDyneError('An outcome competition must be independently assigned')
    receipt = ws.result(job_id)
    if receipt is None or not receipt.get('independent_context'):
        raise StateDyneError('Outcome competition needs a real independent worker receipt')
    out = receipt['output']
    validate(out, SCHEMAS['decision_tournament'])
    active = ws.active_claims()
    entries = out['entries']
    if not out['goal_at_stake'].strip() or not out['comparison_basis'].strip():
        raise StateDyneError('Competing claims require a real user goal and comparison standard')
    if not entries and (active and not out['no_independent_value_reason'].strip()):
        raise StateDyneError('A null competition needs a concrete explanation of why no candidates have decision value')
    seen = set()
    for entry in entries:
        key = entry['local_id']
        if not key.strip() or key in seen:
            raise StateDyneError('Competition entry ids must be nonempty and distinct')
        seen.add(key)
        ids = entry['claim_ids']
        rivals = entry['rival_claim_ids']
        if (not ids or len(ids) != len(set(ids)) or not set(ids).issubset(active)
                or len(rivals) != len(set(rivals)) or not set(rivals).issubset(active)
                or set(ids) & set(rivals)):
            raise StateDyneError('Each competitor must reference actual distinct source-worker claims')
        for field in ('generation_path', 'distinct_prediction', 'evidence_boundary',
                      'implementation_path', 'user_value_delta', 'compared_to_baseline',
                      'why_this_disposition'):
            if not entry[field].strip():
                raise StateDyneError(f'Every competitor must explain {field}, including conditional/null outcomes')
        if (entry['verdict'] in PIVOTAL and not rivals
                and not out['no_independent_value_reason'].strip()):
            raise StateDyneError('A pivotal recommendation without a specific rival needs an explicit real null-search reason')
    opening = out['research_opening']
    new_opportunity = False
    if opening['needed']:
        if not opening['focus'].strip() or not opening['expected_difference'].strip():
            raise StateDyneError('A pivotal research opening requires a concrete target and expected discriminator')
        if opening['evidence_route'] in ('materials', 'calculation', 'public_source'):
            existing = ws.state.setdefault('exploration_opportunities', {})
            def norm(x):
                return re.sub(r'[\W_]+', ' ', x.casefold(), flags=re.UNICODE).strip()
            present = {norm(item['description']) for item in existing.values()
                       if item.get('state') != 'stale'}
            # Only truly unattempted opportunities restart model/evidence
            # research. An attempted no-increment search is not infinite work.
            if norm(opening['focus']) not in present:
                oid = f'{job_id}:J1'
                existing[oid] = {
                    'id': oid, 'description': opening['focus'],
                    'origin_job': job_id, 'state': 'open', 'attempts': 0,
                    'generation_opened': ws.state['generation'],
                    'proposed_by': [job_id],
                    'expected_difference': opening['expected_difference'],
                    'evidence_route': opening['evidence_route']}
                new_opportunity = True
    elif opening['focus'].strip() or opening['expected_difference'].strip():
        raise StateDyneError('Do not claim an unfinished research route when no new study is needed')
    ws.state['decision_tournament'] = {
        'job_id': job_id, 'output': out, 'signature': tournament_signature(ws),
        'epistemic_limit': 'model_judgment_not_semantic_truth'}
    ws.mark_result(job_id)
    ws.save('independent_outcome_tournament_recorded', {
        'job_id': job_id, 'entry_count': len(entries),
        'pivotal_ids': [x['local_id'] for x in entries if x['verdict'] in PIVOTAL],
        'research_reopened': new_opportunity})
    return new_opportunity


def check_draft_against_tournament(ws, draft: dict) -> None:
    tournament = ws.state.get('decision_tournament')
    if not tournament:
        return
    if tournament['signature'] != tournament_signature(ws):
        raise StateDyneError('The outcome competition is stale: re-run after evidence, goal or claim changes')
    disp = {x['claim_id']:x for x in draft['claim_dispositions']}
    used = set(draft['used_claim_ids'])
    response = draft['answer']
    for entry in tournament['output']['entries']:
        if entry['verdict'] not in PIVOTAL:
            continue
        ids = entry['claim_ids']
        if not any(cid in disp for cid in ids):
            raise StateDyneError('A pivotal independent hypothesis silently disappeared from final disposition')
        # A preferred discovery must have a real cited claim admitted into the
        # resulting answer, or a VISIBLE account of why the judgment changed.
        accepted = any(cid in used for cid in ids)
        anchors = [disp[cid]['reason'].strip() for cid in ids if cid in disp]
        if not any(len(anchor) >= 12 and anchor in response for anchor in anchors):
            raise StateDyneError('A pivotal winning or minority option must have an independent, user-visible comparison reason')
        if entry['verdict'] == 'preferred' and not accepted:
            # The composer's other path may actually be better, but silently
            # reversing the independent judgment isn't an acceptable result.
            if not all(disp[cid]['treatment'] in ('not_selected','reject') for cid in ids):
                raise StateDyneError('A reversed independent recommendation needs explicit claim disposition')


def check_audit_against_tournament(ws, audit: dict, draft: dict) -> None:
    """Existing independent final audit must not approve an unhandled rival."""
    if audit['verdict'] != 'pass':
        return
    check_draft_against_tournament(ws, draft)
