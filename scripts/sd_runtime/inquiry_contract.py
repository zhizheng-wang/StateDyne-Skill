"""Questions as a falsifiable information exchange, not a scripted interview.

Structural guarantees only: a model reviewer must still judge the economic,
psychological or scientific validity of its counterfactual implications.
"""
from __future__ import annotations
from .common import StateDyneError


def previous_question_groups(ws):
    turns=ws.state.get('turn_history', [])
    if not turns: return []
    prior=turns[-1].get('draft') or {}
    output=prior.get('output') or {}
    return output.get('question_groups', [])


def validate_question_groups(draft: dict) -> None:
    """Enforce private information value, not a compulsory frontstage WHY script.

    Every real user question has an accountable epistemic fork and an honest
    no-answer route. Neither the group count nor purpose sentence has any
    required placement or literal presence in the user-facing answer.
    A separate semantic reviewer judges whether the exchange feels natural.
    """
    asked={d['unknown_id'] for d in draft['information_dispositions'] if d['treatment']=='ask'}
    groups=draft['question_groups']
    ids=[]; seen_groups=set()
    for group in groups:
        gid=group['group_id'].strip()
        if not gid or gid in seen_groups:
            raise StateDyneError('Question rationale groups need distinct stable IDs')
        seen_groups.add(gid)
        members=group['unknown_ids']
        if not members or len(members)!=len(set(members)):
            raise StateDyneError('A question group must contain distinct actually asked questions')
        ids.extend(members)
        purpose=group['analytic_purpose'].strip()
        if len(purpose)<16:
            raise StateDyneError('Every question group needs a substantive INTERNAL information-value rationale')
        for field in ('if_first','if_second','if_unknown'):
            if len(group[field].strip())<12:
                raise StateDyneError('Question group needs two distinct judgment consequences and an unknown path')
        if group['if_first'].strip().casefold()==group['if_second'].strip().casefold():
            raise StateDyneError('Two answer paths cannot promise the same model update')
        if group['if_unknown'].strip().casefold() in (group['if_first'].strip().casefold(),group['if_second'].strip().casefold()):
            raise StateDyneError('Cannot pretend an unobserved answer supports either branch')
    if len(ids)!=len(set(ids)) or set(ids)!=asked:
        raise StateDyneError('Every asked question must be assigned exactly once to an internal decision-fork group; no unasked question may be added')


def validate_question_payoff(draft: dict, resolutions: list[dict]) -> None:
    """Follow-up must report a gain (including a meaningful null) naturally.

    The answer_anchor is any real excerpt from the composed answer; no fixed
    headings, two separate paragraphs, or verbatim explanation template is
    required. The independent reviewer remains responsible for semantic
    consistency between evidence_gained, still_unknown, and the answer.
    """
    report=draft['question_payoff']
    expected={r['group_id'] for r in resolutions}
    ids=report['covered_groups']
    if len(ids)!=len(set(ids)) or set(ids)!=expected:
        raise StateDyneError('Answer must account for all evaluated question groups, no more and no fewer')
    if not expected:
        if any(report[k].strip() for k in ('evidence_gained','still_unknown','answer_anchor')):
            raise StateDyneError('No new question results were received; do not invent a payoff')
        return
    gained=report['evidence_gained'].strip()
    remaining=report['still_unknown'].strip()
    anchor=report['answer_anchor'].strip()
    if len(gained)<17 or len(remaining)<17 or gained==remaining:
        raise StateDyneError('Follow-up must distinguish gained evidence from still-open uncertainties')
    if len(anchor)<14 or anchor not in draft['answer']:
        raise StateDyneError('User response must visibly communicate the gained/unchanged judgment without a forced two-sentence template')


def validate_question_resolution(ws, assessment: dict) -> None:
    expected={g['group_id'] for g in previous_question_groups(ws)}
    results=assessment['question_results']
    if len(results)!=len(expected) or {r['group_id'] for r in results}!=expected:
        raise StateDyneError('New evidence must explicitly resolve every prior asked-question group, even if user cannot answer')
    for record in results:
        if len(record['evidence_change'].strip())<16 or len(record['revised_judgment'].strip())<16:
            raise StateDyneError('A question response requires an actual evidence assessment and revised/unchanged judgment')
        if record['outcome']=='new_relation' and not (assessment['new_foci'] or assessment['affected_claim_ids'] or assessment['impact']=='rebuild'):
            raise StateDyneError('Claiming a new relation must actually affect a model, focus, or rebuild request')
