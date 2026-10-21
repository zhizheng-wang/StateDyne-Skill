"""Persistent research frontier for an evolving reality model.

This is an agenda of OBSERVABLE stored opportunities and unresolved questions,
not a private reasoning trace or a claim that any candidate is true.  It keeps
research continuation separate from the delivery-phase sequence.
"""
from __future__ import annotations

from copy import deepcopy

ENVIRONMENT_DIMENSIONS = frozenset({"environment", "actors", "rules_incentives"})
ENVIRONMENT_ROLES = frozenset({"environment_scout", "selection_scout", "environment"})


def is_fresh_relation(item: dict) -> bool:
    """A completed attempt is not new merely because a legacy state says open."""
    return (item.get("state") == "open" and not item.get("attempts", 0)
            and item.get("system_priority", "important") in ("blocking", "important")
            and bool(_clean(item.get("description"))))


def environment_relation_ids(state: dict, relation_ids: list[str]) -> list[str]:
    """Route load-bearing environment/selection findings through the real environment operator.

    Provenance and system dimension, not suggestive keywords, establish the route.
    No environment mechanism is invented for a domain without such evidence.
    """
    result = []
    opportunities = state.get("exploration_opportunities", {})
    for oid in relation_ids:
        item = opportunities.get(oid, {})
        origin = item.get("origin_job")
        job_role = state.get("jobs", {}).get(origin, {}).get("role", "")
        if (is_fresh_relation(item) and
                (item.get("system_dimension") in ENVIRONMENT_DIMENSIONS or
                 job_role in ENVIRONMENT_ROLES or origin in ENVIRONMENT_ROLES)):
            result.append(oid)
    return result


def _clean(value):
    return ' '.join(str(value or '').split())


def agenda(state: dict) -> list[dict]:
    """Build a stable, bounded-to-source *view* of all worthy unfinished work.

    No arbitrary top-N is applied here.  Completed/attempted branches are
    preserved in state but are not presented as freshly unexamined research.
    """
    output = []
    for obj in state.get('exploration_opportunities', {}).values():
        focus = _clean(obj.get('description'))
        if not is_fresh_relation(obj):
            continue
        route = 'self_research'
        priority = obj.get('system_priority') or 'important'
        output.append({'id': obj['id'], 'kind': 'new_relation', 'focus': focus,
                       'route': route, 'priority': priority, 'ready': True,
                       'source': obj.get('origin_job', ''), 'attempts': 0})
    for obj in state.get('unknowns', {}).values():
        # A disposition of 'defer', 'unavailable' or 'ask' does not resolve
        # the question. Earlier releases erased these from the user-visible
        # continuation even though no answer/evidence was obtained.
        if obj.get('state', 'open') not in ('open', 'defer', 'unavailable', 'ask') or obj.get('priority') not in ('blocking','important'):
            continue
        focus = _clean(obj.get('question'))
        if not focus:
            continue
        route = obj.get('route', 'unavailable')
        attempted = obj['id'] in state.get('investigated_unknowns', [])
        declined = (route == 'user' and state.get('task_thread', {}).get('user_input_policy')
                    == 'no_repeated_questions_without_invitation')
        # Keep unresolved questions available as CONDITIONAL knowledge, not as
        # another invitation to repeat a failed search or a declined interview.
        ready = not attempted and not declined and route != 'unavailable'
        if declined:
            route = 'conditional_no_user_question'
        if attempted:
            route = 'awaiting_changed_evidence'
        output.append({'id': obj['id'], 'kind': 'discriminator', 'focus': focus,
                       'route':route, 'priority':obj.get('priority'), 'ready':ready,
                       'source':obj.get('origin_job', ''), 'attempts':int(attempted),
                       'disposition':obj.get('state','open')})
    goal = state.get('goal_review') or {}
    if goal and state.get('task_thread', {}).get('status', 'active') == 'active':
        for i, candidate in enumerate(goal.get('alternatives', []), 1):
            if candidate.get('needs_user_choice') and _clean(candidate.get('target')):
                output.append({'id':f'goal-option:{goal.get("job_id", "review")}:{i}',
                               'kind':'goal_tradeoff', 'focus':_clean(candidate['target']) +
                               ' — ' + _clean(candidate.get('potential_gain')) +
                               ' / ' + _clean(candidate.get('tradeoff')),
                               'route':'compare_without_replacing_user_goal',
                               'priority':'important', 'source':goal.get('job_id', ''), 'attempts':0, 'ready':True})
    order = {'new_relation':0,'discriminator':1,'goal_tradeoff':2}
    weight = {'blocking':0,'important':1}
    output.sort(key=lambda x:(weight.get(x['priority'],2),order[x['kind']],x['id']))
    return deepcopy(output)


def unattempted_open_relations(state:dict) -> list[str]:
    """Route genuinely unattempted relation opportunities to the next search.

    Scheduler capacity governs batching, not an epistemic maximum.  Evidence
    and model-outside targeted queues are deduplicated by the caller.
    """
    items = [obj for obj in state.get('exploration_opportunities', {}).values()
             if is_fresh_relation(obj)]
    # Blockers come before other opportunities; insertion order is preserved
    # within each urgency class. No artificial top-N truncation.
    return [obj['id'] for obj in sorted(items,
            key=lambda x: 0 if x.get('system_priority') == 'blocking' else 1)]


def unattempted_environment_questions(state:dict) -> list[str]:
    """An environment worker can report a material unknown without an opportunity.

    Conceptual environmental investigation is distinct from actually acquiring
    evidence. A candidate can be probed once without falsely claiming its
    public documents or user-held data were obtained.
    """
    attempted = set(state.get('environment_questions_attempted', []))
    return [q['id'] for q in state.get('unknowns', {}).values()
            if q.get('origin') in ('environment', 'selection')
            and q.get('state', 'open') in ('open', 'defer', 'unavailable', 'ask')
            and q.get('priority') in ('blocking', 'important')
            and q['id'] not in attempted and _clean(q.get('question'))]


def meaningful_frontier(state:dict) -> bool:
    """Important unaddressed public/model-side research or user-selectable goals.

    Do not FORCE follow-up for an unanswered but already attempted private
    detail when no independently useful continuation is available.
    """
    return any(x.get('ready', False) for x in agenda(state))
