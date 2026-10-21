"""Effect-first cognitive search: independent raw discovery, adaptive search bundles.

Parallel work is allowed only from a shared immutable snapshot. A semantic
discovery is never guaranteed by the presence of a job, field or audit record.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from .common import StateDyneError, atomic_write, digest, read_json, save_json, text_digest
from .schemas import OPERATORS, SCHEMAS, validate
from .store import Workspace
from .frontier import record_focus, check_boundary, ensure_repair_changed_relation
from .diversity import check_raw_discovery_diversity
from .probe_bridge import unbridged_model_outside
from .inquiry_frontier import pending_self_research
from .inquiry_contract import validate_question_resolution
from .probe_portfolio import register_portfolio, pending_model_expansion
from .system_map import register_system_map, pending_coverage_opportunities
from .goal_review import register_goal_review
from .load_bearing import register_load_bearing, snapshot_signature
from .priority_dispatch import priority_batch
from .breakthrough import validate_breakthrough
from .decision_tournament import register_tournament, tournament_signature
from .research_agenda import (unattempted_open_relations,
    unattempted_environment_questions, environment_relation_ids)

ROOT = Path(__file__).resolve().parents[2]
ROLE_FILE = {"frame": "frame", "discovery": "discovery", "reframe": "reframe", "contrast_probe": "contrast_probe",
             "entry_review": "entry_review", "entry_repair": "entry_repair", "schedule": "schedule",
             "blind_challenge": "blind_challenge", "environment_scout": "environment_scout", "goal_scout": "goal_scout", "selection_scout": "selection_scout", "relation_scout": "relation_scout",
             "probe_portfolio": "probe_portfolio", "open_search": "open_search", "load_bearing": "load_bearing", "change_forward": "change_forward", "change_backward": "change_backward", "change_portfolio": "change_portfolio", "change_action_probe": "change_action_probe",
             "compose": "compose", "audit": "audit", "scope_intent": "scope_intent", "frontier_scout": "frontier_scout", "evidence_scout": "evidence_scout",
             "system_map": "system_map", "system_reconcile": "system_map",
             "delta_assess": "delta_assess", "delta_integrate": "delta_integrate", "delta_challenge": "delta_challenge",
             "turn_router": "turn_router", "value_frontier": "value_frontier", "breakthrough_scout": "breakthrough_scout", "decision_tournament": "decision_tournament"}


def instructions(role: str) -> str:
    portability = (ROOT / "references/cross-model-contract.md").read_text(encoding="utf-8")
    core = (ROOT / "references/core.md").read_text(encoding="utf-8")
    kernel = (ROOT / "references/workers-quality-kernel.md").read_text(encoding="utf-8")
    breakthrough = (ROOT / "references/breakthrough-engine.md").read_text(encoding="utf-8")
    closure = (ROOT / "references/closure-and-novelty.md").read_text(encoding="utf-8")
    generative_loop = (ROOT / "references/generative-loop.md").read_text(encoding="utf-8")
    result_realization = (ROOT / "references/result-realization.md").read_text(encoding="utf-8")
    file = ROLE_FILE.get(role, "operation")
    specialized = ""
    if role in {"turn_router", "value_frontier", "compose", "audit", "schedule", "delta_assess", "goal_scout", "system_map", "decision_tournament"}:
        specialized += (ROOT / "references/long-horizon-autonomy.md").read_text(encoding="utf-8") + "\n\n"
    if role in {"value_frontier", "load_bearing", "compose", "audit", "schedule", "goal_scout", "change_portfolio"}:
        specialized += (ROOT / "references/high-value-reframing.md").read_text(encoding="utf-8") + "\n\n"
    if role in {"system_map", "goal_scout", "relation_scout", "compose", "audit"}:
        specialized += (ROOT / "references/goal-calibration.md").read_text(encoding="utf-8") + "\n\n"
    if role in {"selection_scout", "environment_scout", "environment", "compose", "audit"}:
        specialized += (ROOT / "references/selection-mechanisms.md").read_text(encoding="utf-8") + "\n\n"
    if role in {"reframe", "contrast_probe", "relation_scout", "goal_scout", "compose", "audit"}:
        specialized += (ROOT / "references/relational-structure.md").read_text(encoding="utf-8") + "\n\n"
    if role in {"compose", "audit", "schedule", "delta_assess", "delta_integrate"}:
        specialized += (ROOT / "references/continuation-contract.md").read_text(encoding="utf-8") + "\n\n"
    if role in {"compose", "audit", "schedule", "load_bearing", "decision_tournament", "frontier_scout", "evidence_scout", "relation_scout", "probe_portfolio"}:
        specialized += (ROOT / "references/information-followthrough.md").read_text(encoding="utf-8") + "\n\n"
    if role in {"compose", "audit", "load_bearing", "schedule"}:
        specialized += (ROOT / "references/result-consistency.md").read_text(encoding="utf-8") + "\n\n"
    if role in {"compose", "audit", "load_bearing", "schedule", "evidence_scout", "environment_scout", "environment"}:
        specialized += (ROOT / "references/numeric-source-trace.md").read_text(encoding="utf-8") + "\n\n"
    if role in {"change_forward", "change_backward", "change_portfolio", "change_action_probe", "compose", "audit", "adoption"}:
        specialized += (ROOT / "references/intervention-leverage.md").read_text(encoding="utf-8") + "\n\n" + (ROOT / "references/change-formation.md").read_text(encoding="utf-8") + "\n\n" + (ROOT / "references/change-action-preflight.md").read_text(encoding="utf-8")
    if role in {"goal_scout", "system_map", "selection_scout", "relation_scout", "load_bearing", "schedule", "compose", "audit", "decision_tournament", "change_forward", "change_backward", "change_portfolio", "change_action_probe", "evidence_scout"}:
        specialized += "\n\n" + (ROOT / "references/outcome-intersection.md").read_text(encoding="utf-8")
    return (portability + "\n\n" + core + "\n\n" + generative_loop + "\n\n"
            + (result_realization + "\n\n" if role in {"compose", "audit", "schedule", "value_frontier", "goal_scout", "change_forward", "change_backward", "change_portfolio", "change_action_probe", "delta_assess", "turn_router"} else "")
            + breakthrough + "\n\n"
            + (closure + "\n\n" if role in {"schedule", "compose", "audit", "value_frontier",
                 "turn_router", "delta_assess", "delta_integrate", "breakthrough_scout"} else "")
            + kernel + "\n\n" + specialized + "\n\n" + (ROOT / f"references/operators/{file}.md").read_text(encoding="utf-8")
            + ("\n\n# 11.2 final dispatch priority: visible intervention value and composition\n"
               "Read the user's real requested outcome first. Compare genuinely different ways that outcome is created; "
               "reuse their own working methods. A dated checklist is not itself a mechanism. Every point must explain the real generating relation, net incremental value, and priority over a concrete rival in the actual answer. If points combine, show each single outcome vs their joint outcome; plans compare coordinated actions vs the best single or no added action. "
               "If the user explicitly wants only usable help now, give it without forcing a continued-research invitation; "
               "preserve the research frontier for later. Audit real feasibility and evidence."
               if role in {"compose", "audit", "schedule", "value_frontier", "goal_scout"} else ""))


class Engine:
    def __init__(self, workspace: Workspace, backend):
        self.ws, self.backend = workspace, backend

    def job(self, name, role, schema, inputs):
        # Every reviewed turn requires genuinely fresh scheduler/composer/audit
        # requests. Generation alone is unchanged for additive updates or a
        # side question, so it is insufficient as a job-cache namespace.
        cycle = self.ws.state.get('delivery_cycle', 0)
        tag = (f"g{self.ws.state['generation']}-{name}" if cycle == 0 else
               f"g{self.ws.state['generation']}-c{cycle}-{name}")
        return self.ws.get_job(tag, role, schema, inputs, instructions(role))

    def dispatch(self, jobs):
        # All immutable requests were created from a common snapshot before execution.
        # Each backend call gets fresh messages; no sibling output is ever prepended.
        self.ws.state["active_job_ids"] = [j["id"] for j in jobs]
        self.ws.save("jobs_dispatched", {"job_ids": self.ws.state["active_job_ids"]})
        count = min(len(jobs), self.ws.state["config"]["parallel_workers"])
        with ThreadPoolExecutor(max_workers=max(1, count)) as pool:
            results = list(pool.map(self.backend.execute, jobs))
        pending = [job["id"] for job, result in zip(jobs, results) if result is None]
        if pending:
            return {"status": "waiting_for_real_workers", "jobs": pending,
                    "instructions": "Execute each jobs/<id>/request.json in a separate permitted host worker, then submit its actual output. Do not author the blind results in this controller context."}
        for job in jobs:
            self.ws.result(job["id"])  # Schema and immutable input binding.
        return None

    def transition(self, phase, **updates):
        self.ws.state.update(phase=phase, **updates)
        self.ws.save("phase_changed", {"phase": phase})

    def resolve_auto_stage(self, proposed_scope: str, reason: str):
        """Independently examine a proposed shift from analysis to intervention.

        Do not let a downstream model infer that the user asked for action merely
        because some mechanism/point is already available. Review only the raw
        user task, not candidate reports. A generated quote must exist in it.
        """
        if self.ws.state['scope'] != 'auto':
            return proposed_scope, None
        cached = self.ws.state.get('scope_intent')
        if not cached:
            inputs = {**self.ws.raw_view(), 'proposed_scope': proposed_scope,
                      'scheduler_rationale': reason}
            cycle = self.ws.state.get('delivery_cycle', 0)
            job = self.job(f'scope-intent-c{cycle}', 'scope_intent', 'scope_intent', inputs)
            pending = self.dispatch([job])
            if pending:
                return None, pending
            outcome = self.ws.result(job['id'])['output']
            quote = outcome['user_request_quote'].strip()
            original = [x['text'] for x in self.ws.raw_view()['task_sources']]
            if quote and (not original or quote not in original[-1]):
                raise StateDyneError('Scope intent quotes a request not present in the latest user turn')
            if outcome['request_basis'] == 'explicit' and not quote:
                raise StateDyneError('Explicit intervention intent must cite actual user words')
            if not outcome['reason'].strip():
                raise StateDyneError('Scope arbiter requires a source-grounded explanation')
            self.ws.state['scope_intent'] = {'job_id': job['id'], **outcome}
            self.ws.mark_result(job['id'])
            self.ws.save('auto_stage_intent_independently_checked', {
                'proposed_scope': proposed_scope, 'requested_scope': outcome['requested_scope'],
                'basis': outcome['request_basis'], 'source_quote': quote})
            cached = self.ws.state['scope_intent']
        if cached['request_basis'] != 'explicit':
            return 'analysis', None
        return cached['requested_scope'], None

    def remaining_operations(self):
        """Return cognitive slots; None means *no predefined stopping count*.

        Actual operational failure protection (max_jobs/API/timeouts) stays
        separate. A request reaching those limits is blocked/provisional,
        never declared a completed cognitive investigation.
        """
        cap = self.ws.state["config"]["max_operations"]
        return float("inf") if cap is None else max(0, cap - self.ws.state["operations_done"])

    def advance(self):
        try:
            return self._advance_impl()
        except StateDyneError as exc:
            self.ws.state["last_error"] = str(exc)
            self.ws.save("execution_blocked_not_completed", {"error": str(exc), "jobs": self.ws.state.get("active_job_ids", [])})
            raise

    def _advance_impl(self):
        while True:
            s = self.ws.state
            phase = s["phase"]
            if phase == "route_turn":
                pending_turn=s.get('pending_turn')
                if not pending_turn:
                    raise StateDyneError('Cannot classify a turn without actual user text')
                inputs=self.ws.current_view()
                inputs['new_user_turn']=deepcopy(pending_turn)
                tag=f'turn-route-{pending_turn["route_index"]}'
                job=self.job(tag, 'turn_router', 'turn_route', inputs)
                pending=self.dispatch([job])
                if pending:
                    return pending
                self.ws.apply_turn_route(self.ws.result(job['id'])['output'], job['id'])
                continue
            elif phase == "discover":
                raw = self.ws.raw_view()
                # Ten independent jobs, with identical raw-source boundaries; no serial goal/selection delay.
                # Earlier versions ran the blind challenge after the others;
                # that unnecessary serialization produced no extra evidence.
                jobs = [self.job("frame", "frame", "frame", deepcopy(raw)),
                        self.job("system-map", "system_map", "system_map", deepcopy(raw)),
                        self.job("goal-scout", "goal_scout", "goal_review", deepcopy(raw)),
                        self.job("selection-scout", "selection_scout", "work", deepcopy(raw)),
                        self.job("relation-scout", "relation_scout", "work", deepcopy(raw)),
                        self.job("discovery", "discovery", "work", deepcopy(raw)),
                        self.job("reframe", "reframe", "work", deepcopy(raw)),
                        self.job("contrast-probe", "contrast_probe", "work", deepcopy(raw)),
                        self.job("environment-scout", "environment_scout", "work", deepcopy(raw)),
                        self.job("blind-challenge", "blind_challenge", "work", deepcopy(raw))]
                pending = self.dispatch(jobs)
                if pending:
                    return pending
                # Verify independent raw search produced differentiated work or
                # a specific null-search rationale before admitting the batch.
                # This is a limited textual guard, not a semantic truth test.
                check_raw_discovery_diversity(self.ws, jobs)
                record_focus(self.ws, jobs[0]["id"])
                register_system_map(self.ws, jobs[1]["id"])
                register_goal_review(self.ws, jobs[2]["id"])
                for job in jobs[3:]:
                    self.ws.merge_work(job["id"])
                self.transition("sweep", completed_operators=[],
                                blind_job=jobs[-1]["id"], blind_complete=True)
            elif phase == "expand_frontier":
                # An *explicit* user-requested second search. Reuse the
                # released evidence/model, but not the completed old answer
                # as proof. The existing portfolio then independently tests
                # the added mechanisms before a newly audited answer.
                cycle = s.get('delivery_cycle', 0)
                if not s.get('open_search_requested') or cycle < 1:
                    raise StateDyneError('Expansion requires an explicit completed-stage continuation')
                inputs = self.ws.current_view()
                inputs['expansion_focus'] = s.get('expansion_focus', '')
                raw=self.ws.raw_view()
                raw['expansion_focus']=s.get('expansion_focus','')
                jobs = [self.job(f'open-search-c{cycle}', 'open_search', 'work', deepcopy(inputs)),
                        self.job(f'breakthrough-expand-c{cycle}', 'breakthrough_scout', 'work', deepcopy(raw))]
                pending=self.dispatch(jobs)
                if pending:return pending
                baseline=list(self.ws.active_claims().values())
                validate_breakthrough(self.ws,jobs[1]['id'],baseline_claims=baseline)
                product = self.ws.result(jobs[0]['id'])['output']
                if not product['claims'] and not product['unknowns'] and not product['opportunities'] and len(product['no_increment_reason'].strip()) < 40:
                    raise StateDyneError('Expansion with no substantive new candidate must document the genuine null search')
                if product['claims'] and not (product['unknowns'] or product['opportunities']):
                    raise StateDyneError('New expansion hypotheses need discriminating information or a concrete next research opportunity')
                for job in jobs:self.ws.merge_work(job['id'])
                self.ws.state.setdefault('breakthrough_receipts',[]).append(jobs[1]['id'])
                self.ws.state.setdefault('expansion_runs', []).append({
                    'cycle': cycle, 'job_id': jobs[0]['id'], 'blind_job_id': jobs[1]['id'],
                    'candidate_count': sum(len(self.ws.result(j['id'])['output']['claims']) for j in jobs),
                    'unknown_count': sum(len(self.ws.result(j['id'])['output']['unknowns']) for j in jobs),
                    'no_increment_reason': product['no_increment_reason']})
                self.ws.save('explicit_expand_ran_parallel_incumbent_and_blind_search', {
                    'cycle':cycle,'job_ids':[j['id'] for j in jobs]})
                self.transition('probe_portfolio', portfolio_complete=False,
                                load_bearing_complete=False)
            elif phase == "delta_assess":
                # Additive evidence enters the existing reality model. A fresh
                # independent judgment selects local re-computation or a full
                # rebuild if the goal, scope, or premise changed fundamentally.
                new_ids = s.get('pending_delta_sources', [])
                if not new_ids:
                    raise StateDyneError('Delta assessment requires a real newly supplied source')
                inputs = self.ws.current_view()
                inputs['new_sources'] = [deepcopy(s['sources'][sid]) for sid in new_ids]
                job = self.job(f'delta-assess-c{s["delivery_cycle"]}', 'delta_assess', 'delta_assessment', inputs)
                pending = self.dispatch([job])
                if pending:
                    return pending
                assessment = self.ws.result(job['id'])['output']
                known = set(self.ws.active_claims())
                known_q = set(s['unknowns'])
                if not assessment['reason'].strip() or not assessment['newly_relevant_difference'].strip():
                    raise StateDyneError('Delta assessment requires a concrete change or grounded no-change finding')
                validate_question_resolution(self.ws, assessment)
                # This survives into compose and final review. A question that
                # yielded nothing is not silently promoted to a deep discovery.
                s['latest_question_resolution']=deepcopy(assessment['question_results'])
                self.ws.save('user_information_payoff_checked', {
                    'group_results': [(r['group_id'],r['outcome']) for r in assessment['question_results']]})
                if not set(assessment['affected_claim_ids']).issubset(known) or not set(assessment['affected_unknown_ids']).issubset(known_q):
                    raise StateDyneError('Delta assessment points to a nonexistent/stale relation')
                if s.get('task_thread',{}).get('last_route')=='replace_goal' and not (
                    assessment['goal_or_boundary_changed'] or assessment['impact']=='rebuild'):
                    raise StateDyneError('An explicitly replaced goal must receive a full independent system/goal rebuild')
                if assessment['goal_or_boundary_changed'] or assessment['impact']=='rebuild':
                    self.ws.mark_result(job['id'])
                    self.ws.rebuild_after_delta(job['id'])
                    continue
                self.ws.invalidate_delta_dependencies(assessment, job['id'])
                self.transition('delta_integrate')
            elif phase == 'delta_integrate':
                inputs = self.ws.current_view()
                inputs['new_sources'] = [deepcopy(s['sources'][sid]) for sid in s.get('pending_delta_sources', [])]
                cycle = s['delivery_cycle']
                jobs=[self.job(f'delta-integrate-c{cycle}', 'delta_integrate','work',deepcopy(inputs)),
                      self.job(f'delta-challenge-c{cycle}', 'delta_challenge','work',deepcopy(inputs))]
                # A major newly reported reality needs a new raw-only search,
                # independent of incumbent and reconciliation. A tangent does not.
                if s.get('interaction_mode') != 'side':
                    jobs.append(self.job(f'breakthrough-update-c{cycle}', 'breakthrough_scout',
                                         'work', self.ws.raw_view()))
                pending=self.dispatch(jobs)
                if pending:return pending
                if len(jobs)>2:
                    validate_breakthrough(self.ws,jobs[2]['id'],baseline_claims=list(self.ws.active_claims().values()))
                for job in jobs:self.ws.merge_work(job['id'])
                if len(jobs)>2:
                    s.setdefault('breakthrough_receipts',[]).append(jobs[2]['id'])
                    self.ws.save('new_user_evidence_received_blind_paradigm_reopen',{'job_id':jobs[2]['id']})
                self.transition('system_reconcile')
            elif phase == 'system_reconcile':
                inputs=self.ws.current_view()
                inputs['new_sources']=[deepcopy(s['sources'][sid]) for sid in s.get('pending_delta_sources', [])]
                cycle = s['delivery_cycle']
                # Both read the SAME verified new evidence, in parallel: one
                # reconciles the system, another rechecks objectives/values.
                jobs = [self.job(f'system-reconcile-c{cycle}', 'system_reconcile','system_map',deepcopy(inputs)),
                        self.job(f'goal-reconcile-c{cycle}', 'goal_scout', 'goal_review',deepcopy(inputs))]
                pending=self.dispatch(jobs)
                if pending:
                    return pending
                job = jobs[0]
                register_system_map(self.ws, job['id'])
                register_goal_review(self.ws, jobs[1]['id'])
                for sid in s.get('pending_delta_sources', []):
                    if sid not in s.setdefault('processed_delta_sources', []):
                        s['processed_delta_sources'].append(sid)
                self.ws.save('delta_evidence_integrated_and_system_model_reconciled', {'source_ids':s.get('pending_delta_sources', []),'job_id':job['id']})
                s['pending_delta_sources']=[]
                self.transition('probe_portfolio')
            elif phase == "intervention_frontier":
                # A requested change stage receives two orthogonal causal
                # searches on the exact same snapshot: from current process
                # forward, and from desired result backward. This is not a
                # mandatory list of points or a second copy of the same advice.
                frozen = self.ws.current_view()
                cycle = self.ws.state.get('delivery_cycle', 0)
                jobs = [self.job(f"change-forward-c{cycle}", "change_forward", "work", deepcopy(frozen)),
                        self.job(f"change-backward-c{cycle}", "change_backward", "work", deepcopy(frozen))]
                pending = self.dispatch(jobs)
                if pending:
                    return pending
                for j in jobs:
                    self.ws.merge_work(j["id"])
                # The two blind point searches do not know which candidates
                # the other discovered. A separate real review must compare
                # pairs/bundles and counter-positions before a point ranking.
                self.transition("change_portfolio")
            elif phase == "change_portfolio":
                cycle = s.get('delivery_cycle', 0)
                # Two genuinely independent workers see the same frozen point
                # pool. The action probe pre-evaluates controllability, costs,
                # acceptance and no-action alternatives before ranking, while
                # remaining BACKSTAGE until a later authorized actions turn.
                frozen = self.ws.current_view()
                jobs = [
                    self.job(f"change-portfolio-c{cycle}", "change_portfolio", "work", deepcopy(frozen)),
                    self.job(f"change-action-probe-c{cycle}", "change_action_probe", "work", deepcopy(frozen)),
                ]
                pending = self.dispatch(jobs)
                if pending:
                    return pending
                before = set(self.ws.active_claims())
                for job in jobs:
                    self.ws.merge_work(job["id"])
                new_claims = {cid: item for cid, item in self.ws.active_claims().items() if cid not in before}
                point_ids = sorted(cid for cid, item in self.ws.active_claims().items() if item['kind'] == 'point')
                action_ids = sorted(cid for cid, item in self.ws.active_claims().items()
                                    if item['kind'] == 'action')
                s['action_preflight'] = {
                    'point_claim_ids': point_ids,
                    'action_candidate_ids': action_ids,
                    'newly_preflighted_action_ids': sorted(cid for cid, item in new_claims.items()
                                                           if item['kind'] == 'action'),
                    'portfolio_job_id': jobs[0]['id'],
                    'action_probe_job_id': jobs[1]['id'],
                    'source_generation': s['generation'],
                    'delivery_cycle': cycle,
                    'released_actions': False,
                }
                self.ws.save('point_priority_and_action_feasibility_independently_compared',
                             {'portfolio_job': jobs[0]['id'], 'probe_job': jobs[1]['id'],
                              'preflight_action_ids': action_ids,
                              'visible_action_stage': s.get('delivery_scope')})
                self.transition("schedule", intervention_frontier_done=True)
            elif phase == "entry_review":
                # Unlike the final blind challenge, this check runs *before* first information selection.
                # The reviewer sees all initial products and raw contrasts, not an already drafted answer.
                inputs = self.ws.current_view()
                inputs["first_pass_job_ids"] = [j["job_id"] for j in s["work_results"]
                                                 if self.ws.job_request(j["job_id"])["tag"] in
                                                 {f"g{s['generation']}-discovery", f"g{s['generation']}-reframe",
                                                  f"g{s['generation']}-contrast-probe", f"g{s['generation']}-environment-scout",
                                                  f"g{s['generation']}-selection-scout",
                                                  f"g{s['generation']}-blind-challenge",
                                                  f"g{s['generation']}-frontier-scout",
                                                  f"g{s['generation']}-evidence-scout"}]
                inputs["previous_gate_reviews"] = deepcopy(s.get("entry_reviews", []))
                review_tag = f"entry-review-{s.get('entry_round',0)}" if not s.get('delivery_cycle',0) else f"entry-review-c{s['delivery_cycle']}-{s.get('entry_round',0)}"
                job = self.job(review_tag, "entry_review", "entry_review", inputs)
                pending = self.dispatch([job])
                if pending:
                    return pending
                decision = self.ws.result(job["id"])["output"]
                new_foci = check_boundary(self.ws, decision, job["id"])
                if s.get("entry_reviews"):
                    previous = s["entry_reviews"][-1]["output"]
                    repair_tag = (f"g{s['generation']}-entry-repair-{s['entry_repairs_done'] - 1}"
                                  if not s.get('delivery_cycle',0) else
                                  f"g{s['generation']}-entry-repair-c{s['delivery_cycle']}-{s['entry_repairs_done'] - 1}")
                    repairs = [r for r in s['jobs'].values() if r['tag'] == repair_tag and r['status'] == 'completed']
                    if len(repairs) != 1:
                        raise StateDyneError("Independent recheck is missing a completed repair artifact")
                    ensure_repair_changed_relation(self.ws, previous, decision, repairs[0]['id'])
                if (self.ws.state.get("foci") or new_foci) and not decision["examined_contrasts"]:
                    raise StateDyneError("Entry review must explain which anchored contrasts were examined")
                if decision["verdict"] == "reopen":
                    for field in ("missing_relation", "why_material", "required_new_prediction_or_test"):
                        if not decision[field].strip():
                            raise StateDyneError("Reopening the first pass requires a concrete gap, consequence and test")
                elif not decision["no_gap_reason"].strip():
                    raise StateDyneError("A passing first-pass boundary review requires a concrete comparison")
                if new_foci:
                    s["foci"].extend(new_foci)
                    self.ws.save("independent_review_discovered_omitted_raw_phenomena",
                                 {"review_job": job["id"], "foci": [f["id"] for f in new_foci]})
                s["entry_review"] = {"job_id": job["id"], "output": decision}
                s.setdefault("entry_reviews", []).append({"job_id": job["id"], "output": decision})
                self.ws.mark_result(job["id"])
                self.ws.save("source_anchored_first_pass_boundary_reviewed", {"verdict": decision["verdict"],
                            "round": s.get("entry_round", 0), "foci": [c["focus_id"] for c in decision["coverage"]]})
                # A newly proposed model-outside hypothesis is not allowed to
                # disappear between discovery and information selection. This
                # independent *program* gate inspects worker products, not
                # hidden reasoning; the reviewer verdict remains unmodified.
                bridge_gaps = unbridged_model_outside(self.ws)
                if bridge_gaps:
                    s["bridge_gaps"] = bridge_gaps
                    self.ws.save("novel_model_outside_candidate_lacks_information_bridge",
                                 {"claim_ids": [g["claim_id"] for g in bridge_gaps],
                                  "entry_review_job": job["id"],
                                  "model_review_verdict": decision["verdict"]})
                else:
                    s.pop("bridge_gaps", None)
                if decision["verdict"] == "reopen" or bridge_gaps:
                    if s["entry_repairs_done"] >= s["config"]["max_entry_repairs"]:
                        # Honest provisional delivery is more useful than an
                        # endless loop or claiming all mechanisms were found.
                        self.transition("schedule", entry_unresolved=True,
                                        entry_gap_stop_reason="first_pass_generation_or_candidate_information_bridge_still_unresolved")
                    else:
                        self.transition("entry_repair")
                else:
                    # First, challenge the value/goal/solution representation while
                    # alternatives can still compete in the search tournament.
                    # This is no longer an epilogue after scheduler closure.
                    if s.get('delivery_cycle', 0) == 0 and not s.get('value_frontier_done'):
                        self.transition('value_frontier', value_frontier_return_phase='schedule')
                    else:
                        self.transition('schedule')
            elif phase == "entry_repair":
                inputs = self.ws.current_view()
                inputs["gate_findings"] = deepcopy(s["entry_review"]["output"])
                inputs["bridge_gaps"] = deepcopy(s.get("bridge_gaps", []))
                inputs["operation"] = ("predict" if s.get("bridge_gaps") else
                                       s["entry_review"]["output"]["next_operator"])
                repair_tag = f"entry-repair-{s['entry_repairs_done']}" if not s.get('delivery_cycle',0) else f"entry-repair-c{s['delivery_cycle']}-{s['entry_repairs_done']}"
                job = self.job(repair_tag, "entry_repair", "work", inputs)
                pending = self.dispatch([job])
                if pending:
                    return pending
                self.ws.merge_work(job["id"])
                self.transition("entry_review", entry_round=s.get("entry_round", 0) + 1,
                                entry_repairs_done=s["entry_repairs_done"] + 1)
            elif phase == "sweep":
                # Two differentiated views *before* first boundary review: new
                # representations can actually change the review and first questions.
                # One challenges the representation; the other designs ways to
                # obtain independently discriminating evidence and hidden-context
                # counterexamples. They run on the same frozen pre-sweep snapshot.
                frozen = self.ws.current_view()
                raw = self.ws.raw_view()
                jobs = [self.job("frontier-scout", "frontier_scout", "work", deepcopy(frozen)),
                        self.job("evidence-scout", "evidence_scout", "work", deepcopy(frozen)),
                        self.job("breakthrough-raw", "breakthrough_scout", "work", deepcopy(raw))]
                pending = self.dispatch(jobs)
                if pending:
                    return pending
                # The breakthrough worker sees only the original raw problem, not
                # the incumbent claims or sibling results. Its proposals reach the
                # tournament BEFORE early closure/first user interview.
                baseline=list(self.ws.active_claims().values())
                validate_breakthrough(self.ws, jobs[2]['id'], baseline_claims=baseline)
                for j in jobs:
                    self.ws.merge_work(j["id"])
                self.ws.state.setdefault('breakthrough_receipts', []).append(jobs[2]['id'])
                self.ws.save('raw_blind_breakthrough_entered_initial_tournament', {'job_id':jobs[2]['id']})
                # The new independent portfolio reasons *over* the expanded
                # candidate pool, before any reviewer or final user questions.
                self.transition("probe_portfolio", sweep_complete=True)
            elif phase == "probe_portfolio":
                inputs = self.ws.current_view()
                if s.get('value_frontier_round',0):
                    tag=f'probe-portfolio-value-c{s.get("delivery_cycle",0)}-r{s["value_frontier_round"]}'
                else:
                    tag = 'probe-portfolio' if not s.get('delivery_cycle',0) else f'probe-portfolio-c{s["delivery_cycle"]}'
                job = self.job(tag, "probe_portfolio", "probe_portfolio", inputs)
                pending = self.dispatch([job])
                if pending:
                    return pending
                register_portfolio(self.ws, job["id"])
                # An independently verified challenge of pivotal premises now
                # runs BEFORE the first boundary review and the user questions.
                # A user-authorized expansion retains its *already completed*
                # raw first-pass boundary review. Replaying entry_review with
                # the old recheck ledger would misinterpret a new portfolio as
                # a repeated initial review and demand a nonexistent repair.
                # Instead newly added candidates go through fresh independent
                # load-bearing review, adaptive scheduling and final exact-draft
                # audit, without treating old hypotheses as newly proven.
                next_phase = ('schedule' if ((s.get('open_search_requested') and
                              s.get('delivery_cycle', 0) > 0) or s.pop('value_frontier_returning', False))
                              else 'entry_review')
                self.transition("load_bearing", portfolio_complete=True,
                                load_bearing_return=next_phase)
            elif phase == "load_bearing":
                inputs = self.ws.current_view()
                cycle=s.get('delivery_cycle',0)
                round_no=s.get('load_bearing_round',0)
                tag=f'load-bearing-c{cycle}-r{round_no}'
                job=self.job(tag,'load_bearing','load_bearing',inputs)
                pending=self.dispatch([job])
                if pending:
                    return pending
                register_load_bearing(self.ws,job['id'])
                target=s.pop('load_bearing_return','entry_review')
                # A new decisive, obtainable premise found by a *late* audit
                # cannot be ignored simply because composition was about to run.
                # Schedule another genuine investigation when the budget permits;
                # an unavailable route remains a visible conditional limit.
                pending_research=pending_self_research(self.ws)
                if (target=='compose' and pending_research
                        and self.remaining_operations() > 0):
                    target='schedule'
                    self.ws.save('late_premise_changed_next_cognitive_operation',
                                 {'unknown_ids':pending_research,'audit_job':job['id']})
                self.transition(target,load_bearing_complete=True,
                                load_bearing_round=round_no+1)
            elif phase == "schedule":
                if s.get('scope') in ('points', 'actions', 'plan') and not s.get('intervention_frontier_done'):
                    self.transition('intervention_frontier')
                    continue
                if not s.get("blind_complete") or not s.get("entry_review") or (s["entry_review"]["output"]["verdict"] != "pass" and not s.get("entry_unresolved")):
                    raise StateDyneError("Exploration must not start before anchored boundary gate and raw blind challenge")
                if s.get("delivery_cycle", 0) == 0 and (not s.get("sweep_complete") or not s.get("portfolio_complete")):
                    raise StateDyneError("Exploration must receive independent gap/evidence search and the registered probe portfolio")
                if self.remaining_operations() == 0:
                    self.transition("compose", stop_reason="exploration_budget_exhausted", budget_limited=True)
                    continue
                # Valuable discoveries have FIRST-CLASS scheduling rights.
                # Do not wait until an incumbent model declares itself done.
                # A model-gap search and unrelated evidence can be parallel,
                # but never put dependent investigations in the same batch.
                uncovered = pending_model_expansion(self.ws)
                coverage = pending_coverage_opportunities(self.ws)
                # All material, as-yet-unattempted relation opportunities may
                # enter active investigation, not just ones tagged by a probe
                # or by predefined system coverage. The immutable work batch
                # still respects actual host tool capacity.
                general = unattempted_open_relations(s)
                research = pending_self_research(self.ws)
                environment_questions = unattempted_environment_questions(s)
                # ALL independently opened material relationships compete
                # NOW, before the scheduler can lock in an incumbent model.
                # Environment/selection openings receive the existing real
                # environment operator; all others receive independent reframe.
                # Capacity determines only this batch size, never whether a
                # source of discovery is admissible to the queue.
                candidates = list(dict.fromkeys(uncovered + coverage + general))
                env_candidates = environment_relation_ids(s, candidates)
                model_candidates = [oid for oid in candidates if oid not in env_candidates]
                # 10.20: A material acquisition that changes the candidate
                # space must receive a *fresh* model/alternative search. An
                # evidence scout must not merely add a citation to the old
                # answer. This queue contains real completed acquire jobs,
                # never fabricated worker receipts or semantic truth claims.
                evidence_reframes = s.get('pending_evidence_reframes', [])
                if candidates or research or environment_questions or evidence_reframes:
                    # One frozen batch can address multiple independent system
                    # gaps and facts. The old one-item slices silently narrowed
                    # exploration and wasted independent worker capacity.
                    work = priority_batch(
                        model_opportunities=model_candidates,
                        environment_opportunities=env_candidates,
                        environment_unknowns=environment_questions,
                        research_unknowns=research,
                        evidence_reframes=evidence_reframes,
                        capacity=min(s['config']['max_parallel_operations'],
                                     self.remaining_operations()),
                        rotation=s.get('priority_rotation', 0),
                        opportunity_metadata=s.get('exploration_opportunities', {}),
                    )
                    # Start from another lane next time so low host concurrency
                    # cannot indefinitely delay environmental or evidence work.
                    s['priority_rotation'] = (s.get('priority_rotation', 0) + len(work)) % 6
                    self.ws.save('high_value_new_discovery_received_immediate_search_priority', {
                        'model_opportunities': model_candidates,
                        'environment_opportunities': env_candidates,
                        'environment_unknowns': environment_questions,
                        'evidence_unknowns': research,
                        'evidence_reframe_jobs': [batch['acquire_job'] for batch in evidence_reframes],
                        'selected_operations': [
                            {'operator': x['operator'], 'opportunities': x['opportunity_ids'],
                             'targets': x['target_ids']} for x in work
                        ],
                        'deferred_due_to_concurrency':
                            max(0, len(candidates) + len(environment_questions) + len(set(research)) + bool(evidence_reframes) - len(work)),
                    })
                    s['decisions'] = work
                    self.transition('operate')
                    continue
                inputs = self.ws.current_view()
                inputs["completed_operators"] = s.get("completed_operators", [])
                job = self.job(f"schedule-{s.get('schedule_round', 0)}", "schedule", "search_plan", inputs)
                pending = self.dispatch([job])
                if pending:
                    return pending
                decision = self.ws.result(job["id"])["output"]
                validate(decision, SCHEMAS["search_plan"])
                if s["scope"] != "auto" and decision["delivery_scope"] != s["scope"]:
                    raise StateDyneError("Scheduler cannot override the user's explicit output scope")
                if s['scope'] == 'auto':
                    accepted_scope, pending = self.resolve_auto_stage(decision['delivery_scope'], decision['scope_reason'])
                    if pending:
                        return pending
                    decision['delivery_scope'] = accepted_scope
                if not decision["scope_reason"].strip():
                    raise StateDyneError("Scheduler needs a concrete scope reason")
                if decision["finish"] and decision["decisions"]:
                    raise StateDyneError("Search plan cannot finish and dispatch work simultaneously")
                if not decision["finish"] and not decision["decisions"]:
                    raise StateDyneError("Search plan must choose useful work or explicitly finish")
                if len(decision["decisions"]) > min(s["config"]["max_parallel_operations"],
                                                    self.remaining_operations()):
                    raise StateDyneError("Requested concurrent operations exceed the configured execution safety budget")
                known = set(self.ws.active_claims()) | set(s["unknowns"])
                opportunities = s.get("exploration_opportunities", {})
                keys = set()
                for task in decision["decisions"]:
                    if not set(task["target_ids"]).issubset(known):
                        raise StateDyneError("Search plan targeted an unknown/stale claim or question")
                    if not set(task["opportunity_ids"]).issubset(opportunities):
                        raise StateDyneError("Search plan targeted an unknown exploration opportunity")
                    if any(opportunities[o]["state"] == "stale" for o in task["opportunity_ids"]):
                        raise StateDyneError("Cannot execute a superseded exploration opportunity")
                    if not all(task[k].strip() for k in ("rationale", "expected_difference", "strongest_alternative")):
                        raise StateDyneError("Search work requires a concrete expected difference and rival operation")
                    if len(decision["decisions"]) > 1 and not task["why_parallel_safe"].strip():
                        raise StateDyneError("Parallel work requires an explicit independent-input justification")
                    key = (task["operator"], tuple(task["target_ids"]), tuple(task["opportunity_ids"]))
                    if key in keys:
                        raise StateDyneError("Duplicate parallel work would repeat an unchanged search")
                    keys.add(key)
                if len(decision["decisions"]) > 1 and any(task["operator"] in ("change", "adoption") for task in decision["decisions"]):
                    raise StateDyneError("Dependent change/adoption work must not run in an unsequenced parallel batch")
                self.ws.mark_result(job["id"])
                s["schedule_round"] = s.get("schedule_round", 0) + 1
                s["delivery_scope"] = decision["delivery_scope"]
                s["adoption_relevant"] = decision["adoption_relevant"]
                # Auto scope may reveal the user really requested a point or
                # solution deliverable. Search points from BOTH directions
                # before composing it; keep the original scheduler receipt.
                if (decision["delivery_scope"] in ("points", "actions", "plan")
                        and not s.get('intervention_frontier_done')):
                    self.transition('intervention_frontier')
                    continue
                tasks = decision["decisions"]
                # Before accepting a 'finish', perform one real attempt to
                # obtain material/calculable high-value evidence opened by a
                # model-outside discovery. A question that changes *understanding*
                # is worth following up even if no immediate action flips.
                # This never turns public facts into an interview, and never
                # creates an infinite loop: each inquiry is investigated once.
                # An unmodelled high-value relation must trigger an actual
                # model-expansion operation, not merely a sentence in review.
                pending_models = list(dict.fromkeys(
                    pending_model_expansion(self.ws) + unattempted_open_relations(s)
                )) if decision["finish"] else []
                pending_evidence = pending_self_research(self.ws) if decision["finish"] else []
                if pending_models:
                    tasks = [{"operator": "reframe", "target_ids": [],
                              "opportunity_ids": pending_models,
                              "rationale": "An independent portfolio found a potentially valuable relation family missing from every admitted model.",
                              "expected_difference": "Construct a new competing generative relation and genuinely unreported distinguishing predictions.",
                              "strongest_alternative": "Document a specific null search, and preserve conditional existing models.",
                              "why_parallel_safe": ""}]
                    self.ws.save("independent_unmodelled_relation_forced_into_reframe",
                                 {"opportunity_ids": pending_models})
                elif pending_evidence:
                    tasks = [{"operator": "acquire", "target_ids": pending_evidence,
                              "opportunity_ids": [],
                              "rationale": "Obtain independently discoverable information before finalizing the current model.",
                              "expected_difference": "Evidence can validate or overturn a newly proposed relation/prediction.",
                              "strongest_alternative": "Keep a conditional judgment if the available evidence does not discriminate.",
                              "why_parallel_safe": ""}]
                    self.ws.save("discovery_frontier_self_research_precedes_finish", {"unknown_ids": pending_evidence})
                # Completion is a supported judgement, never a loophole for
                # omitting a user-requested point/action/plan stage.
                if decision["finish"] and s["delivery_scope"] != "analysis":
                    available_kinds = {c["kind"] for c in self.ws.active_claims().values()}
                    prior = self.ws.previously_delivered_interventions()
                    available_kinds.update(k for k, v in prior.items() if v)
                    needed = {"points": {"point"}, "actions": {"point", "action"},
                              "plan": {"point", "action", "plan"}}[s["delivery_scope"]]
                    if not needed.issubset(available_kinds) and "change" not in s.get("completed_operators", []):
                        tasks = [{"operator": "change", "target_ids": [], "opportunity_ids": [],
                                  "rationale": "Explicit requested intervention stages have not been produced.",
                                  "expected_difference": "Produce independent intervention points then mapped actions and a plan as requested.",
                                  "strongest_alternative": "Provisional delivery if no safe or evidentially grounded intervention exists.",
                                  "why_parallel_safe": ""}]
                    elif decision["adoption_relevant"] and "adoption" not in s.get("completed_operators", []):
                        tasks = [{"operator": "adoption", "target_ids": [], "opportunity_ids": [],
                                  "rationale": "Changing the user's behaviour requires credible adoption conditions.",
                                  "expected_difference": "Clarify value protected, credible entry and feedback without inventing motives.",
                                  "strongest_alternative": "Deliver a conditional action with its adoption limitation.",
                                  "why_parallel_safe": ""}]
                s["decisions"] = tasks
                if not tasks:
                    if (not s.get('value_frontier_done',False)
                            and (s.get('interaction_mode') != 'side'
                                 or s.get('task_thread',{}).get('force_independent_continuation'))
                            and s.get('goal_review')):
                        self.transition('value_frontier',
                            saved_finish_reason=decision['finish_reason'] or 'search_has_no_other_independent_value')
                    else:
                        self.transition("compose", stop_reason=decision["finish_reason"] or "scheduler_found_no_higher_value_immediate_operation")
                else:
                    self.transition("operate")
            elif phase == "operate":
                # Each sibling receives an identical pre-operation snapshot.
                # Read/merge only after *all* model calls finish; one worker's
                # hypothesis cannot contaminate another's independent search.
                snapshot = self.ws.current_view()
                jobs = []
                cycle = s.get("delivery_cycle", 0)
                for i, task in enumerate(s["decisions"]):
                    inputs = deepcopy(snapshot)
                    inputs.update(operation=task["operator"], targets=task["target_ids"],
                                  opportunity_ids=task["opportunity_ids"],
                                  requested_difference=task["expected_difference"])
                    tag = f"operation-{s['operations_done'] + i}" if not cycle else f"operation-c{cycle}-{s['operations_done'] + i}"
                    role = "reframe_informed" if task["operator"] == "reframe" else task["operator"]
                    jobs.append(self.job(tag, role, "work", inputs))
                pending = self.dispatch(jobs)
                if pending:
                    return pending
                for task, job in zip(s["decisions"], jobs):
                    # Track *real* newly admitted information from the acquire
                    # worker, not a claim of having researched the web.
                    claims_before = set(self.ws.active_claims())
                    unknowns_before = set(self.ws.state['unknowns'])
                    self.ws.merge_work(job["id"])
                    if task["operator"] == "reframe" and task.get('evidence_trigger_ids'):
                        acknowledged = set(task['evidence_trigger_ids'])
                        self.ws.state['pending_evidence_reframes'] = [record for record in
                            self.ws.state.get('pending_evidence_reframes', [])
                            if record['acquire_job'] not in acknowledged]
                        self.ws.save('new_evidence_independent_model_revisit_completed',
                                     {'reframe_job': job['id'], 'acquisition_jobs': sorted(acknowledged)})
                    if task["operator"] == "acquire":
                        added_claims = [cid for cid, claim in self.ws.active_claims().items()
                                        if cid not in claims_before and claim['kind'] in
                                        ('mechanism', 'inference', 'prediction')]
                        added_unknowns = [qid for qid, q in self.ws.state['unknowns'].items()
                                          if qid not in unknowns_before and
                                          q.get('priority') in ('blocking', 'important')]
                        if added_claims or added_unknowns:
                            self.ws.state.setdefault('pending_evidence_reframes', []).append({
                                'acquire_job': job['id'], 'claim_ids': added_claims,
                                'unknown_ids': added_unknowns})
                            self.ws.save('new_evidence_reopened_model_outside_search', {
                                'job_id': job['id'], 'claim_ids': added_claims,
                                'unknown_ids': added_unknowns})
                        # Attempted is not the same as resolved; unresolved
                        # evidence is retained for a conditional answer.
                        known_unknowns = set(self.ws.state["unknowns"])
                        attempted = [qid for qid in task["target_ids"] if qid in known_unknowns]
                        ledger = self.ws.state.setdefault("investigated_unknowns", [])
                        for qid in attempted:
                            if qid not in ledger:
                                ledger.append(qid)
                        if attempted:
                            self.ws.save("model_outside_information_research_attempted", {"unknown_ids": attempted,
                                                                                "worker_job_id": job["id"]})
                    if task['operator'] == 'environment' and task['target_ids']:
                        examined = s.setdefault('environment_questions_attempted', [])
                        for qid in task['target_ids']:
                            if qid not in examined:
                                examined.append(qid)
                        self.ws.save('environment_question_examined_without_claiming_evidence_acquired',
                            {'question_ids':task['target_ids'],'worker_job_id':job['id']})
                    self.ws.mark_opportunities_attempted(task, job_id=job['id'])
                completed = s.get("completed_operators", []) + [task["operator"] for task in s["decisions"]]
                self.transition("schedule", operations_done=s["operations_done"] + len(jobs), completed_operators=completed)
            elif phase == 'value_frontier':
                # A plausible answer is not proof that the highest-value
                # *problem representation* or pathway has been found. Challenge
                # the current best alternative once, independently, before
                # releasing a primary decision. No forced novelty.
                inputs=self.ws.current_view()
                tag=f'value-frontier-c{s.get("delivery_cycle",0)}'
                job=self.job(tag, 'value_frontier', 'work', inputs)
                pending=self.dispatch([job])
                if pending:
                    return pending
                product=self.ws.result(job['id'])['output']
                if not product['claims'] and len(product['no_increment_reason'].strip())<35:
                    raise StateDyneError('A null high-value search needs a meaningful attempted alternative and reason')
                if product['claims']:
                    prior={(c['statement'].strip().casefold(),tuple(c['distinct_consequences']))
                        for c in self.ws.active_claims().values()}
                    if any((c['statement'].strip().casefold(),tuple(c['distinct_consequences'])) in prior
                           for c in product['claims']):
                        raise StateDyneError('A restated candidate with identical predictions is not an independent new discovery')
                if product['claims'] or product['unknowns'] or product['opportunities']:
                    self.ws.merge_work(job['id'])
                    s['value_frontier_returning']=True
                else:
                    # An evidence-free null search is a real worker receipt, not
                    # a new cognitive finding; no extra review or scheduling.
                    self.ws.mark_result(job['id'])
                s['value_frontier_done']=True
                s.setdefault('task_thread',{})['force_independent_continuation']=False
                self.ws.save('independent_alternative_value_path_search_completed',
                    {'job_id':job['id'],'novel_candidate_count':len(product['claims']),
                     'no_forced_novelty':not bool(product['claims'])})
                if product['claims'] or product['unknowns'] or product['opportunities']:
                    # New relation may reverse the current plan. Use fresh IDs
                    # for genuine reconsideration; NEVER replay the old probe,
                    # load-bearing, or exact-draft review receipt.
                    s.pop('value_frontier_return_phase', None)
                    s['value_frontier_round']=s.get('value_frontier_round',0)+1
                    self.transition('probe_portfolio',portfolio_complete=False,
                                    load_bearing_round=s.get('load_bearing_round',0)+1,
                                    intervention_frontier_done=False if s.get('delivery_scope') in ('points','actions','plan') else s.get('intervention_frontier_done',False),
                                    load_bearing_complete=False,load_bearing_audit=None)
                else:
                    earlier = s.pop('value_frontier_return_phase', None)
                    if earlier == 'schedule':
                        self.transition('schedule')
                    else:
                        self.transition('compose', stop_reason=s.pop('saved_finish_reason','independent_value_search_found_no_material_increment'))
            elif phase == "decision_tournament":
                # The value of ten independent voices is the strongest viable
                # DIFFERENCE they find, not the number of roles or a consensus
                # summary. Give a separate worker the frozen candidate pool,
                # underlying goal, actual evidence and independent premise audit.
                cycle = s.get('delivery_cycle', 0)
                inputs = self.ws.current_view()
                inputs['load_bearing_audit'] = deepcopy(s.get('load_bearing_audit'))
                job = self.job(f'decision-tournament-c{cycle}-{tournament_signature(self.ws)[:14]}', 'decision_tournament',
                               'decision_tournament', inputs)
                pending = self.dispatch([job])
                if pending:
                    return pending
                research_reopened = register_tournament(self.ws, job['id'])
                if research_reopened and self.remaining_operations() > 0:
                    # The independent judge found a NEW observable route that
                    # might reverse the answer: investigate before composing.
                    self.transition('schedule')
                else:
                    self.transition('compose')
            elif phase == "compose":
                # Changes introduced by adaptive search or intervention point
                # generation must be challenged too. Reusing an old pass is
                # allowed only for the exact same claims/evidence/goal/scope.
                load=s.get('load_bearing_audit')
                if not load or load.get('signature')!=snapshot_signature(self.ws):
                    self.transition('load_bearing',load_bearing_return='compose')
                    continue
                # Independent outcome competition is a real mandatory pass,
                # not a sentence that the composer may self-certify.
                tournament = s.get('decision_tournament')
                if (not tournament or tournament['signature'] != tournament_signature(self.ws)):
                    self.transition('decision_tournament')
                    continue
                inputs = self.ws.current_view()
                inputs["delivery_scope"] = s.get("delivery_scope", s["scope"])
                inputs["previous_issues"] = s.get("repair_issues", [])
                cycle = s.get("delivery_cycle", 0)
                tag = f"compose-{s['repairs_done']}" if not cycle else f"compose-c{cycle}-{s['repairs_done']}"
                job = self.job(tag, "compose", "draft", inputs)
                pending = self.dispatch([job])
                if pending:
                    return pending
                self.ws.set_draft(job["id"])
                self.transition("review")
            elif phase == "review":
                inputs = self.ws.current_view()
                inputs["delivery_scope"] = s.get("delivery_scope") or ("analysis" if s["scope"] == "auto" else s["scope"])
                inputs.update(draft=s["draft"]["output"], draft_sha256=s["draft"]["sha256"],
                              blind_prior=self.ws.result(s["blind_job"])["output"],
                              previous_issues=s.get("repair_issues", []))
                cycle = s.get("delivery_cycle", 0)
                tag = f"review-{s['repairs_done']}" if not cycle else f"review-c{cycle}-{s['repairs_done']}"
                job = self.job(tag, "audit", "audit", inputs)
                pending = self.dispatch([job])
                if pending:
                    return pending
                self.ws.set_audit(job["id"])
                if s["audit"]["output"]["verdict"] == "pass":
                    self.transition("release")
                elif s["repairs_done"] >= s["config"]["max_repairs"]:
                    self.transition("blocked", stop_reason="repair_budget_exhausted_with_open_review_issues")
                else:
                    self.transition("repair", repair_issues=deepcopy(s["audit"]["output"]["issues"]))
            elif phase == "repair":
                inputs = self.ws.current_view()
                inputs.update(operation="repair", issues=s["repair_issues"],
                              targets=[x for i in s["repair_issues"] for x in i["target_ids"]])
                cycle = s.get("delivery_cycle", 0)
                tag = f"repair-{s['repairs_done']}" if not cycle else f"repair-c{cycle}-{s['repairs_done']}"
                job = self.job(tag, "repair", "work", inputs)
                pending = self.dispatch([job])
                if pending:
                    return pending
                self.ws.merge_work(job["id"])
                self.transition("compose", repairs_done=s["repairs_done"] + 1)
            elif phase == "release":
                return self.publish()
            elif phase == "done":
                return self.verify_release()
            elif phase == "blocked":
                return {"status": "blocked", "reason": s["stop_reason"],
                        "draft": "draft-only.md" if (self.ws.root / "draft-only.md").exists() else None,
                        "published_answer": None,
                        "limit": "An unapproved draft is retained for diagnosis; it is not an audited delivery."}
            else:
                raise StateDyneError(f"Unknown engine phase: {phase}")

    def _check_release(self):
        s = self.ws.state
        draft, audit = s.get("draft"), s.get("audit")
        if not draft or not audit or audit["output"]["verdict"] != "pass":
            raise StateDyneError("No passing review of this draft exists")
        if (draft["sha256"] != audit["draft_sha256"] or text_digest(draft["output"]["answer"]) != draft["sha256"]
                or digest(draft['output']) != draft.get('payload_sha256')
                or audit.get('draft_payload_sha256') != draft.get('payload_sha256')):
            raise StateDyneError("Draft identity or review of structural quantities differs from reviewed bytes")
        if draft["cognition_hash"] != self.ws.cognition_hash() or audit["cognition_hash"] != self.ws.cognition_hash():
            raise StateDyneError("A premise changed after review; regenerate and re-review")
        generation = s["generation"]
        items = [j for j in s["jobs"].values() if self.ws.job_request(j["id"])["generation"] == generation]
        blind_tags = {f"g{generation}-{tag}" for tag in ("discovery", "reframe", "contrast-probe", "environment-scout", "selection-scout", "relation-scout", "blind-challenge")}
        blind_jobs = [j for j in items if j["tag"] in blind_tags and j["status"] == "completed"]
        if len(blind_jobs) != 7:
            raise StateDyneError("Required independently generated products are missing")
        entry = s.get("entry_review")
        if not entry or self.ws.result(entry["job_id"]) is None:
            raise StateDyneError("First-pass generation boundary was never examined")
        if entry["output"]["verdict"] != "pass":
            if not s.get("entry_unresolved") or draft["output"]["status"] == "complete":
                raise StateDyneError("Unresolved generation must not be released as a completed answer")
        check_boundary(self.ws, entry["output"], entry["job_id"])
        if unbridged_model_outside(self.ws) and not s.get("entry_unresolved"):
            raise StateDyneError("Unlinked independent prediction was not carried into the information cycle")
        if len(s.get("entry_reviews", [])) != s["entry_repairs_done"] + 1:
            raise StateDyneError("All first-pass rechecks must be retained in the event record")
        receipts=s.get('breakthrough_receipts',[])
        if not receipts or not any(self.ws.result(jid) and self.ws.result(jid)['independent_context']
                                   and self.ws.job_request(jid)['generation']==generation for jid in receipts):
            raise StateDyneError('A completed initial or refreshed source-blind breakthrough search receipt is required')
        for round_no in range(s["entry_repairs_done"]):
            tag = (f"g{generation}-entry-repair-{round_no}" if not s.get('delivery_cycle',0)
                   else f"g{generation}-entry-repair-c{s['delivery_cycle']}-{round_no}")
            if not any(j["tag"] == tag and j["status"] == "completed" for j in items):
                raise StateDyneError("A reopened first-pass gap was not repaired before release")
        load=s.get('load_bearing_audit')
        if not load or not self.ws.result(load['job_id']):
            raise StateDyneError('Independent load-bearing evidence/assumption audit is missing')
        if load.get('signature')!=snapshot_signature(self.ws):
            raise StateDyneError('New evidence or model claims appeared after the last independent premise audit')
        if not self.ws.result(load['job_id'])['independent_context']:
            raise StateDyneError('Load-bearing audit must be a real independent execution')
        if s.get('skill_version') == '11.3.0':
            jury = s.get('decision_tournament')
            if not jury or jury.get('signature') != tournament_signature(self.ws):
                raise StateDyneError('A current real cross-worker outcome competition is required before release')
            juror = self.ws.result(jury['job_id'])
            if (not juror or not juror['independent_context'] or
                    self.ws.job_request(jury['job_id'])['role'] != 'decision_tournament'):
                raise StateDyneError('The outcome competition must have an actual independent worker receipt')
            if juror['worker_ref'] in {self.ws.result(load['job_id'])['worker_ref'],
                                       self.ws.result(audit['job_id'])['worker_ref'],
                                       self.ws.result(draft['job_id'])['worker_ref']}:
                raise StateDyneError('The juror cannot be the composer, final reviewer or premise auditor')
        portfolio = s.get("probe_portfolio")
        if not portfolio or not self.ws.result(portfolio["job_id"]):
            raise StateDyneError("A registered independent information-probe portfolio is required before release")
        if not self.ws.result(portfolio["job_id"])["independent_context"]:
            raise StateDyneError("Portfolio cannot be fabricated in the main controller context")
        system_map=s.get('system_map')
        if not system_map or not self.ws.result(system_map['job_id']):
            raise StateDyneError('The system goal/boundary/upstream/downstream/environment map was not actually executed')
        if not system_map['goal_text'] or not system_map['working_boundary']:
            raise StateDyneError('System coverage must be tied to an actual goal and bounded scope')
        focus_jid = s.get("focus_job")
        if not focus_jid or self.ws.result(focus_jid) is None:
            raise StateDyneError("Missing independent raw phenomena ledger")
        # A verified stage continuation may change presentation scope but not
        # the original evidence snapshot given to the blind workers.
        original_raw = self.ws.job_request(focus_jid)["inputs"]
        current_raw = self.ws.raw_view()
        if any(original_raw[k] != current_raw[k] for k in ("task_sources", "material_index")):
            # Additive evidence is permitted only if explicitly assessed,
            # reconciled and recorded. No source existing in the initial blind
            # snapshot may have changed or vanished.
            previous={src['id']:src for src in original_raw['task_sources']+original_raw['material_index']}
            present={src['id']:src for src in current_raw['task_sources']+current_raw['material_index']}
            added=set(present)-set(previous)
            if (not added or not set(previous).issubset(present) or
                any(present[sid]!=source for sid,source in previous.items()) or
                not added.issubset(set(s.get('processed_delta_sources',[])))):
                raise StateDyneError("Raw blind snapshot changed without a complete, recorded delta analysis")
        refs = [self.ws.result(focus_jid)["worker_ref"],
                self.ws.result(portfolio["job_id"])["worker_ref"],
                self.ws.result(load["job_id"])["worker_ref"]]
        goal_jobs=[j for j in items if j['tag']==f'g{generation}-goal-scout' and j['status']=='completed']
        if len(goal_jobs)!=1 or not self.ws.state.get('goal_review') or not self.ws.result(goal_jobs[0]['id'])['independent_context']:
            raise StateDyneError('Independent objective discovery and goal/protected-value review is missing')
        initial_map_jobs=[j for j in items if j['tag']==f'g{generation}-system-map' and j['status']=='completed']
        if len(initial_map_jobs)!=1 or not self.ws.result(initial_map_jobs[0]['id'])['independent_context']:
            raise StateDyneError('Initial independent system coverage was not genuinely executed')
        refs.append(self.ws.result(initial_map_jobs[0]['id'])['worker_ref'])
        kinds = set()
        for j in blind_jobs:
            req = self.ws.job_request(j["id"])
            if set(req["inputs"]) != {"task_sources", "material_index", "output_scope"}:
                raise StateDyneError("A blind worker was given model-derived context")
            result = self.ws.result(j["id"])
            if not result or not result["independent_context"]:
                raise StateDyneError("No independent-context execution receipt; do not claim independent review")
            refs.append(result["worker_ref"])
            kinds.add(result["backend_kind"])
        if s.get('processed_delta_sources'):
            reconciles=[job for job in items if self.ws.job_request(job['id'])['role']=='system_reconcile' and job['status']=='completed']
            if not reconciles:
                raise StateDyneError('Additive feedback was not reconciled into the system map')
        if len(refs) != len(set(refs)):
            raise StateDyneError("Blind worker references are reused")
        if not self.ws.result(focus_jid)["independent_context"]:
            raise StateDyneError("The raw phenomena ledger did not use an independent worker")
        for reviewed in s.get("entry_reviews", []):
            entry_result = self.ws.result(reviewed["job_id"])
            if not entry_result["independent_context"] or entry_result["worker_ref"] in refs:
                raise StateDyneError("Each boundary review must be a fresh independent worker, not a reused initial worker")
            refs.append(entry_result["worker_ref"])
        writer = self.ws.result(draft["job_id"])
        reviewer = self.ws.result(audit["job_id"])
        if writer["worker_ref"] == reviewer["worker_ref"] or not reviewer["independent_context"]:
            raise StateDyneError("Exact-draft reviewer must be a separate fresh execution")
        kinds.update((writer["backend_kind"], reviewer["backend_kind"]))
        # Every accepted stage contributes provenance, not only discovery/review.
        for record in s["jobs"].values():
            if record["status"] == "completed" and self.ws.job_request(record["id"])["generation"] == s["generation"]:
                kinds.add(self.ws.result(record["id"])["backend_kind"])
        if "fixture" in kinds or s["backend"] == "fixture":
            return "simulation_only"
        if kinds == {"openai_live"}:
            return "api_execution_logged_semantics_model_reviewed"
        if kinds == {"native_attested"}:
            return "host_attested_isolation_not_independently_verified"
        raise StateDyneError("Execution provenance is mixed or unknown")

    def publish(self):
        assurance = self._check_release()
        draft = self.ws.state["draft"]
        name = "simulation-answer.md" if assurance == "simulation_only" else "answer.md"
        preface = ""
        if assurance == "simulation_only":
            preface = "> SIMULATION ONLY — scripted test output, not a model capability evaluation.\n\n"
        elif self.ws.state.get("entry_unresolved"):
            preface = "> 首轮发现门仍有未接通的重要生成关系；以下为条件性、经模型审核的阶段性结果，不代表已找出真正起因。\n\n"
        elif self.ws.state["budget_limited"]:
            preface = "> 本次执行达到探索预算上限。以下是经过模型审阅的阶段性结果，不代表解释空间已穷尽。\n\n"
        text = preface + draft["output"]["answer"] + "\n"
        atomic_write(self.ws.root / name, text)
        nav = deepcopy(draft['output']['navigation'])
        record = {"status": draft["output"]["status"], "answer_file": name,
                  "navigation": nav,
                  "answer_file_sha256": text_digest(text), "draft_sha256": draft["sha256"],
                  "draft_payload_sha256": draft["payload_sha256"],
                  "cognition_hash": self.ws.cognition_hash(), "assurance": assurance,
                  "audit_job": self.ws.state["audit"]["job_id"], "stop_reason": self.ws.state["stop_reason"],
                  "semantic_truth_guaranteed": False, "capability_evaluation_passed": False,
                  "first_pass_gap_unresolved": bool(self.ws.state.get("entry_unresolved", False))}
        save_json(self.ws.root / "release.json", record)
        if self.ws.state.get('interaction_mode') != 'side' or not self.ws.state.get('task_navigation', {}).get('last_primary_scope'):
            self.ws.state['task_navigation']['last_primary_scope'] = nav['primary_stage']
        self.ws.state['task_navigation']['last_next_scope'] = nav['next_stage']
        self.ws.state['task_navigation']['last_answer_anchor'] = nav['visible_anchor']
        self.ws.state['task_navigation']['last_release_cycle'] = self.ws.state.get('delivery_cycle', 0)
        self.ws.state.setdefault('task_thread',{})['research_frontier'] = self.ws.research_frontier()
        if self.ws.state.get('interaction_mode') != 'side':
            thread=self.ws.state.setdefault('task_thread',{})
            thread['last_verified_primary_stage']=nav['primary_stage']
            thread['last_next_stage']=nav['next_stage']
            thread['latest_valuable_search']=nav['expansion_offer']
            if (self.ws.state.get('goal_review') or {}).get('current_target'):
                thread['latest_unfinished_goal']=self.ws.state['goal_review']['current_target']
        self.transition("done")
        return record

    def verify_release(self):
        self.ws.verify_events()
        assurance = self._check_release()
        record = read_json(self.ws.root / "release.json")
        if (record["assurance"] != assurance or record["cognition_hash"] != self.ws.cognition_hash()
                or record.get('draft_payload_sha256') != self.ws.state['draft'].get('payload_sha256')):
            raise StateDyneError("Release binding mismatch")
        if record.get('navigation') != self.ws.state['draft']['output']['navigation'] or record['navigation']['visible_anchor'] != self.ws.state.get('task_navigation', {}).get('last_answer_anchor'):
            raise StateDyneError('Published navigation no longer matches the audited draft and workflow')
        if record["answer_file"] not in ("answer.md", "simulation-answer.md"):
            raise StateDyneError("Invalid published answer path")
        text = (self.ws.root / record["answer_file"]).read_text(encoding="utf-8")
        if text_digest(text) != record["answer_file_sha256"]:
            raise StateDyneError("Published answer was changed after review")
        return record
