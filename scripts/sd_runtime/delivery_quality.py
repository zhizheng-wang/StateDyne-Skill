"""Observable floors for the independent final review of explanation and action.

This module cannot judge semantic truth. It checks that the independent
reviewer inspected every selected causal bridge, preserved uncertainties in
the actual answer, and compared actions with no additional activity.
"""
from __future__ import annotations
from .common import StateDyneError

CAUSAL_KINDS = frozenset({'mechanism', 'inference', 'prediction', 'point'})


def validate_delivery_quality(ws, audit: dict, draft: dict) -> None:
    active = ws.active_claims()
    chosen = set(draft['used_claim_ids'])
    # An intervention point also makes a causal claim about what changes the
    # outcome; challenge its key bridge, not just explanations of the past.
    expected = {cid for cid in chosen if active[cid]['kind'] in CAUSAL_KINDS}
    reviews = audit['causal_boundary_reviews']
    got = [r['claim_id'] for r in reviews]
    if len(got) != len(set(got)) or set(got) != expected:
        raise StateDyneError('Independent review must inspect exactly every selected causal/predictive/point claim')
    dispositions = {x['claim_id']: x['treatment'] for x in draft['claim_dispositions']}
    for item in reviews:
        cid = item['claim_id']
        claim = active[cid]
        if not item['contested_link'].strip() or not item['consequence_if_wrong'].strip():
            raise StateDyneError('Causal review needs an identified missing bridge and consequence if false')
        if item['evidence_grade'] != 'direct_observation' or claim['epistemic_status'] == 'hypothesis':
            if item['narrative_treatment'] == 'as_supported':
                raise StateDyneError('A hypothesized or indirectly supported causal link cannot be promoted into fact')
        if dispositions.get(cid) == 'conditional' and item['narrative_treatment'] == 'as_supported':
            raise StateDyneError('A conditionally selected claim cannot be audited as established fact')
        if item['narrative_treatment'] == 'explicitly_conditional':
            if dispositions[cid] == 'use':
                raise StateDyneError('Conditionally supported causal bridge cannot be used as a certain claim')
            if (not item['user_visible_limit'].strip() or
                    item['user_visible_limit'] not in draft['answer']):
                raise StateDyneError('The causal inference boundary must be visible in the exact delivered answer')
        elif item['narrative_treatment'] == 'requires_revision' and audit['verdict'] == 'pass':
            raise StateDyneError('A disputed causal bridge requires actual revision, not a passing final audit')

    # Only points independently *shown in this turn* need a new point-value
    # audit. Prior audited point explanations may be referenced by a later
    # actions/plan turn without repeating or silently re-ranking them.
    visible_points = {x['claim_id']: x for x in draft['delivery_units'] if x['kind'] == 'point'}
    point_reviews = audit['point_value_reviews']
    got_points = [r['point_claim_id'] for r in point_reviews]
    if len(got_points) != len(set(got_points)) or set(got_points) != set(visible_points):
        raise StateDyneError('Every newly visible intervention point needs its own value and priority review')
    for row in point_reviews:
        for field in ('intervention_location', 'causal_transmission', 'incremental_value',
                      'rank_reason', 'strongest_competitor', 'conditions_that_reorder',
                      'joint_value', 'action_feasibility_or_gap',
                      'user_visible_leverage', 'user_visible_value',
                      'user_visible_priority'):
            if not row[field].strip():
                raise StateDyneError(f'Point-value review missing concrete {field}')
        anchors = [row[key].strip() for key in ('user_visible_leverage','user_visible_value','user_visible_priority')]
        if len(set(anchors)) != 3 or any(a in b for i,a in enumerate(anchors) for j,b in enumerate(anchors) if i != j):
            raise StateDyneError('Point location/transmission, independent incremental value, and relative priority need distinct visible explanations')
        if not all(anchor in draft['answer'] for anchor in anchors):
            raise StateDyneError('Point location, incremental value and relative priority must each be visible in this exact turn')
        companions = row['companion_point_ids']
        if len(companions) != len(set(companions)) or row['point_claim_id'] in companions:
            raise StateDyneError('Point combination references must be distinct other points')
        available_points = ({cid for cid,c in active.items() if c['kind']=='point'} &
                            (set(visible_points) | ws.previously_delivered_interventions()['point']))
        if not set(companions).issubset(available_points):
            raise StateDyneError('Point combinations must reference real delivered current points')
        if row['combination_mode'] in ('complement','necessary_joint','substitute') and not companions:
            raise StateDyneError('A claimed point interaction must identify its paired point(s)')
        if row['combination_mode'] in ('independent', 'none_found') and companions:
            raise StateDyneError('Do not pretend no interaction while declaring companion points')
        if companions:
            anchor = row['user_visible_combination'].strip()
            if not anchor or anchor not in draft['answer']:
                raise StateDyneError('A claimed point combination or substitution must explain its joint value in the exact visible answer')
            if anchor in anchors or any(anchor in a for a in anchors):
                raise StateDyneError('A point combination needs a separate visible interaction explanation, not a recycled ranking sentence')
        elif row['user_visible_combination'].strip() and row['user_visible_combination'] not in draft['answer']:
            raise StateDyneError('An optional point interaction claim must appear in the delivered answer')
    # A plan is the actual organization of actions, not simply their names.
    # Require a separately visible explanation of combined effects, ordering,
    # feasibility and why it beats the best single action or no addition.
    visible_plans = {x['claim_id']:x for x in draft['delivery_units'] if x['kind']=='plan'}
    plan_reviews = audit['plan_combination_reviews']
    planned_ids = [r['plan_claim_id'] for r in plan_reviews]
    if len(planned_ids) != len(set(planned_ids)) or set(planned_ids) != set(visible_plans):
        raise StateDyneError('Every newly delivered plan needs a separate action-combination review')
    available_actions = (ws.previously_delivered_interventions()['action'] |
        {u['claim_id'] for u in draft['delivery_units'] if u['kind']=='action'})
    for row in plan_reviews:
        plan_id = row['plan_claim_id']
        selected_actions = row['action_claim_ids']
        if (not selected_actions or len(selected_actions) != len(set(selected_actions))
                or not set(selected_actions).issubset(available_actions)):
            raise StateDyneError('A delivered plan must combine/reference real actions previously or currently delivered')
        expected_action_links = {cid for cid in active[plan_id]['depends_on']
                                 if cid in available_actions and active[cid]['kind']=='action'}
        if set(selected_actions) != expected_action_links:
            raise StateDyneError('Plan action combination must account for all separately delivered action dependencies')
        if row['combination_mode'] in ('combined', 'conditional') and len(selected_actions) < 2:
            raise StateDyneError('A joint action plan requires multiple linked actions; single actions are not synergy')
        for field in ('dependency_and_sequence','gain_vs_best_single_or_no_action',
                      'feasibility_or_failure_boundary', 'user_visible_composition',
                      'user_visible_comparison'):
            if not row[field].strip():
                raise StateDyneError(f'Plan combination review is missing {field}')
        if (row['user_visible_composition'] not in draft['answer'] or
                row['user_visible_comparison'] not in draft['answer']):
            raise StateDyneError('Combined action sequence and gain vs best single/no action must be visible in the exact plan')
        if row['user_visible_composition'] == row['user_visible_comparison']:
            raise StateDyneError('Plan composition cannot stand in for a distinct comparison of its added value')
    readiness = audit['change_adoption_review']
    scope = ws.state.get('delivery_scope', ws.state['scope'])
    if scope == 'auto':
        scope = 'analysis'
    if readiness['status'] == 'not_relevant':
        if not readiness['relevance_reason'].strip():
            raise StateDyneError('A no-adoption finding needs a substantive reason')
        if ws.state.get('adoption_relevant') and scope in ('points','actions','plan') and audit['verdict']=='pass':
            raise StateDyneError('Material acceptance/habit/organizational transition cannot be skipped')
    else:
        for field in ('relevance_reason', 'protected_value_or_expected_loss',
                      'why_change_is_credible', 'start_while_old_state_persists',
                      'feedback_to_new_default', 'pace_and_threshold_alternatives'):
            if not readiness[field].strip():
                raise StateDyneError(f'Adoption review must examine {field}')
        if readiness['status'] == 'needs_revision' and audit['verdict']=='pass':
            raise StateDyneError('Unresolved change-formation bridge cannot be approved')
        if readiness['status'] == 'analysed' and scope in ('points','actions','plan'):
            if not readiness['user_visible_anchor'].strip() or readiness['user_visible_anchor'] not in draft['answer']:
                raise StateDyneError('Material human or organizational change mechanism needs a visible explanation')
    boundary = audit['stage_boundary_review']
    if boundary['delivered_scope'] != scope or not boundary['reason'].strip():
        raise StateDyneError('Independent review must identify the exact current delivery stage')
    if boundary['premature_future_content'] and audit['verdict']=='pass':
        raise StateDyneError('Cannot pass a response that jumped into a future stage without request')

    # An answer cannot replace earlier audited points with new convenient
    # actions. Each action must show which point it changes and WHY, and the
    # independent reviewer challenges that causal bridge per action.
    visible_actions = {u['claim_id']:u for u in draft['delivery_units'] if u['kind']=='action'}
    action_reviews = audit['action_point_reviews']
    reviewed_ids = [r['action_claim_id'] for r in action_reviews]
    if len(reviewed_ids) != len(set(reviewed_ids)) or set(reviewed_ids) != set(visible_actions):
        raise StateDyneError('Every newly delivered action requires its own point-transmission review')
    prior_points = ws.previously_delivered_interventions()['point']
    now_points = {u['claim_id'] for u in draft['delivery_units'] if u['kind']=='point'}
    eligible_points = prior_points | now_points
    for row in action_reviews:
        aid = row['action_claim_id']
        linked = row['point_claim_ids']
        if not linked or len(linked)!=len(set(linked)) or not set(linked).issubset(eligible_points):
            raise StateDyneError('An action may only point at real, previously reviewed intervention points')
        declared = set(active[aid]['depends_on'])
        if not set(linked).issubset(declared):
            raise StateDyneError('Action link must follow its separately stored causal dependencies')
        for field in ('changed_relation_and_path','distinct_gain_vs_no_action',
                      'strongest_competing_action','burden_and_failure_boundary',
                      'user_visible_path'):
            if not row[field].strip():
                raise StateDyneError(f'Independent action-point review requires {field}')
        if row['user_visible_path'] not in draft['answer']:
            raise StateDyneError('The point-to-action transmission must be explained visibly in this turn')
        if row['verdict']=='needs_revision' and audit['verdict']=='pass':
            raise StateDyneError('An action that fails to change its chosen point cannot pass release')

    action_claims = {cid for cid in chosen if active[cid]['kind'] == 'action'}
    challenge = audit['strategy_challenge']
    covered = challenge['selected_action_claim_ids']
    if len(covered) != len(set(covered)) or set(covered) != action_claims:
        raise StateDyneError('Strategy comparison must cover exactly the selected action claims')
    if not action_claims:
        if challenge['verdict'] != 'not_applicable':
            raise StateDyneError('Do not claim an action comparison when no action was actually delivered')
        return
    if challenge['verdict'] == 'not_applicable':
        raise StateDyneError('Delivered actions require a comparison against no added action')
    for key in ('no_extra_action_alternative', 'distinct_gain', 'added_burden',
                'overlap_or_monitoring_risk', 'when_alternative_wins', 'visible_comparison'):
        if not challenge[key].strip():
            raise StateDyneError(f'Action competition missing a concrete {key}')
    if challenge['visible_comparison'] not in draft['answer']:
        raise StateDyneError('The action/no-extra-action tradeoff must be visible to the user')
    if (challenge['verdict'] in ('needs_revision', 'prefer_no_extra_action')
            and audit['verdict'] == 'pass'):
        raise StateDyneError('A no-action-dominant or inadequate bundle cannot silently pass with the old actions')
