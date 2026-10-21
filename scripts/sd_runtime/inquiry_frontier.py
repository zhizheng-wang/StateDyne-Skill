"""Discovery-to-information lineage and value gates.

An epistemic question can matter by opening a new explanation or future
prediction without yet changing a present action. This module tracks observable
relationships; it cannot certify semantic truth, novelty or completeness.
"""
from __future__ import annotations
import re
from .common import StateDyneError
from .inquiry_contract import validate_question_groups, validate_question_payoff

VALUE_EFFECTS = frozenset({
    "changes_current_choice", "changes_explanation", "opens_testable_mechanism",
    "changes_prediction", "changes_action"})
ACTION_EFFECTS = frozenset({"changes_current_choice", "changes_action"})
DISCOVERY_EFFECTS = frozenset({"changes_explanation", "opens_testable_mechanism", "changes_prediction"})
DISCOVERY_ORIGINS = frozenset({"raw_residual", "reframe", "prediction", "environment", "selection", "goal", "system_map", "load_bearing"})


def discovery_inquiries(ws) -> list[dict]:
    """Expose new candidates and their actual routed discriminators to the scheduler.

    These are open epistemic tasks, not automatically questions for the user.
    A model-outside hypothesis may be kept conditional or rejected, but should
    not disappear simply because it does not change today's action.
    """
    active = ws.active_claims()
    result = []
    for q in ws.state['unknowns'].values():
        if q.get('state') in ('stale', 'addressed') or q['origin'] not in DISCOVERY_ORIGINS:
            continue
        linked = [active[cid] for cid in q['related_claims'] if cid in active]
        if not linked and q['origin'] not in ('system_map','load_bearing','goal'):
            continue
        origin_roles = sorted({ws.job_request(c['origin_job'])['role'] for c in linked})
        result.append({
            'unknown_id': q['id'], 'question': q['question'], 'origin': q['origin'],
            'route': q['route'], 'priority': q['priority'],
            'claim_ids': [c['id'] for c in linked], 'origin_roles': origin_roles,
            'predictions': list(dict.fromkeys(str(pred) for c in linked
                                               for pred in c.get('distinct_consequences', []))),
            'why_it_matters': q['why_it_matters'],
            'recognition_prompt': q.get('recognition_prompt', ''),
            'counter_cue': q.get('counter_cue', ''),
            'investigation_attempted': q['id'] in ws.state.get('investigated_unknowns', []),
        })
    # Stable, human-auditable presentation order for independent discovery:
    # protect blocking/important evidence first, then lift genuinely different
    # untested predictions ahead of routine refinements at the same urgency.
    # This ordering is a cue for the actual scheduler/editor, not proof that a
    # candidate is true or an instruction to ask every listed question.
    def rank(item):
        priority={'blocking':0, 'important':1, 'optional':2}.get(item['priority'],3)
        novel=(item['origin'] in ('prediction','reframe','raw_residual','environment','selection','goal','system_map')
               and bool(item['predictions'] or item['recognition_prompt']))
        return (priority, item['investigation_attempted'], 0 if novel else 1,
                0 if item['claim_ids'] else 1, item['unknown_id'])
    return sorted(result, key=rank)


def validate_inquiry_dispositions(ws, draft):
    """Prevent an independent explanatory candidate being silenced by action-only gates.

    The model can still reject/defer a weak candidate; an explanatory unknown
    need not be asked, and a public or calculable unknown must never be
    outsourced to the user. This is a structural *floor*, not semantic grading.
    """
    claims = ws.active_claims()
    choices = {d['claim_id']: d for d in draft['claim_dispositions']}
    seen_questions = set()
    for disp in draft['information_dispositions']:
        unknown = ws.state['unknowns'][disp['unknown_id']]
        effect = disp['decision_effect']
        ask = disp['treatment'] == 'ask'
        if ask:
            if (unknown.get('recognition_prompt') and unknown['priority'] in ('blocking', 'important')
                    and unknown['recognition_prompt'] not in disp['visible_question']):
                raise StateDyneError('A high-value recognition probe must reach the user in natural language, not only as a backend question')
            if (unknown.get('counter_cue') and unknown['priority'] in ('blocking', 'important')
                    and unknown['counter_cue'] not in draft['answer']):
                raise StateDyneError('A high-value recognition prompt must show its rival/counter-cue, not just confirm the preferred story')
            if effect not in VALUE_EFFECTS:
                raise StateDyneError('User questions that cannot change an explanation, discovery, prediction or action are not mandatory interviews')
            if unknown['route'] != 'user':
                raise StateDyneError('Do not outsource non-user information: actively acquire it or leave an explicit conditional limit')
            normalized = re.sub(r'[\W_]+', ' ', disp['visible_question'].casefold()).strip()
            # For genuinely *new* model-space inquiries, duplicate prompts
            # are evidence that the discovery is not reaching the question
            # frontier. Preserve legacy multi-question compatibility for
            # ordinary model-discrimination fixtures and earlier work.
            if unknown['origin'] in DISCOVERY_ORIGINS:
                if normalized in seen_questions:
                    raise StateDyneError('Duplicate novel-discovery questions do not increase information value')
                seen_questions.add(normalized)
            if effect in DISCOVERY_EFFECTS:
                if unknown['origin'] not in ('system_map','load_bearing','goal') and (
                    not unknown['related_claims'] or not any(cid in claims for cid in unknown['related_claims'])
                ):
                    raise StateDyneError('Epistemic-discovery questions require an actual linked candidate')
                if unknown['origin'] not in ('system_map','load_bearing','goal') and effect in ('opens_testable_mechanism', 'changes_prediction') and not any(
                    claims[cid].get('distinct_consequences') for cid in unknown['related_claims'] if cid in claims
                ):
                    raise StateDyneError('A question labeled novel prediction must link to a model with a differentiated predicted outcome')
            if (unknown['origin'] in DISCOVERY_ORIGINS and effect in DISCOVERY_EFFECTS
                    and unknown['priority'] in ('blocking', 'important') and draft['status'] == 'complete'):
                raise StateDyneError('An important new explanatory/predictive question cannot be asked while claiming a fully completed explanation')
        elif disp['visible_question'].strip():
            raise StateDyneError('Unasked questions may not masquerade as delivered inquiries')

        # A previously prioritized cross-model probe cannot silently degrade
        # into 'mere refinement' when the editor likes the incumbent story.
        # Explicitly rejected model candidates are exempt: there is no mandate
        # to ask every hypothetical question.
        if (unknown.get('portfolio_probe_id') and unknown['priority'] in ('important', 'blocking')
                and effect in ('refines_only', 'not_actionable') and disp['treatment'] != 'addressed'):
            live_selected = any(cid in claims and choices[cid]['treatment'] in ('use', 'conditional')
                                for cid in unknown['related_claims'])
            if live_selected:
                raise StateDyneError('An independently prioritized inquiry cannot be silently downgraded while its causal model is selected')

        if (disp['treatment'] == 'defer' and effect in DISCOVERY_EFFECTS
                and unknown['origin'] in DISCOVERY_ORIGINS and unknown['priority'] in ('important', 'blocking')):
            # The independent hypothesis can be rejected with a reason, or
            # preserved conditionally. When it is used in the answer, explain
            # on-screen why its missing discriminator need not block this stage.
            active_relevant = [cid for cid in unknown['related_claims']
                               if cid in claims and choices[cid]['treatment'] in ('use', 'conditional')]
            if active_relevant:
                explanation = disp['fallback_if_unknown'].strip()
                if not explanation or explanation not in draft['answer']:
                    raise StateDyneError('A deferred high-value novel-discovery probe needs a visible conditional reason, not silent suppression')
    validate_question_groups(draft)
    validate_question_payoff(draft, ws.state.get('latest_question_resolution', []))


def pending_self_research(ws) -> list[str]:
    """Find important obtainable evidence never actually investigated.

    Only the locally available routes are automatically queued: material
    searches and calculations. Web searching requires an explicitly enabled
    and available tool. User-held / unavailable questions are never queued.
    """
    researched = set(ws.state.get('investigated_unknowns', []))
    web = ws.state['config'].get('web_search_enabled', False)
    actionable_routes = {'materials', 'calculation'} | ({'public_source'} if web else set())
    return [q['unknown_id'] for q in discovery_inquiries(ws)
            if q['unknown_id'] not in researched
            and q['priority'] in ('blocking','important')
            and q['route'] in actionable_routes]
