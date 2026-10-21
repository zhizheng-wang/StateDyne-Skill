"""Candidate -> distinct prediction -> source-routed discriminator bridge.

A structural *minimum* for source-blind model-outside discoveries, not an
oracle deciding whether a hypothesis is true, novel or clinically appropriate.
Discriminating information can be user-held, public, calculable or currently
unavailable; a question to the user is NOT always necessary or appropriate.
"""
from __future__ import annotations
import re


def _identity(claim: dict) -> str:
    # Compare observed mechanism + prediction, not role titles or model prose.
    mech = claim.get('mechanism') or {}
    parts = [claim.get('statement', ''), mech.get('transformation', ''),
             *claim.get('distinct_consequences', [])]
    return re.sub(r'[\W_]+', ' ', ' '.join(parts).casefold(), flags=re.UNICODE).strip()


def _first_job(ws, tag: str):
    for job in ws.state.get('jobs', {}).values():
        if job.get('tag') == tag and job.get('status') == 'completed':
            return job
    return None


def unbridged_model_outside(ws) -> list[dict]:
    """Return newly proposed source-blind hypotheses with no linked test.

    The source-blind generation roles are compared with the baseline. All
    genuinely differentiated hypotheses require some *declared* discriminator
    route; we never force a number of visible questions, and the route need not
    be the user. An information-finding worker or repair worker may supply the
    missing link later. Claims with no materially different prediction are not
    credited as new bridges by this check.
    """
    gen = ws.state.get('generation')
    baseline_job = _first_job(ws, f'g{gen}-discovery')
    if not baseline_job:
        return []
    baseline_result = ws.result(baseline_job['id'])
    if not baseline_result:
        return []
    baseline = {_identity(x) for x in baseline_result['output']['claims']}
    # Following raw generators may share facts but must discover their own
    # testable differences, or supply a concrete grounded null result.
    gaps = []
    for role, tag in [('reframe', 'reframe'), ('contrast_probe', 'contrast-probe'),
                      ('frontier_scout', 'frontier-scout'), ('breakthrough_scout', 'breakthrough-raw')]:
        job = _first_job(ws, f'g{gen}-{tag}')
        if not job:
            continue
        result = ws.result(job['id'])
        if not result:
            continue
        for claim in result['output']['claims']:
            if claim['kind'] not in ('mechanism', 'prediction') or claim['epistemic_status'] != 'hypothesis':
                continue
            # No *independently different predicted consequence* = not yet a
            # new prediction for purposes of this particular bridge check.
            if not claim['distinct_consequences'] or _identity(claim) in baseline:
                continue
            cid = f"{job['id']}:{claim['local_id']}"
            already_linked = [q for q in ws.state.get('unknowns', {}).values()
                              if q['state'] != 'stale' and cid in q['related_claims']
                              and q['question'].strip() and q['why_it_matters'].strip()]
            if already_linked:
                continue
            gaps.append({'role': role, 'claim_id': cid,
                         'statement': claim['statement'],
                         'new_predictions': claim['distinct_consequences'],
                         'missing': 'no linked source-routed discriminating question or evidence operation'})
    return gaps
