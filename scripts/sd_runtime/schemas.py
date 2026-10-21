"""Small strict schemas for observable work products, not private reasoning."""
from __future__ import annotations
from typing import Any
from .common import StateDyneError

S = {"type": "string"}
B = {"type": "boolean"}
I = {"type": "integer"}

def arr(item):
    return {"type": "array", "items": item}

def enum(*values):
    return {"type": "string", "enum": list(values)}

def obj(**properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}

EVIDENCE = obj(source_id=S, quote=S)
MECHANISM = obj(inputs=arr(S), conditions=arr(S), transformation=S,
                intermediate_states=arr(S), outputs=arr(S), feedback=S, scope=S)
CLAIM = obj(local_id=S, kind=enum("mechanism", "inference", "prediction", "point", "action", "plan"),
            statement=S, epistemic_status=enum("hypothesis", "inference"),
            mechanism=MECHANISM, evidence=arr(EVIDENCE), depends_on=arr(S),
            alternatives=arr(S), distinct_consequences=arr(S))
UNKNOWN = obj(local_id=S, question=S, why_it_matters=S,
              origin=enum("model_discrimination", "raw_residual", "reframe", "prediction", "adoption", "environment", "selection", "goal", "system_map", "load_bearing"),
              route=enum("materials", "calculation", "public_source", "user", "unavailable"),
              priority=enum("blocking", "important", "optional"), related_claims=arr(S))
WORK = obj(summary=S, claims=arr(CLAIM), unknowns=arr(UNKNOWN),
           opportunities=arr(S), no_increment_reason=S)
FOCAL = obj(local_id=S, evidence=arr(EVIDENCE), observation=S,
            unexplained_difference=S, why_material=S,
            priority=enum("critical", "supporting"))
FRAME = obj(foci=arr(FOCAL), no_focus_reason=S)
# An objective-scoped model of the whole relevant system. Explicitly marking a
# dimension not material is preferable to inventing its missing contents.
SYSTEM_DIMENSIONS = ("goal", "boundary", "internal_process", "upstream_inputs",
                     "downstream_results", "environment", "actors", "rules_incentives",
                     "history", "feedback", "model_outside")
SYSTEM_COVERAGE = obj(dimension=S,
    state=enum("represented", "open", "not_material"),
    basis=enum("reported", "inferred", "hypothesized", "unavailable", "not_applicable"),
    observed_or_hypothesized=S, missing=S, why_material=S,
    evidence=arr(EVIDENCE),
    route=enum("materials", "calculation", "public_source", "user", "unavailable"),
    priority=enum("blocking", "important", "optional"))
SYSTEM_LINK = obj(from_dimension=S, to_dimension=S,
    link=S, kind=enum("hypothesized_causation", "observed_relation", "constraint", "information_flow", "feedback", "unknown"),
    evidence=arr(EVIDENCE))
SYSTEM_MAP = obj(goal_text=S, goal_basis=enum("explicit", "inferred", "missing"),
    goal_evidence=arr(EVIDENCE), success_condition=S, protected_constraints=arr(S),
    working_boundary=S, boundary_reason=S,
    coverage=arr(SYSTEM_COVERAGE), links=arr(SYSTEM_LINK),
    whole_model_gap=S, no_material_gap_reason=S)
# Objective calibration is independent of the system-map author's framing.
# Alternatives are invitations to the user, never silent replacement goals.
VALUE_AXIS = obj(label=S, content=S, basis=enum("explicit", "inferred", "hypothesized"),
                 evidence=arr(EVIDENCE), distinct_from=S, loss_if_collapsed=S)
GOAL_OPTION = obj(target=S, potential_gain=S, tradeoff=S,
                  evidence_or_test=S, needs_user_choice=B)
GOAL_QUESTION = obj(question=S, why_it_matters=S,
                    route=enum("materials", "calculation", "public_source", "user", "unavailable"),
                    priority=enum("blocking", "important", "optional"))
GOAL_REVIEW = obj(current_target=S, basis=enum("explicit", "inferred", "missing"),
                  source_evidence=arr(EVIDENCE), observable_success=S,
                  valued_dimensions=arr(VALUE_AXIS), alternatives=arr(GOAL_OPTION),
                  unresolved=arr(GOAL_QUESTION), gap_or_conflict=S,
                  adequate_existing_goal_reason=S)
# A natural conversation can ask several questions for one discriminating reason;
# record the *payoff* before asking, and compare it with the next answer.
QUESTION_RESULT = obj(group_id=S,
    outcome=enum("supports_first", "supports_second", "mixed", "unknown", "new_relation"),
    evidence_change=S, revised_judgment=S)
DELTA_ASSESSMENT = obj(impact=enum("local", "rebuild"), reason=S,
    affected_claim_ids=arr(S), affected_unknown_ids=arr(S),
    goal_or_boundary_changed=B, newly_relevant_difference=S, new_foci=arr(FOCAL),
    question_results=arr(QUESTION_RESULT))

FOCUS_COVERAGE = obj(focus_id=S, status=enum("explained", "partial", "open", "not_material"),
                     candidate_claim_ids=arr(S), missing_or_explained_bridge=S,
                     unreported_prediction=S, discriminator=S, reason=S)
OPERATORS = ("acquire", "deepen", "counterfactual", "predict", "reframe", "environment", "transfer", "innovate", "adoption", "change", "finish")
SEARCH_SPACE_ASSESSMENT = obj(
    judgment=enum("new_testable_space", "no_new_space_after_search", "missing_search"),
    candidate_claim_ids=arr(S),
    prior_representation_limit=S,
    tested_alternative_representation=S,
    unreported_outcome=S,
    discriminating_observation=S,
    comparison_reason=S)
SYSTEM_COVERAGE_DISPOSITION = obj(dimension=S,
    resolution=enum("search", "conditional", "not_material_after_review"),
    rationale=S, evidence_or_next_action=S)
ENTRY_REVIEW = obj(system_coverage_dispositions=arr(SYSTEM_COVERAGE_DISPOSITION),
                   search_space_assessment=SEARCH_SPACE_ASSESSMENT, verdict=enum("pass", "reopen"), new_foci=arr(FOCAL), coverage=arr(FOCUS_COVERAGE), examined_contrasts=arr(S),
                   missing_relation=S, why_material=S,
                   next_operator=enum("deepen", "counterfactual", "predict", "reframe", "acquire", "innovate", "adoption", "change"),
                   required_new_prediction_or_test=S, no_gap_reason=S)
# The probe portfolio is an independently executed hypothesis tournament.
# It admits both tests of existing candidates and explicitly unmodelled
# relation families. No fixed number of probes is required.
PROBE = obj(local_id=S, claim_ids=arr(S), model_gap=S, question=S,
            unreported_outcome=S, rival_outcome=S, why_distinguishes=S,
            # Separate an internal technical discriminator from a natural, neutral
            # recognition cue; the counter-cue protects against guided memories.
            recognition_prompt=S, counter_cue=S,
            route=enum("materials", "calculation", "public_source", "user", "unavailable"),
            importance=enum("critical", "important", "optional"),
            advance=B, reason=S)
EXPLORATION_ATTEMPT = obj(local_id=S,
    focus=enum("outside_current_model", "upstream_environment", "selection_or_measurement",
               "counterfactual_baseline", "within_current_model"),
    incumbent_limit=S, alternative_representation=S, distinct_prediction=S,
    rival_prediction=S, evidence_route=enum("materials", "calculation", "public_source", "user", "unavailable"),
    outcome=enum("advanced", "deferred", "null_after_search"), probe_local_ids=arr(S), reason=S)
PROBE_PORTFOLIO = obj(covered_representation=S, exploration_attempts=arr(EXPLORATION_ATTEMPT),
                      probes=arr(PROBE), null_search_reason=S)
# A separate adversarial pass on the *load-bearing* premises of explanations,
# decisions, computations and interventions. No field certifies semantic truth.
BURDEN_TEST = obj(local_id=S, claim_ids=arr(S), proposition=S,
    role=enum("observation", "derived_measure", "causal_bridge", "forecast",
              "objective_or_value", "intervention", "scope_or_source"),
    support=enum("anchored", "recomputed", "conditional", "unsupported", "contradicted"),
    evidence=arr(EVIDENCE), importance=enum("critical", "important", "minor"),
    hidden_premise=S, strongest_rival=S, differentiated_outcome=S,
    decisive_test=S, route=enum("materials", "calculation", "public_source", "user", "unavailable"),
    disposition=enum("retain", "investigate", "downgrade", "reject"), reason=S,
    quantified_incremental_claim=B)
RECALC = obj(local_id=S, claim_ids=arr(S), expression=S, stated_result=S,
    absolute_tolerance=S, unit=S, input_basis=S, evidence=arr(EVIDENCE),
    interpretation_limit=S)
ROBUSTNESS_CHECK = obj(local_id=S, claim_ids=arr(S),
    kind=enum("forecast_sensitivity", "incrementality_counterfactual", "strong_alternative_baseline", "selection_or_metric_bias"),
    base_assumption=S, changed_assumption=S, base_outcome=S, changed_outcome=S,
    impact_on_judgment=S, would_reverse=B, evidence_route=enum("materials", "calculation", "public_source", "user", "unavailable"),
    evidence_or_test=S, visible_limit=S)
# Quantified program impacts must reconcile gross outcome, the no-program
# baseline and displacement in a single compatible unit. With no reliable
# counterfactual, record the unresolved bridge instead of inventing numbers.
NET_EFFECT = obj(local_id=S, claim_ids=arr(S),
    status=enum("reconciled", "counterfactual_unavailable"),
    gross_with_program=S, gross_without_program=S, displaced_or_transferred=S,
    stated_net_increment=S, absolute_tolerance=S, unit=S,
    input_basis=S, visible_limit=S)
LOAD_BEARING = obj(thesis_at_risk=S, as_of_scope=S, as_of_handling=S,
    examined_claim_ids=arr(S), tests=arr(BURDEN_TEST), recalculations=arr(RECALC),
    robustness_checks=arr(ROBUSTNESS_CHECK), net_effect_checks=arr(NET_EFFECT),
    best_countermodel=S, decision_reversal=S, discovery_limit=S)
SCHEDULE = obj(operator=enum(*OPERATORS), target_ids=arr(S), rationale=S,
               expected_difference=S, strongest_alternative=S,
               delivery_scope=enum("analysis", "points", "actions", "plan"),
               adoption_relevant=B, scope_reason=S)
SEARCH_TASK = obj(operator=enum(*[o for o in OPERATORS if o != "finish"]),
                  target_ids=arr(S), opportunity_ids=arr(S), rationale=S,
                  expected_difference=S, strongest_alternative=S,
                  why_parallel_safe=S)
SEARCH_PLAN = obj(decisions=arr(SEARCH_TASK), finish=B, finish_reason=S,
                  delivery_scope=enum("analysis", "points", "actions", "plan"),
                  adoption_relevant=B, scope_reason=S)
# Consult only the actual user request when auto scope proposes skipping to
# interventions. A source quote is required to authorise a new stage.
SCOPE_INTENT = obj(requested_scope=enum("analysis", "points", "actions", "plan"),
                   request_basis=enum("explicit", "implicit", "missing"),
                   user_request_quote=S, reason=S, protected_user_objective=S)
DISPOSITION = obj(claim_id=S, treatment=enum("use", "conditional", "not_selected", "reject"), reason=S)
INFO_DISPOSITION = obj(unknown_id=S, treatment=enum("ask", "defer", "unavailable", "addressed"),
                       reason=S, visible_question=S, evidence=arr(EVIDENCE),
                       # Historical field name retained for existing worker compatibility.
                       # Its meaning is now ANY substantial epistemic or action effect,
                       # not only an immediate choice or intervention.
                       decision_effect=enum("changes_current_choice", "changes_explanation",
                                            "opens_testable_mechanism", "changes_prediction",
                                            "changes_action", "refines_only", "not_actionable"),
                       fallback_if_unknown=S)
# Route an ordinary user turn BEFORE updating the main task. This is an
# observable worker judgment, never an attempt to read hidden model thoughts.
TURN_ROUTE = obj(route=enum("main_update", "side", "next", "expand", "replace_goal", "pause", "close"),
    quoted_trigger=S, reason=S, preserves_primary_goal=B,
    user_declines_more_questions=B, user_invites_questions=B,
    expansion_focus=S, no_new_information_route=S)
# Actual cross-worker result competition, separate from the composer and final
# accuracy reviewer. A minority alternative cannot lose just by being outvoted.
DECISION_TOURNAMENT_ENTRY = obj(local_id=S, claim_ids=arr(S), rival_claim_ids=arr(S),
    generation_path=S, distinct_prediction=S, evidence_boundary=S,
    implementation_path=S, user_value_delta=S, compared_to_baseline=S,
    verdict=enum("preferred", "serious_rival", "investigate", "rejected"),
    why_this_disposition=S)
RESEARCH_OPENING = obj(needed=B, focus=S, expected_difference=S,
    evidence_route=enum("materials", "calculation", "public_source", "user", "unavailable"))
DECISION_TOURNAMENT = obj(goal_at_stake=S, comparison_basis=S,
    entries=arr(DECISION_TOURNAMENT_ENTRY),
    biggest_reversal_condition=S, no_independent_value_reason=S,
    research_opening=RESEARCH_OPENING)
# A separately auditable navigation bridge; factual answers do not have to
# invent a new stage. A side reply may use the prior primary scope.
NAVIGATION = obj(mode=enum("primary", "side"),
    primary_stage=enum("analysis", "points", "actions", "plan"),
    next_stage=enum("points", "actions", "plan", "none"),
    next_offer=S, expansion_offer=S, visible_anchor=S, reason=S)
# Optional, auditable source binding for concrete research continuation.
# Old completed turns remain valid; an active *new-relation/goal* frontier in
# v11 requires these fields at release time, not only a generic offer.
NAVIGATION["properties"]["research_focus_id"] = S
NAVIGATION["properties"]["research_focus_excerpt"] = S
# A user-authored quote showing that THIS reply should end without a sales pitch
# for continuing research. Preserve the verified stage and actual agenda.
NAVIGATION["properties"]["quiet_reply_quote"] = S
# Explicit user-facing delivery bindings: the runtime verifies that requested
# intervention stages appear independently in the *actual* answer.
DELIVERY_UNIT = obj(kind=enum("point", "action", "plan"), claim_id=S,
                    visible_text=S, comparison=S)
FOCUS_DISPOSITION = obj(focus_id=S, status=enum("explained", "conditional", "open", "not_material"),
                         linked_claim_ids=arr(S), visible_resolution=S, rationale=S)
# Internal decision-fork contract. Do NOT use analytic_purpose as mandatory
# frontstage text or heading; the final answer can express purpose organically.
# Two distinct predictions and a no-answer route remain non-negotiable.
QUESTION_GROUP = obj(group_id=S, unknown_ids=arr(S), analytic_purpose=S,
    if_first=S, if_second=S, if_unknown=S)
# One freeform excerpt anchors the honest update in ordinary user-facing prose;
# its placement and wording are not scripted by backend field names.
QUESTION_PAYOFF = obj(covered_groups=arr(S), evidence_gained=S, still_unknown=S,
                      answer_anchor=S)
# Cross-section identity for load-bearing numerical outcomes. The writer must
# separately anchor the headline, analytic body and closing treatment; omission
# is allowed only when that section does not state this measure. No guessed
# point estimates or required per-task fixed number of quantitative claims.
PIVOTAL_QUANTITY = obj(local_id=S, claim_ids=arr(S), metric=S,
    measurement_basis=S, population_and_scope=S, period=S, unit=S,
    measure_kind=enum("gross", "net_increment", "eligible_net_increment", "valuation", "rate", "other"),
    scenario=S, headline_anchor=S, headline_value=S,
    body_anchor=S, body_value=S, conclusion_anchor=S, conclusion_value=S,
    relation=enum("same_measure", "different_measures_explained", "single_location"),
    visible_reconciliation=S, assumption_or_limit=S)
# Conjunctive result: each target predicate must hold on the SAME real unit,
# not merely in different subgroup totals. A conditional bridge is permitted.
OBJECTIVE_CONDITION = obj(name=S,
    status=enum("observed_same_entities", "estimated", "unverified"),
    evidence_or_assumption=S)
OBJECTIVE_JOIN = obj(local_id=S, quantity_ids=arr(S), claim_ids=arr(S),
    target_entity_or_cohort=S, necessary_conditions=arr(OBJECTIVE_CONDITION),
    joint_status=enum("observed_intersection", "conditional_intersection", "unresolved"),
    same_entity_basis=S, missing_join_or_displacement=S,
    visible_joint_anchor=S, visible_uncertainty_anchor=S)
# High-impact observed numerical inputs AND derived values. The conversion
# formula returns canonical base units (USD, shares, completed units, etc.).
# No preset count: only numbers that bear the actual decision or headline.
NUMERIC_SOURCE_CHECK = obj(local_id=S,
    kind=enum("sourced_fact", "derived", "scenario"),
    base_dimension=enum("usd", "usd_per_year", "shares", "housing_units", "percent"),
    population_and_scope=S, period=S,
    visible_anchor=S, displayed_value=S, displayed_unit=S,
    source_tier=enum("registered_material", "retrieved_primary", "retrieved_secondary",
                     "derived_from_checked_inputs", "unverified_assumption"),
    source_locator=S, source_quote=S, source_value=S, source_unit=S,
    formula=S, absolute_tolerance_base=S, user_visible_limit=S)
DRAFT = obj(answer=S, status=enum("complete", "provisional", "needs_information"), goal_line=S,
            navigation=NAVIGATION, pivotal_quantities=arr(PIVOTAL_QUANTITY),
            objective_joins=arr(OBJECTIVE_JOIN),
            numeric_source_checks=arr(NUMERIC_SOURCE_CHECK),
            question_groups=arr(QUESTION_GROUP), question_payoff=QUESTION_PAYOFF,
            focus_dispositions=arr(FOCUS_DISPOSITION),
            claim_dispositions=arr(DISPOSITION), information_dispositions=arr(INFO_DISPOSITION),
            used_claim_ids=arr(S), delivery_units=arr(DELIVERY_UNIT),
            delivery_limit_reason=S)
ISSUE = obj(issue_id=S, severity=enum("blocking", "improvement"), target_ids=arr(S),
            finding=S, next_operator=enum(*OPERATORS), repair_request=S)
# The existing independent final reviewer does both checks without spawning a
# mandatory extra worker: one proof boundary per selected causal/point claim,
# and one cross-action comparison against no *additional* intervention.
CAUSAL_BOUNDARY = obj(claim_id=S, contested_link=S,
    evidence_grade=enum("direct_observation", "partial_indirect", "unobserved"),
    narrative_treatment=enum("as_supported", "explicitly_conditional", "requires_revision"),
    user_visible_limit=S, consequence_if_wrong=S)
STRATEGY_CHALLENGE = obj(selected_action_claim_ids=arr(S),
    no_extra_action_alternative=S, distinct_gain=S, added_burden=S,
    overlap_or_monitoring_risk=S, when_alternative_wins=S,
    visible_comparison=S,
    verdict=enum("not_applicable", "additional_action_justified", "conditional",
                 "prefer_no_extra_action", "needs_revision"))
# The semantic reviewer must inspect every point actually explained in THIS
# turn. These are review observations, not hidden weights or a fixed point quota.
POINT_VALUE_REVIEW = obj(point_claim_id=S,
    intervention_location=S, causal_transmission=S, incremental_value=S,
    rank_reason=S, strongest_competitor=S, conditions_that_reorder=S,
    combination_mode=enum("independent", "complement", "necessary_joint",
                          "substitute", "conditional", "none_found"),
    companion_point_ids=arr(S), joint_value=S, action_feasibility_or_gap=S,
    user_visible_leverage=S, user_visible_value=S,
    user_visible_priority=S, user_visible_combination=S)
# Human-readable plans may select one good action or combine truly complementary actions.
# Do not silently call a set of independent tasks a synergy.
PLAN_COMBINATION_REVIEW = obj(plan_claim_id=S, action_claim_ids=arr(S),
    combination_mode=enum("combined", "conditional", "single_preferred"),
    dependency_and_sequence=S, gain_vs_best_single_or_no_action=S,
    feasibility_or_failure_boundary=S,
    user_visible_composition=S, user_visible_comparison=S)
# Understanding the old process does not establish a usable transition.
# "not_relevant" is allowed for tasks without a material human/organizational
# adoption or habit barrier; never invent a psychological motive to fill this.
CHANGE_ADOPTION_REVIEW = obj(
    status=enum("not_relevant", "analysed", "needs_revision"),
    relevance_reason=S, protected_value_or_expected_loss=S,
    why_change_is_credible=S, start_while_old_state_persists=S,
    feedback_to_new_default=S, pace_and_threshold_alternatives=S,
    user_visible_anchor=S)
STAGE_BOUNDARY_REVIEW = obj(delivered_scope=enum("analysis", "points", "actions", "plan"),
    premature_future_content=B, reason=S)
QUANTITY_REVIEW = obj(quantity_id=S,
    verdict=enum("consistent", "distinction_supported", "needs_revision"),
    source_scope_and_units=S, competing_numeric_interpretation=S,
    effect_on_conclusion=S)
NUMERIC_SOURCE_REVIEW = obj(local_id=S,
    verdict=enum("verified_fact", "checked_derivation", "conditional_assumption", "needs_revision"),
    verified_source_locator=S, actual_source_measure=S, original_unit_and_date=S,
    independent_unit_reconciliation=S, consequence_if_wrong=S,
    independent_retrieval_receipt=S)
OBJECTIVE_JOIN_REVIEW = obj(local_id=S,
    verdict=enum("joint_verified", "conditional_only", "needs_revision"),
    entity_and_time_match=S, strongest_non_joint_alternative=S,
    evidence_or_missing_join=S, consequence_for_conclusion=S)
# Independent review of each actually delivered action, rather than only
# an aggregate 'the plan is good' self-certification. Point ID references
# are verified against the active causal graph and prior *published* points.
ACTION_POINT_REVIEW = obj(action_claim_id=S, point_claim_ids=arr(S),
    changed_relation_and_path=S, distinct_gain_vs_no_action=S,
    strongest_competing_action=S, burden_and_failure_boundary=S,
    user_visible_path=S, verdict=enum("supported", "conditional", "needs_revision"))
AUDIT = obj(verdict=enum("pass", "revise"), issues=arr(ISSUE),
            action_point_reviews=arr(ACTION_POINT_REVIEW),
            objective_join_reviews=arr(OBJECTIVE_JOIN_REVIEW),
            objective_join_coverage_reason=S,
            quantity_reviews=arr(QUANTITY_REVIEW), numeric_coverage_reason=S,
            numeric_source_reviews=arr(NUMERIC_SOURCE_REVIEW), source_fact_coverage_reason=S,
            examined_focus_ids=arr(S),
            examined_claim_ids=arr(S), examined_unknown_ids=arr(S),
            remaining_limits=arr(S),
            causal_boundary_reviews=arr(CAUSAL_BOUNDARY),
            point_value_reviews=arr(POINT_VALUE_REVIEW),
            plan_combination_reviews=arr(PLAN_COMBINATION_REVIEW),
            change_adoption_review=CHANGE_ADOPTION_REVIEW,
            stage_boundary_review=STAGE_BOUNDARY_REVIEW,
            strategy_challenge=STRATEGY_CHALLENGE)
SCHEMAS = {"decision_tournament": DECISION_TOURNAMENT, "turn_route": TURN_ROUTE, "goal_review": GOAL_REVIEW, "frame": FRAME, "system_map": SYSTEM_MAP, "delta_assessment": DELTA_ASSESSMENT, "work": WORK, "schedule": SCHEDULE,
           "search_plan": SEARCH_PLAN, "scope_intent": SCOPE_INTENT, "probe_portfolio": PROBE_PORTFOLIO, "load_bearing": LOAD_BEARING, "entry_review": ENTRY_REVIEW,
           "draft": DRAFT, "audit": AUDIT}


def validate(value: Any, schema: dict, path: str = "$") -> None:
    """Validate exactly the subset we generate; no dependency on jsonschema."""
    kind = schema["type"]
    valid = ((kind == "object" and isinstance(value, dict)) or
             (kind == "array" and isinstance(value, list)) or
             (kind == "string" and isinstance(value, str)) or
             (kind == "boolean" and isinstance(value, bool)) or
             (kind == "integer" and isinstance(value, int) and not isinstance(value, bool)))
    if not valid:
        raise StateDyneError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise StateDyneError(f"{path}: invalid enum value {value!r}")
    if kind == "object":
        required = set(schema.get("required", schema["properties"]))
        observed = set(value)
        missing = required - observed
        extra = observed - set(schema["properties"])
        if missing or extra:
            raise StateDyneError(f"{path}: missing={sorted(missing)}, extra={sorted(extra)}")
        for key in value:
            validate(value[key], schema["properties"][key], f"{path}.{key}")
    if kind == "array":
        for index, item in enumerate(value):
            validate(item, schema["items"], f"{path}[{index}]")
