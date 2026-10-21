"""Versioned candidate workspace. Every independent contribution is retained.

The store validates declared references, not the truth or completeness of a model.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import re
from typing import Any
from .common import StateDyneError, atomic_write, canonical, digest, read_json, save_json, text_digest, utc_now
from .schemas import SCHEMAS, validate
from .inquiry_frontier import discovery_inquiries, validate_inquiry_dispositions, VALUE_EFFECTS, ACTION_EFFECTS
from .research_agenda import agenda, meaningful_frontier

# max_operations=None removes a preassigned cognitive exploration quota. The
# other capacities are transport/concurrency/failure safeguards, NEVER a
# certificate that open questions were investigated. Users can increase them.
DEFAULTS = {"max_jobs": 2048, "max_api_requests": 4096, "max_operations": None,
            "max_repairs": 8, "max_entry_repairs": 8, "max_output_tokens": 16000, "max_tool_rounds": 16,
            "max_input_characters": 400000, "timeout_seconds": 300,
            "max_retries": 3, "parallel_workers": 12, "max_parallel_operations": 12,
            "reasoning_effort": None,
            "max_question_characters": None, "web_search_enabled": False}


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = self.root / "state.json"
        self.state = read_json(self.path)
        if self.state.get("schema_version") != 2:
            raise StateDyneError("Unsupported workspace schema")
        if self.state.get("skill_version") not in {"11.0.0", "11.1.0", "11.2.0", "11.2.1", "11.3.0"}:
            raise StateDyneError("Incompatible previous StateDyne workspace; start a fresh run from the authorized task and materials. No automatic mutation of earlier runs")

    @classmethod
    def create(cls, root: Path, task: str, *, scope="auto", backend="native", model="host-selected",
               config=None, materials=None):
        root = root.resolve()
        if root.exists() and any(root.iterdir()):
            raise StateDyneError("Choose a new empty work directory; existing data is never overwritten")
        if not task.strip():
            raise StateDyneError("The task cannot be empty")
        if scope not in ("auto", "analysis", "points", "actions", "plan"):
            raise StateDyneError("Unsupported output scope")
        if backend not in ("native", "openai", "fixture"):
            raise StateDyneError("Unsupported backend")
        root.mkdir(parents=True, exist_ok=True)
        cfg = dict(DEFAULTS)
        cfg.update(config or {})
        for key in ("max_jobs", "max_api_requests", "max_output_tokens", "max_input_characters",
                    "timeout_seconds", "parallel_workers", "max_parallel_operations"):
            if type(cfg[key]) is not int or cfg[key] < 1:
                raise StateDyneError(f"{key} must be a positive integer")
        if cfg["max_question_characters"] is not None and (
            type(cfg["max_question_characters"]) is not int or cfg["max_question_characters"] < 1
        ):
            raise StateDyneError("max_question_characters must be None (unlimited) or a positive integer")
        if cfg["max_operations"] is not None and (
            type(cfg["max_operations"]) is not int or cfg["max_operations"] < 0
        ):
            raise StateDyneError("max_operations must be None (no cognitive quota) or nonnegative")
        for key in ("max_repairs", "max_entry_repairs", "max_tool_rounds", "max_retries"):
            if type(cfg[key]) is not int or cfg[key] < 0:
                raise StateDyneError(f"{key} must be a nonnegative integer")
        state = {"schema_version": 2, "skill_version": "11.3.0", "revision": 0,
                 "generation": 1, "phase": "discover", "delivery_cycle": 0, "backend": backend, "model": model,
                 "scope": scope, "config": cfg, "created_at": utc_now(), "sources": {},
                 "claims": {}, "unknowns": {}, "work_results": [], "jobs": {},
                 "operations_done": 0, "repairs_done": 0, "entry_repairs_done": 0, "entry_round": 0, "schedule_round": 0, "stop_reason": "",
                 "budget_limited": False, "draft": None, "audit": None,
                 "turn_history": [], "events": [], "latest_question_resolution": [], "exploration_opportunities": {}, "foci": [], "entry_reviews": [], "entry_unresolved": False, "web_research_leads": {}, "sweep_complete": False, "portfolio_complete": False, "probe_portfolio": None, "intervention_frontier_done": False, "action_preflight": None, "investigated_unknowns": [], "environment_questions_attempted": [], "pending_evidence_reframes": [],
                 "system_map":None,"system_map_history":[],"goal_review":None,"goal_review_history":[], "load_bearing_audit":None,"load_bearing_history":[],"load_bearing_round":0,"load_bearing_complete":False, "pending_delta_sources":[],"processed_delta_sources":[], "expansion_runs":[], "portfolio_history":[], "open_search_requested":False, "expansion_focus":"", "expansion_target_scope":None, "expansion_base_point_ids": [],
                 "interaction_mode": "primary",
                 "task_navigation": {"last_primary_scope": None, "last_next_scope": None, "last_answer_anchor": "", "last_release_cycle": None},
                 "task_thread": {"status": "active", "root_source_id": "S1", "turn_routes": [],
                                 "user_input_policy": "open", "latest_unfinished_goal": task,
                                 "last_verified_primary_stage": None, "latest_valuable_search": "",
                                 "research_frontier": [], "force_independent_continuation": False},
                 "pending_turn": None, "current_turn_source_id": "S1", "value_frontier_done": False,
                 "breakthrough_receipts": [], "decision_tournament": None}
        save_json(root / "state.json", state)
        ws = cls(root)
        ws.add_source("User task", task, kind="user_reported", precision="as_reported", is_task=True)
        for label, text in (materials or []):
            ws.add_source(label, text, kind="provided_material", precision="as_provided")
        ws.save("created", {"backend": backend, "model": model})
        return ws

    def save(self, event: str, detail: Any = None):
        self.state["revision"] += 1
        previous = self.state["events"][-1]["event_hash"] if self.state["events"] else ""
        entry = {"revision": self.state["revision"], "time": utc_now(), "event": event,
                 "detail": detail, "previous_hash": previous}
        entry["event_hash"] = digest(entry)
        self.state["events"].append(entry)
        save_json(self.path, self.state)

    def add_source(self, label: str, text: str, *, kind: str, precision: str, is_task=False,
                   source_url: str | None = None):
        if not isinstance(text, str) or not text.strip():
            raise StateDyneError("Empty source")
        if len(text.encode("utf-8")) > 2_000_000:
            raise StateDyneError("Source exceeds 2 MB; explicitly select an appropriate excerpt")
        sid = f"S{len(self.state['sources']) + 1}"
        self.state["sources"][sid] = {"id": sid, "label": label, "text": text,
            "sha256": text_digest(text), "kind": kind, "precision": precision,
            "active": True, "is_task": is_task, "source_url": source_url}
        return sid

    def raw_view(self):
        sources = self.state["sources"]
        return {"task_sources": [deepcopy(s) for s in sources.values() if s["is_task"] and s["active"]],
                "material_index": [{k: v for k, v in s.items() if k != "text"}
                                   for s in sources.values() if not s["is_task"] and s["active"]],
                "output_scope": self.state["scope"]}

    def current_view(self):
        from .probe_bridge import unbridged_model_outside
        return {**self.raw_view(), "claims": list(self.active_claims().values()),
                "unknowns": list(self.state["unknowns"].values()),
                "work_results": deepcopy(self.state["work_results"]),
                "breakthrough_receipts": deepcopy(self.state.get("breakthrough_receipts", [])),
                "foci": deepcopy(self.state.get("foci", [])),
                "system_map":deepcopy(self.state.get("system_map")),
                "scope_intent":deepcopy(self.state.get("scope_intent")),
                "goal_review":deepcopy(self.state.get("goal_review")),
                "pending_delta_sources":deepcopy(self.state.get("pending_delta_sources", [])),
                "entry_unresolved": self.state.get("entry_unresolved", False),
                "bridge_gaps": unbridged_model_outside(self),
                "discovery_inquiries": discovery_inquiries(self),
                "probe_portfolio": deepcopy(self.state.get("probe_portfolio")),
                "load_bearing_audit": deepcopy(self.state.get("load_bearing_audit")),
                "decision_tournament": deepcopy(self.state.get("decision_tournament")),
                "entry_review": deepcopy(self.state.get("entry_review", {})),
                "exploration_opportunities": deepcopy(list(self.state.get("exploration_opportunities", {}).values())),
                "web_research_leads": deepcopy(list(self.state.get("web_research_leads", {}).values())),
                "recent_turns": deepcopy(self.state["turn_history"][-2:]),
                "last_verified_primary_turn": deepcopy(next((t for t in reversed(self.state["turn_history"])
                    if t.get("release") and (t.get("draft") or {}).get("output",{}).get("navigation",{}).get("mode") == "primary"), None)),
                "task_thread": deepcopy(self.state.get("task_thread", {})),
                "research_frontier": deepcopy(self.research_frontier()),
                "research_agenda": deepcopy(agenda(self.state)),
                "pending_turn": deepcopy(self.state.get("pending_turn")),
                "latest_user_message": deepcopy(self.state.get('sources', {}).get(self.state.get('current_turn_source_id'))),
                "user_input_policy": self.state.get("task_thread",{}).get("user_input_policy", "open"),
                "interaction_mode": self.state.get("interaction_mode", "primary"),
                "task_navigation": deepcopy(self.state.get("task_navigation", {})),
                "previously_delivered_interventions": {k: sorted(v) for k, v in self.previously_delivered_interventions().items()},
                "action_preflight": deepcopy(self.state.get("action_preflight")),
                "adoption_relevant": self.state.get("adoption_relevant", False),
                "latest_question_resolution": deepcopy(self.state.get('latest_question_resolution', [])),
                "budget_limited": self.state["budget_limited"],
                "expansion_focus": self.state.get("expansion_focus", ""),
                "expansion_target_scope": self.state.get("expansion_target_scope"),
                "expansion_base_point_ids": deepcopy(self.state.get("expansion_base_point_ids", [])),
                "expansion_runs": deepcopy(self.state.get("expansion_runs", [])),
                "prior_probe_portfolios": deepcopy(self.state.get("portfolio_history", [])[-2:]),
                "pending_evidence_reframes": deepcopy(self.state.get("pending_evidence_reframes", []))}

    def mark_opportunities_attempted(self, task: dict, job_id: str | None = None):
        """Record the real attempt/outcome, not just a scheduler decision.

        A null attempt stays available as history, not as a repeatedly advertised
        unexplored direction. A newly generated relation gets its own new ID.
        """
        ledger = self.state.setdefault('exploration_opportunities', {})
        product = (self.result(job_id) or {}).get('output', {}) if job_id else {}
        advanced = bool(product.get('claims') or product.get('unknowns') or product.get('opportunities'))
        outcome = ('new_leads' if advanced else 'no_increment') if job_id else 'attempted'
        for oid in task.get('opportunity_ids', []):
            if oid not in ledger:
                raise StateDyneError(f'Unknown exploration opportunity: {oid}')
            ledger[oid]['attempts'] = ledger[oid].get('attempts', 0) + 1
            ledger[oid]['state'] = 'examined'
            ledger[oid]['attempt_outcome'] = outcome
            if job_id:
                ledger[oid]['last_attempt_job'] = job_id
        if task.get('opportunity_ids'):
            self.save('search_opportunities_attempted', {'ids': task['opportunity_ids'],
                'operator': task['operator'], 'outcome': outcome, 'worker_job_id': job_id})

    def research_frontier(self):
        """Live source-bounded research agenda, independent of answer stage.

        The agenda contains unexplored model relations, meaningful evidence
        discriminators and user-owned goal trade-offs. During a side exchange
        preserve the last audited primary opening if no new live one exists.
        Explicit new-goal isolation clears the old thread and its old agenda.
        """
        # Do not resurrect an attempted/dead opportunity from an old side-turn
        # snapshot. The live ledger itself persists across a side question.
        return agenda(self.state)

    def receive_user_turn(self, text: str):
        """Default conversational intake; classify the CURRENT turn against the
        frozen primary task before treating it as a new task or evidence.

        Routing is a real model-worker decision with a verifiable input, not a
        keyword heuristic or a silent overwrite of the preceding goal.
        """
        if self.state["phase"] != "done":
            raise StateDyneError("Finish/verify the current stage before accepting a new conversational turn")
        if not isinstance(text, str) or not text.strip():
            raise StateDyneError("Cannot route an empty user turn")
        if len(text.encode("utf-8")) > 2_000_000:
            raise StateDyneError("User turn exceeds 2 MB")
        if self.state.get("pending_turn"):
            raise StateDyneError("Finish the already pending turn before starting another")
        self.state["pending_turn"] = {"text":text,"sha256":text_digest(text),
            "route_index":len(self.state.get("task_thread",{}).get("turn_routes",[]))+1}
        self.state["phase"] = "route_turn"
        self.save("unclassified_user_turn_waiting_for_independent_routing",
                  {"sha256":text_digest(text),"route_index":self.state["pending_turn"]["route_index"]})
        return {"status":"routing_required", "next":"advance", "job_has_run":False}

    def apply_turn_route(self, result: dict, jid: str):
        """Apply only source-grounded routing, with previous verified task intact."""
        from .schemas import validate
        validate(result, SCHEMAS["turn_route"])
        pending=self.state.get("pending_turn")
        if self.state["phase"]!="route_turn" or not pending or text_digest(pending["text"])!=pending["sha256"]:
            raise StateDyneError("No intact pending user turn to route")
        if not result["quoted_trigger"].strip() or result["quoted_trigger"] not in pending["text"]:
            raise StateDyneError("A turn route must cite an unchanged span of the actual new user text")
        route=result["route"]
        if route != "replace_goal" and not result["preserves_primary_goal"]:
            raise StateDyneError("Side questions/refusals cannot silently replace the primary objective")
        if route=="replace_goal" and result["preserves_primary_goal"]:
            raise StateDyneError("An explicitly replaced objective must not pretend it remains the primary task")
        if route in ("pause","close","replace_goal") and not result["reason"].strip():
            raise StateDyneError("A task-lifecycle change needs a specific user-grounded reason")
        if route in ("pause","close","replace_goal") and result["quoted_trigger"].strip() in ("嗯","好的","下一步"):
            raise StateDyneError("A brief acknowledgment cannot terminate or replace the primary objective")
        if result["user_declines_more_questions"] and result["user_invites_questions"]:
            raise StateDyneError("User cannot simultaneously decline and invite more questions")
        if result["user_declines_more_questions"] and len(result["no_new_information_route"].strip()) < 30:
            raise StateDyneError("When the user declines questions, provide a substantive route that does not request more user details")
        if route=="expand" and not result["expansion_focus"].strip():
            raise StateDyneError("An expansion must identify a concrete research direction")
        thread=self.state.setdefault("task_thread",{})
        if result["user_declines_more_questions"]:
            thread["user_input_policy"]="no_repeated_questions_without_invitation"
            thread["independent_continuation_plan"] = result["no_new_information_route"].strip()
            thread['force_independent_continuation']=True
        elif result["user_invites_questions"]:
            thread["user_input_policy"]="open"
        thread.setdefault("turn_routes",[]).append({"index":pending["route_index"],
            "route":route,"trigger":result["quoted_trigger"],"reason":result["reason"],
            "user_declines_more_questions":result["user_declines_more_questions"],
            "user_invites_questions":result["user_invites_questions"],
            "real_worker_job":jid})
        thread["last_route"] = route
        self.mark_result(jid)
        message=pending["text"]
        self.state["pending_turn"]=None
        # The last *released* primary answer remains intact until the chosen
        # action archives it. Side questions retain its stage and goal.
        self.state["phase"]="done"
        self.save("grounded_turn_route_accepted",{"route":route,"router_job":jid,
            "primary_goal_preserved":route!="replace_goal","user_input_policy":thread["user_input_policy"]})
        if route=="next":
            thread['status']='active'  # The user explicitly resumed the previous workflow.
            self.continue_stage("next")
        elif route=="expand":
            thread['status']='active'
            self.expand_search(result["expansion_focus"])
        elif route=="replace_goal":
            # A new independent goal is an epistemic boundary, not a delta
            # to the old model. Keep only an archive marker, never pass old
            # sources/claims/answers to workers for the new goal.
            self.isolate_replaced_goal(message)
        else:
            if route=="pause":thread["status"]="paused"
            elif route=="close":thread["status"]="closed"
            elif thread.get("status")!="closed":thread["status"]="active" if route=="main_update" else thread.get("status","active")
            self.update(message, interaction="feedback" if route=="main_update" else "side_question")
        self.save("routed_user_turn_applied",{"route":route,"phase":self.state["phase"],
                  "main_stage":self.state.get("task_navigation",{}).get("last_primary_scope")})
        return route

    def isolate_replaced_goal(self, message: str):
        """Start a genuinely fresh cognitive epoch inside an auditable workspace.

        Retain old bytes/event hashes as inactive history but make current/raw
        views contain ONLY material authorized for the new goal. This is
        required when a user changes subject and forbids prior conversations.
        """
        prior_thread = deepcopy(self.state.get('task_thread', {}))
        old_root = prior_thread.get('root_source_id')
        if not old_root or not self.state.get('sources', {}).get(old_root, {}).get('active'):
            raise StateDyneError('Cannot safely isolate a new goal without an active prior task source')
        prior_generation=self.state['generation']
        previous_scope=self.state.get('task_navigation',{}).get('last_primary_scope')
        # supersedes forces a full new raw discovery, not delta_assess.
        sid=self.update(message, supersedes=old_root, scope='auto', interaction='feedback')
        for key,source in self.state['sources'].items():
            if key != sid:
                source['active']=False
                source['is_task']=False
        self.state['sources'][sid]['is_task']=True
        for key, default in (
            ('claims',{}),('unknowns',{}),('work_results',[]),
            ('exploration_opportunities',{}),('web_research_leads',{}),
            ('investigated_unknowns',[]),('environment_questions_attempted',[]),('pending_evidence_reframes',[]),
            ('system_map_history',[]),('goal_review_history',[]),
            ('load_bearing_history',[]),('portfolio_history',[]),
            ('expansion_runs',[]),('breakthrough_receipts',[]),
            ('turn_history',[]),('foci',[])):
            self.state[key]=deepcopy(default)
        # Past task contents and turn summaries are not sent in current_view.
        # Keep only non-content archival audit identifiers.
        self.state.setdefault('archived_goal_boundaries',[]).append({
            'prior_generation':prior_generation,
            'prior_task_source':old_root,
            'prior_scope':previous_scope,
            'new_goal_source':sid})
        self.state['task_thread']={
            'status':'active', 'root_source_id':sid, 'turn_routes':[],
            'user_input_policy':'open', 'latest_unfinished_goal':message,
            'last_verified_primary_stage':None,'latest_valuable_search':'',
            'research_frontier':[], 'force_independent_continuation':False}
        self.state['task_navigation']={
            'last_primary_scope':None,'last_next_scope':None,
            'last_answer_anchor':'','last_release_cycle':None}
        self.state['scope']='auto'
        self.state['interaction_mode']='primary'
        self.state['current_turn_source_id']=sid
        self.state['value_frontier_done']=False
        self.state['phase']='discover'
        self.save('independent_replacement_goal_isolated_from_prior_task',{
            'new_goal_source':sid,'prior_generation':prior_generation,
            'new_generation':self.state['generation']})
        return sid

    def continue_stage(self, scope: str):
        """One user-approved phase advance, reusing identical sources and discovery.

        No new evidence is invented, no old independent audit is recycled for
        the next deliverable, and the new stage gets its own draft+audit.
        """
        if scope == "next":
            current = self.state.get("task_navigation", {}).get("last_primary_scope")
            stages = {"analysis": "points", "points": "actions", "actions": "plan"}
            scope = stages.get(current)
            if scope is None:
                frontier=self.research_frontier()
                independently_researchable = next((x for x in frontier if x['route'] in
                    ('self_research','public_source','materials','calculation',
                     'compare_without_replacing_user_goal')), None)
                if independently_researchable:
                    return self.expand_search(independently_researchable['focus'][:2000])
                raise StateDyneError("No verified next stage or independently researchable frontier; a user-only or unavailable fact cannot be silently researched as if obtained")
        if scope not in ("points", "actions", "plan"):
            raise StateDyneError("Continuation accepts next, points, actions or plan")
        if self.state["phase"] != "done":
            raise StateDyneError("Only a fully released stage can continue; finish/verify the current stage first")
        previous = {"scope": self.state.get("delivery_scope", self.state["scope"]),
                    "generation": self.state["generation"],
                    "draft": deepcopy(self.state.get("draft")),
                    "audit": deepcopy(self.state.get("audit")),
                    "release": read_json(self.root / "release.json"),
                    "answer": (self.root / read_json(self.root / "release.json")["answer_file"]).read_text(encoding="utf-8")}
        self.state["turn_history"].append(previous)
        self.state["scope"] = scope
        self.state["delivery_scope"] = scope
        self.state["interaction_mode"] = "primary"
        self.state['open_search_requested'] = False
        self.state['expansion_target_scope'] = None
        self.state['expansion_base_point_ids'] = []
        self.state.pop('scope_intent', None)
        self.state["delivery_cycle"] = self.state.get("delivery_cycle", 0) + 1
        self.state["phase"] = "schedule"
        self.state["operations_done"] = 0
        self.state["repairs_done"] = 0
        self.state["budget_limited"] = False
        self.state["stop_reason"] = ""
        self.state["draft"] = None
        self.state["audit"] = None
        self.state["completed_operators"] = []
        # The previous stage was genuinely audited, and the facts and goal
        # have not changed: reuse completed point search AND backstage action
        # exploration. A new evidence/update path invalidates this cache.
        verified_prior = self.previously_delivered_interventions()
        reuse_point_frontier = bool(
            (scope == 'actions' and verified_prior['point']) or
            (scope == 'plan' and verified_prior['point'] and verified_prior['action'])
        )
        self.state['intervention_frontier_done'] = reuse_point_frontier
        self.state['preflight_reused_from_prior_stage'] = bool(
            reuse_point_frontier and self.state.get('action_preflight') and
            self.state['action_preflight'].get('source_generation') == self.state['generation']
        )
        # A changed output objective still requires a fresh independent
        # load-bearing decision audit; only unchanged search is reused.
        self.state['load_bearing_complete']=False
        for field in ("repair_issues", "decisions", "active_job_ids", "last_error"):
            self.state.pop(field, None)
        for name in ("answer.md", "simulation-answer.md", "release.json", "draft-only.md"):
            (self.root / name).unlink(missing_ok=True)
        self.save("stage_continued_without_repeating_unchanged_raw_discovery",
                  {"scope": scope, "cycle": self.state["delivery_cycle"],
                   "reused_audited_point_frontier": reuse_point_frontier,
                   "reused_action_preflight": self.state["preflight_reused_from_prior_stage"]})

    def expand_search(self, focus: str = ''):
        """Explicit continuation that searches *outside* a released model.

        This is neither a scope change to intervention nor a source update.
        Preserve the previous reviewed answer, claims and source identity.
        No worker output is invented merely by requesting the search.
        """
        if self.state['phase'] != 'done':
            raise StateDyneError('Expansion requires a completed, independently reviewed stage')
        if not isinstance(focus, str) or len(focus) > 2000:
            raise StateDyneError('Optional expansion focus must be text <=2000 characters')
        last_release = read_json(self.root/'release.json')
        previous = {'scope': self.state.get('delivery_scope', self.state['scope']),
                    'generation': self.state['generation'],
                    'draft': deepcopy(self.state.get('draft')),
                    'audit': deepcopy(self.state.get('audit')),
                    'release': last_release,
                    'answer': (self.root/last_release['answer_file']).read_text(encoding='utf8')}
        self.state['turn_history'].append(previous)
        # Preserve the user-authorized deliverable. A request for additional
        # POINTS must not silently fall back to a generic explanatory report.
        prior_scope = self.state.get('delivery_scope', self.state['scope'])
        if self.state.get('interaction_mode') == 'side':
            prior_scope = self.state.get('task_navigation', {}).get('last_primary_scope') or prior_scope
        if prior_scope == 'auto':
            prior_scope = 'analysis'
        self.state['scope'] = prior_scope
        self.state['delivery_scope'] = prior_scope
        self.state['expansion_target_scope'] = prior_scope
        self.state['expansion_base_point_ids'] = sorted(
            self.previously_delivered_interventions()['point']
        ) if prior_scope == 'points' else []
        self.state.pop('scope_intent',None)
        self.state['delivery_cycle'] += 1
        self.state['phase'] = 'expand_frontier'
        self.state['value_frontier_done'] = False
        self.state['open_search_requested'] = True
        self.state['interaction_mode'] = 'primary'
        self.state['expansion_focus'] = focus.strip()
        self.state['operations_done'] = 0
        self.state['repairs_done'] = 0
        self.state['schedule_round'] = 0
        self.state['budget_limited'] = False
        self.state['stop_reason'] = ''
        self.state['draft'] = None
        self.state['audit'] = None
        self.state['completed_operators'] = []
        self.state['intervention_frontier_done'] = False
        self.state['load_bearing_complete'] = False
        self.state['load_bearing_audit'] = None
        # Retain deferred prior tournament probes as well as admitted unknowns:
        # otherwise the next model-outside search may repeat a rejected idea.
        if self.state.get('probe_portfolio'):
            self.state.setdefault('portfolio_history', []).append(
                deepcopy(self.state['probe_portfolio']))
        self.state['portfolio_complete'] = False
        self.state['probe_portfolio'] = None
        for field in ('repair_issues','decisions','active_job_ids','last_error'):
            self.state.pop(field,None)
        for filename in ('answer.md','simulation-answer.md','release.json','draft-only.md'):
            (self.root/filename).unlink(missing_ok=True)
        self.save('explicit_expand_kept_evidence_and_prior_verified_result',
                  {'cycle':self.state['delivery_cycle'],'focus':self.state['expansion_focus']})

    def active_claims(self):
        return {key: value for key, value in self.state["claims"].items() if value["state"] == "current"}

    def cognition_hash(self):
        return digest({"sources": self.state["sources"], "claims": self.state["claims"],
                       "unknowns": self.state["unknowns"], "scope": self.state["scope"],
                       "generation": self.state["generation"], "work_results": self.state["work_results"],
                       "foci": self.state.get("foci", []), "entry_reviews": self.state.get("entry_reviews", []),
                       "exploration_opportunities": self.state.get("exploration_opportunities", {}),
                       "probe_portfolio": self.state.get("probe_portfolio"),
                       "load_bearing_audit": self.state.get("load_bearing_audit"),
                       "delivery_scope": self.state.get("delivery_scope"),
                       "scope_intent": self.state.get("scope_intent"),
                       "goal_review": self.state.get("goal_review"),
                       "adoption_relevant": self.state.get("adoption_relevant"),
                       "expansion_focus": self.state.get("expansion_focus", ""),
                       "expansion_target_scope": self.state.get("expansion_target_scope"),
                       "expansion_base_point_ids": self.state.get("expansion_base_point_ids", []),
                       "expansion_runs": self.state.get("expansion_runs", []),
                       "portfolio_history": self.state.get("portfolio_history", []),
                       "pending_evidence_reframes": self.state.get("pending_evidence_reframes", [])})

    def get_job(self, tag: str, role: str, schema: str, inputs: dict, instructions: str):
        # Tags identify a fixed stage. Re-entering a paused stage never rewrites inputs.
        for item in self.state["jobs"].values():
            if item["tag"] == tag and item["status"] != "rejected":
                return self.job_request(item["id"])
        if len(self.state["jobs"]) >= self.state["config"]["max_jobs"]:
            raise StateDyneError("Job budget exhausted; no audited answer is released")
        if len(canonical(inputs)) > self.state["config"]["max_input_characters"]:
            raise StateDyneError("Context budget exceeded; input was not silently summarized or truncated")
        jid = f"J{len(self.state['jobs']) + 1:04d}"
        request = {"id": jid, "tag": tag, "role": role, "schema_name": schema,
                   "schema": SCHEMAS[schema], "inputs": inputs, "instructions": instructions,
                   "model": self.state["model"], "backend": self.state["backend"],
                   "input_version": self.state["revision"], "generation": self.state["generation"]}
        request["input_sha256"] = digest(request)
        save_json(self.root / "jobs" / jid / "request.json", request)
        self.state["jobs"][jid] = {"id": jid, "tag": tag, "role": role, "status": "pending",
                                  "input_sha256": request["input_sha256"]}
        self.save("job_created", {"id": jid, "role": role, "input_hash": request["input_sha256"]})
        return request

    def job_request(self, jid: str):
        if jid not in self.state["jobs"]:
            raise StateDyneError("Unknown job ID")
        request = read_json(self.root / "jobs" / jid / "request.json")
        check = dict(request)
        claimed = check.pop("input_sha256")
        if digest(check) != claimed or claimed != self.state["jobs"][jid]["input_sha256"]:
            raise StateDyneError("Job request integrity mismatch")
        return request

    def retry_job(self, jid: str, reason: str):
        record = self.state["jobs"].get(jid)
        if not record or record["status"] != "pending":
            raise StateDyneError("Only an unaccepted pending job can be retried; accepted work needs a new evidence/update cycle")
        old = self.job_request(jid)
        if old["generation"] != self.state["generation"] or not reason.strip():
            raise StateDyneError("Retry requires a current job and an explicit failure reason")
        record["status"] = "rejected"
        record["rejection_reason"] = reason
        self.save("attempt_retained_for_explicit_retry", {"job_id": jid, "reason": reason})
        # Same source boundary; no sibling diagnosis is introduced by the retry.
        prompt = old["instructions"] + "\n\nA previous attempt was rejected by the controller: " + reason + "\nCorrect the observable product. Do not claim the rejected attempt succeeded."
        new = self.get_job(old["tag"], old["role"], old["schema_name"], old["inputs"], prompt)
        record["superseded_by"] = new["id"]
        self.save("retry_job_created", {"old_job": jid, "new_job": new["id"]})
        return new

    def result(self, jid: str):
        path = self.root / "jobs" / jid / "result.json"
        if not path.exists():
            return None
        result = read_json(path)
        request = self.job_request(jid)
        if result["input_sha256"] != request["input_sha256"] or digest(result["output"]) != result["output_sha256"]:
            raise StateDyneError("Result not bound to the current immutable request")
        validate(result["output"], request["schema"])
        return result

    def mark_result(self, jid: str):
        if self.result(jid) is None:
            raise StateDyneError("No actual result exists")
        self.state["jobs"][jid]["status"] = "completed"

    def exposed(self, jid: str, result: dict):
        request = self.job_request(jid)
        allowed = {s["id"]: [s["text"]] for s in request["inputs"].get("task_sources", [])}
        for sid, passages in result.get("exposed_passages", {}).items():
            allowed.setdefault(sid, []).extend(passages)
        return allowed

    def check_evidence(self, evidence: list, *, exposed=None):
        for ref in evidence:
            sid, quote = ref["source_id"], ref["quote"]
            source = self.state["sources"].get(sid)
            if not source or not source["active"] or not quote.strip() or quote not in source["text"]:
                raise StateDyneError(f"Source/quote mismatch: {sid}")
            if exposed is not None and not any(quote in p for p in exposed.get(sid, [])):
                raise StateDyneError(f"Unseen source passage cited: {sid}; read it through the evidence tool")

    def merge_work(self, jid: str):
        if jid in [w["job_id"] for w in self.state["work_results"]]:
            return
        result = self.result(jid)
        if result is None:
            raise StateDyneError("Cannot merge an unexecuted job")
        output = result["output"]
        validate(output, SCHEMAS["work"])
        ids = [c["local_id"] for c in output["claims"]] + [q["local_id"] for q in output["unknowns"]]
        if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", x) for x in ids):
            raise StateDyneError("Local IDs must be unique ASCII identifiers")
        if not output["summary"].strip():
            raise StateDyneError("Work needs an actual summary")
        if not output["claims"] and not output["unknowns"] and not output["no_increment_reason"].strip():
            raise StateDyneError("No work increment and no evidence-based no-increment reason")
        mapping = {c["local_id"]: f"{jid}:{c['local_id']}" for c in output["claims"]}
        known = set(self.active_claims()) | set(mapping.values())
        new_claims = {}
        seen = self.exposed(jid, result)
        for claim in output["claims"]:
            claim = deepcopy(claim)
            local = claim.pop("local_id")
            claim["id"] = mapping[local]
            if not claim["statement"].strip() or not claim["mechanism"]["transformation"].strip():
                raise StateDyneError("A claim requires an actual statement and transformation, not a label")
            claim["depends_on"] = [mapping.get(x, x) for x in claim["depends_on"]]
            if not set(claim["depends_on"]).issubset(known):
                raise StateDyneError("Unknown or stale claim dependency")
            self.check_evidence(claim["evidence"], exposed=seen)
            claim.update(state="current", origin_job=jid, version=1)
            new_claims[claim["id"]] = claim
        graph = {**self.active_claims(), **new_claims}
        visited, visiting = set(), set()
        def visit(cid):
            if cid in visiting:
                raise StateDyneError("Circular justification dependency (real temporal feedback belongs in mechanism.feedback)")
            if cid in visited:
                return
            visiting.add(cid)
            for dep in graph[cid]["depends_on"]:
                visit(dep)
            visiting.remove(cid)
            visited.add(cid)
        for cid in new_claims:
            visit(cid)
        for claim in new_claims.values():
            if claim["kind"] == "action" and not any(graph[d]["kind"] == "point" for d in claim["depends_on"]):
                raise StateDyneError("An action must map to at least one separately represented intervention point")
            if claim["kind"] == "plan" and not any(graph[d]["kind"] == "action" for d in claim["depends_on"]):
                raise StateDyneError("A plan must map to at least one independently represented action")
        new_unknowns = {}
        for unknown in output["unknowns"]:
            item = deepcopy(unknown)
            local = item.pop("local_id")
            item["id"] = f"{jid}:{local}"
            item["related_claims"] = [mapping.get(x, x) for x in item["related_claims"]]
            if not set(item["related_claims"]).issubset(known):
                raise StateDyneError("Unknown question dependency")
            if not item["question"].strip() or not item["why_it_matters"].strip():
                raise StateDyneError("An information request must have a discriminating purpose")
            item.update(state="open", origin_job=jid, disposition_evidence=[])
            new_unknowns[item["id"]] = item
        # Opportunities are observable work proposals, not extra fixed stages.
        # They are retained across workers, ranked by the scheduler, and never
        # silently deleted when a candidate loses a comparison.
        proposals, reused = {}, []
        existing_opportunities = self.state.setdefault("exploration_opportunities", {})
        def signature(message):
            # Only exact-normalised duplicates are merged automatically.
            # Semantic similarity needs independent review, not a regex.
            return re.sub(r"[\W_]+", " ", message.casefold(), flags=re.UNICODE).strip()
        prior = {signature(item["description"]): oid for oid, item in existing_opportunities.items()
                 if item.get("state") != "stale"}
        for idx, statement in enumerate(output["opportunities"]):
            if not statement.strip():
                raise StateDyneError("Exploration opportunity must describe a real possible gain")
            fingerprint = signature(statement)
            if fingerprint in prior:
                reused.append(prior[fingerprint])
                existing_opportunities[prior[fingerprint]].setdefault("proposed_by", []).append(jid)
                continue
            oid = f"{jid}:O{idx + 1}"
            proposals[oid] = {"id": oid, "description": statement,
                              "origin_job": jid, "state": "open", "attempts": 0,
                              "generation_opened": self.state["generation"], "proposed_by": [jid]}
            prior[fingerprint] = oid
        # Only after validating the entire product do we change state.
        self.state["claims"].update(new_claims)
        self.state["unknowns"].update(new_unknowns)
        self.state.setdefault("exploration_opportunities", {}).update(proposals)
        # Search annotations are discoverability leads, not verified passages.
        # They remain visible for independent retrieval and source checks.
        for lead in result.get("web_research_leads", []):
            if not isinstance(lead, dict) or not isinstance(lead.get("url"), str):
                continue
            url = lead["url"]
            if not url.startswith(("http://", "https://")) or len(url) > 2048:
                continue
            self.state.setdefault("web_research_leads", {})[url] = {
                "url": url, "title": str(lead.get("title", ""))[:512],
                "origin_job": jid, "verified_source": False,
                "warning": "Search citation is not a downloaded and independently verified source passage"}
        self.state["work_results"].append({"job_id": jid, "summary": output["summary"],
            "claim_ids": list(new_claims), "unknown_ids": list(new_unknowns),
            "opportunities": output["opportunities"], "opportunity_ids": list(proposals) + reused,
            "no_increment_reason": output["no_increment_reason"],
            "full_output_path": f"jobs/{jid}/result.json", "output_sha256": result["output_sha256"]})
        self.mark_result(jid)
        self.save("work_admitted_without_main_agent_veto", {"job_id": jid, "claims": list(new_claims), "unknowns": list(new_unknowns)})

    def previously_delivered_interventions(self):
        """Intervention IDs visibly released in earlier *audited* turns.

        A prior report's unfinished draft does not authorize skipping a stage.
        A superseded claim does not count as a currently usable point/action.
        """
        active = self.active_claims()
        historical = {"point": set(), "action": set(), "plan": set()}
        for turn in self.state.get("turn_history", []):
            if not turn.get("release") or not turn.get("audit"):
                continue
            if turn["audit"]["output"]["verdict"] != "pass":
                continue
            for item in (turn.get("draft") or {}).get("output", {}).get("delivery_units", []):
                cid, kind = item["claim_id"], item["kind"]
                if cid in active and active[cid]["kind"] == kind:
                    historical[kind].add(cid)
        return historical

    def check_navigation_contract(self, draft: dict):
        """Bind the user-visible follow-up to the verified primary work stage.

        A side question has its own answer but does not erase or advance the
        main workflow. The UI affordance itself remains the host's decision.
        """
        nav = draft['navigation']
        # User can request a concise final answer for THIS turn while leaving
        # the long-lived research state available for a later explicit resume.
        # This is not a destructive pause/close or a permission to ignore
        # independently worthwhile research during answer production.
        quiet_quote = nav.get('quiet_reply_quote', '').strip()
        quiet_reply = bool(quiet_quote)
        if quiet_reply:
            latest = self.state.get('sources', {}).get(self.state.get('current_turn_source_id'), {})
            if (latest.get('kind') != 'user_reported' or len(quiet_quote) < 6
                    or quiet_quote not in latest.get('text', '')):
                raise StateDyneError('Quiet current-turn closure must quote the latest user request verbatim')
            if any(nav.get(k, '').strip() for k in ('next_offer', 'expansion_offer', 'visible_anchor')):
                raise StateDyneError('A user-requested quiet answer cannot also push continuation offers')
        mode = self.state.get('interaction_mode', 'primary')
        if nav['mode'] != mode:
            raise StateDyneError('Navigation misclassified the current primary stage versus side question')
        actual = self.state.get('delivery_scope', self.state['scope'])
        if actual == 'auto':
            actual = 'analysis'
        prior = self.state.get('task_navigation', {}).get('last_primary_scope')
        stage = prior if mode == 'side' and prior else actual
        if nav['primary_stage'] != stage:
            raise StateDyneError('Navigation lost the last verified primary stage')
        following = {'analysis': 'points', 'points': 'actions', 'actions': 'plan', 'plan': 'none'}[stage]
        if nav['next_stage'] != following:
            raise StateDyneError('Navigation skipped, repeated or incorrectly advanced a stage')
        if not nav['reason'].strip():
            raise StateDyneError('Navigation needs a task-grounded continuation rationale')
        answer = draft['answer']
        if not quiet_reply and following != 'none' and self.state.get('task_thread',{}).get('status','active') == 'active':
            if not nav['next_offer'].strip() or not nav['visible_anchor'].strip():
                raise StateDyneError('An active multi-stage task must keep a real next-step bridge')
        if nav['next_stage'] == 'none' and nav['next_offer'].strip():
            raise StateDyneError('Do not promise a nonexistent next stage')
        if self.state.get('task_thread',{}).get('status','active') in ('paused','closed'):
            if nav['next_offer'].strip() or nav['expansion_offer'].strip():
                raise StateDyneError('Explicitly paused/closed work must not solicit the next stage or continued search')
        elif not quiet_reply:
            # Material unresolved research has an optional concrete continuation;
            # this is not a requirement to ask the user another question.
            active_agenda = meaningful_frontier(self.state)
            if active_agenda and not nav['expansion_offer'].strip():
                raise StateDyneError('Material research agenda requires a visible optional further-research path, not a silent stop')
            if nav['expansion_offer'].strip() and nav['next_stage'] == 'none' and not nav['visible_anchor'].strip():
                raise StateDyneError('Research after the last staged deliverable still needs a visible continuation anchor')
            # An open, source-backed alternative relation/goal must actually
            # be named in the user-facing next-step sentence. Generic "you
            # can still explore" prose does not satisfy this binding.
            high_value_routes = [x for x in agenda(self.state)
                if x.get('ready') and x['kind'] in ('new_relation','goal_tradeoff')]
            if high_value_routes:
                focus_id = nav.get('research_focus_id', '').strip()
                excerpt = nav.get('research_focus_excerpt', '').strip()
                linked = next((x for x in high_value_routes if x['id'] == focus_id), None)
                if not linked or len(excerpt) < 4 or excerpt not in linked['focus']:
                    raise StateDyneError('Concrete research continuation must bind a real open relation/goal and quote its focus')
                if excerpt not in nav['expansion_offer']:
                    raise StateDyneError('The expansion offer must identify its actual recorded research target, not give a generic slogan')
        for field in ('next_offer', 'expansion_offer', 'visible_anchor'):
            if nav[field] and nav[field] not in answer:
                raise StateDyneError(f'Navigation {field} is not present in the reviewed answer')
        if nav['visible_anchor'].strip() and len(nav['visible_anchor'].strip()) < 8:
            raise StateDyneError('The visible bridge must be an intelligible natural-language phrase')

    def check_delivery_contract(self, draft: dict):
        """Verify user-requested intervention stages in the released *text*.

        Checks only explicit stage binding and provenance, not whether the
        intervention will work or if an ordering is clinically/scientifically right.
        """
        current = self.active_claims()
        chosen_scope = self.state.get("delivery_scope", self.state["scope"])
        if chosen_scope == "auto":
            chosen_scope = "analysis"
        used = set(draft["used_claim_ids"])
        if chosen_scope in ('points','actions','plan'):
            goal_line=draft['goal_line'].strip()
            if not goal_line or goal_line not in draft['answer']:
                raise StateDyneError('An intervention deliverable must visibly state the goal before ranking intervention points')
            goal=self.state.get('system_map') or {}
            if goal.get('goal_basis')=='missing' and draft['status']=='complete':
                raise StateDyneError('Do not claim complete intervention without a supported target outcome; mark conditional goal')
        prior = self.previously_delivered_interventions()
        # An actions turn after a points turn MUST NOT re-present the old
        # catalogue; a plan turn after actions should not repeat that catalogue.
        # Direct one-turn requests still present all needed stages separately.
        if chosen_scope == "analysis":
            allowed = set()
        elif chosen_scope == "points":
            allowed = {"point"}
        elif chosen_scope == "actions":
            allowed = {"action"} if prior["point"] else {"point", "action"}
        else:
            allowed = ({"plan"} if prior["action"] else
                       {"action", "plan"} if prior["point"] else
                       {"point", "action", "plan"})
        indexed, by_kind = set(), {"point": [], "action": [], "plan": []}
        last_stage = -1
        last_visible_position = -1
        stage_order = {"point": 0, "action": 1, "plan": 2}
        for item in draft["delivery_units"]:
            cid, kind = item["claim_id"], item["kind"]
            if kind not in allowed:
                raise StateDyneError(f"Stage boundary violated: {chosen_scope} turn cannot deliver {kind} here")
            if cid not in current or current[cid]["kind"] != kind or cid not in used:
                raise StateDyneError("Visible delivery item must bind a selected claim of the matching kind")
            if cid in indexed:
                raise StateDyneError("A selected intervention item appears twice in the delivery contract")
            if (kind == 'point' and chosen_scope == 'points'
                    and self.state.get('open_search_requested')
                    and cid in set(self.state.get('expansion_base_point_ids', []))):
                raise StateDyneError('Point expansion must deliver actual new point value, not reprint an old selected point')
            indexed.add(cid)
            if not item["visible_text"].strip() or item["visible_text"] not in draft["answer"]:
                raise StateDyneError("A point/action/plan must be independently visible in the answer")
            if not item["comparison"].strip() or item["comparison"] not in draft["answer"]:
                raise StateDyneError("Each intervention stage needs a visible comparative selection/priority reason")
            if stage_order[kind] < last_stage:
                raise StateDyneError("Visible intervention stages must be ordered: points, then actions, then plan")
            position = draft["answer"].find(item["visible_text"])
            if position <= last_visible_position:
                raise StateDyneError("The real answer must show intervention points before actions and plans")
            last_visible_position = position
            last_stage = stage_order[kind]
            by_kind[kind].append(cid)
        # Claim-use is a user-facing commitment. Do not smuggle future-phase
        # action/plan claims into earlier drafts under a conditional label.
        chosen_interventions = {cid for cid in used if current[cid]["kind"] in by_kind}
        missing = chosen_interventions - indexed
        if missing:
            raise StateDyneError(f"Selected intervention claims missing from actual delivery: {sorted(missing)}")
        visible_or_prior_points = set(by_kind["point"]) | prior["point"]
        visible_or_prior_actions = set(by_kind["action"]) | prior["action"]
        for aid in by_kind["action"]:
            if not any(pid in visible_or_prior_points for pid in current[aid]["depends_on"]):
                raise StateDyneError("Every visible action must map to a separately delivered intervention point in this or a prior audited turn")
        for pid in by_kind["plan"]:
            if not any(aid in visible_or_prior_actions for aid in current[pid]["depends_on"]):
                raise StateDyneError("A visible plan must map to separately delivered actions in this or a prior audited turn")
        # A genuine *null* continuation is a valid result of additional
        # research. Never force a point that does not exist merely to satisfy
        # a display-stage quota. Existing points may not be copied into a new
        # point-expansion deliverable, and the null research must have an
        # actual independent search receipt and a visible explanation.
        expansion_no_better_point = False
        if (chosen_scope == 'points' and self.state.get('open_search_requested')
                and not by_kind['point']):
            base = set(self.state.get('expansion_base_point_ids', []))
            new_active_points = {cid for cid, c in current.items()
                if c['kind'] == 'point' and cid not in base}
            run = (self.state.get('expansion_runs') or [])[-1:]
            if (not new_active_points and run and run[0].get('cycle') == self.state.get('delivery_cycle')
                    and not run[0].get('candidate_count') and not run[0].get('unknown_count')
                    and len((run[0].get('no_increment_reason') or '').strip()) >= 40):
                reason = draft['delivery_limit_reason'].strip()
                if len(reason) < 20 or reason not in draft['answer']:
                    raise StateDyneError('Null expansion must visibly explain why no independently better point was found')
                expansion_no_better_point = True
        # A stage can be legitimately unavailable; never invent an action just
        # for schema completion, and never report that case as a full release.
        if chosen_scope == "analysis":
            incomplete = []
        elif chosen_scope == "points":
            incomplete = [] if by_kind["point"] or expansion_no_better_point else ["point"]
        elif chosen_scope == "actions":
            incomplete = ([] if visible_or_prior_points else ["point"]) + ([] if by_kind["action"] else ["action"])
        else:
            incomplete = ([] if visible_or_prior_points else ["point"]) + ([] if visible_or_prior_actions else ["action"]) + ([] if by_kind["plan"] else ["plan"])
        if incomplete:
            reason = draft["delivery_limit_reason"].strip()
            if draft["status"] == "complete" or not reason or reason not in draft["answer"]:
                raise StateDyneError("Requested intervention stages are missing; deliver a justified provisional limitation, not a silent skip")
        elif draft["delivery_limit_reason"].strip() and draft["delivery_limit_reason"] not in draft["answer"]:
            raise StateDyneError("A delivery limitation must be visible")

    def set_draft(self, jid: str):
        result = self.result(jid)
        draft = deepcopy(result["output"])
        validate(draft, SCHEMAS["draft"])
        from .frontier import validate_final_focus
        validate_final_focus(self, draft)
        active = set(self.active_claims())
        dispositions = draft["claim_dispositions"]
        if len(dispositions) != len({x["claim_id"] for x in dispositions}) or {x["claim_id"] for x in dispositions} != active:
            raise StateDyneError("Every active candidate needs a disposition; discoveries cannot silently disappear")
        if any(not d["reason"].strip() for d in dispositions):
            raise StateDyneError("Candidate dispositions need concrete reasons")
        used = set(draft["used_claim_ids"])
        if len(used) != len(draft["used_claim_ids"]) or not used.issubset(active):
            raise StateDyneError("Draft uses unknown or stale claims")
        used_dispositions = {d["claim_id"] for d in dispositions if d["treatment"] in ("use", "conditional")}
        if used != used_dispositions:
            raise StateDyneError("used_claim_ids and use/conditional dispositions disagree")
        self.check_delivery_contract(draft)
        from .decision_tournament import check_draft_against_tournament
        check_draft_against_tournament(self, draft)
        self.check_navigation_contract(draft)
        if self.state.get('task_thread',{}).get('user_input_policy')=='no_repeated_questions_without_invitation':
            blocked=[q for q in draft['information_dispositions'] if q['treatment']=='ask']
            if blocked:
                raise StateDyneError('User declined additional details: use autonomous evidence, conditional branches or a provisional judgment instead of another interview')
        from .conclusion_integrity import check_pivotal_quantities
        from .numeric_provenance import validate_numeric_sources
        from .objective_intersection import validate_objective_joins
        check_pivotal_quantities(self, draft)
        validate_numeric_sources(self, draft)
        validate_objective_joins(self, draft)
        from .frontstage import validate_frontstage
        validate_frontstage(self, draft)
        from .load_bearing import check_draft_against_load_bearing
        check_draft_against_load_bearing(self,draft)
        qs = draft["information_dispositions"]
        if len(qs) != len({x["unknown_id"] for x in qs}) or {x["unknown_id"] for x in qs} != set(self.state["unknowns"]):
            raise StateDyneError("Every declared unknown must be carried or addressed")
        if not draft["answer"].strip():
            raise StateDyneError("Empty draft")
        # Evaluate all epistemic values, not just action-changing choices.
        # This detects silent suppression of candidate-linked new predictions.
        validate_inquiry_dispositions(self, draft)
        from .material_unknowns import validate_material_unknowns
        validate_material_unknowns(self, draft)
        asked = [q for q in qs if q["treatment"] == "ask"]
        for q in asked:
            cap = self.state["config"]["max_question_characters"]
            if cap is not None and len(q["visible_question"]) > cap:
                raise StateDyneError("One user-visible question is too long under the explicit optional cap")
        has_unresolved_blocker = False
        for q in qs:
            if not q["reason"].strip():
                raise StateDyneError("Unknown disposition needs a reason")
            self.check_evidence(q["evidence"])
            if q["treatment"] == "addressed" and not q["evidence"]:
                raise StateDyneError("A claimed answer needs actual source evidence; 'not reported' is not negative evidence")
            if q["treatment"] == "ask":
                if not q["visible_question"].strip() or q["visible_question"] not in draft["answer"]:
                    raise StateDyneError("An 'asked' question must actually appear in the visible answer")
                if q["decision_effect"] not in VALUE_EFFECTS:
                    raise StateDyneError("Do not burden the user with a question without an explanatory, predictive, discovery or action impact")
                if self.state["unknowns"][q["unknown_id"]]["route"] != "user":
                    raise StateDyneError("The solver must pursue non-user information by the available tools or mark the limit, not outsource it as a user question")
            if q["treatment"] != "addressed" and (
                q["decision_effect"] in ACTION_EFFECTS or
                (self.state["unknowns"][q["unknown_id"]]["priority"] == "blocking" and
                 q["decision_effect"] in VALUE_EFFECTS)
            ):
                has_unresolved_blocker = True
            if (self.state["unknowns"][q["unknown_id"]]["priority"] == "blocking" and
                q["treatment"] != "addressed" and q["decision_effect"] not in VALUE_EFFECTS):
                # A previously blocking unknown may cease to block when a newly
                # discovered solution is robust under its competing answers.
                # The justification must be user-visible; do not silently downgrade.
                if not q["fallback_if_unknown"].strip() or q["fallback_if_unknown"] not in draft["answer"]:
                    raise StateDyneError("Downgrading a blocking unknown requires a visible robust/conditional result")
        if (has_unresolved_blocker or self.state["budget_limited"] or self.state.get("entry_unresolved")) and draft["status"] == "complete":
            raise StateDyneError("Cannot claim full completion with a blocking unknown, open first-pass gap or exhausted exploration budget")
        if self.state.get("entry_unresolved"):
            pending = {c["focus_id"] for c in self.state["entry_review"]["output"]["coverage"]
                       if c["status"] in ("partial", "open")}
            statuses = {c["focus_id"]:c["status"] for c in draft["focus_dispositions"]}
            if any(statuses.get(fid) not in ("open", "conditional") for fid in pending):
                raise StateDyneError("A still-open initial generation gap must remain visible as conditional or open")
        for q in qs:
            item = self.state["unknowns"][q["unknown_id"]]
            item["state"] = q["treatment"]
            item["disposition_evidence"] = q["evidence"]
        self.state["draft"] = {"job_id": jid, "output": draft, "sha256": text_digest(draft["answer"]),
                               "payload_sha256": digest(draft), "cognition_hash": self.cognition_hash()}
        self.state["audit"] = None
        atomic_write(self.root / "draft-only.md", draft["answer"] + "\n")
        self.mark_result(jid)
        self.save("draft_bound", {"job_id": jid, "draft_sha256": self.state["draft"]["sha256"]})

    def set_audit(self, jid: str):
        result = self.result(jid)
        audit = result["output"]
        validate(audit, SCHEMAS["audit"])
        request = self.job_request(jid)
        draft = self.state["draft"]
        if (not draft or request["inputs"].get("draft_sha256") != draft["sha256"]
                or request["inputs"].get("draft") != draft["output"]
                or digest(draft["output"]) != draft.get("payload_sha256")):
            raise StateDyneError("Audit is for a different draft or its structural contents changed")
        if draft["cognition_hash"] != self.cognition_hash():
            raise StateDyneError("The cognitive workspace changed after composition")
        for name, expected in (("examined_claim_ids", set(self.active_claims())),
                               ("examined_unknown_ids", set(self.state["unknowns"])),
                               ("examined_focus_ids", {f["id"] for f in self.state.get("foci", [])})):
            if len(audit[name]) != len(set(audit[name])) or set(audit[name]) != expected:
                raise StateDyneError(f"Audit coverage mismatch: {name}")
        issue_ids = [i["issue_id"] for i in audit["issues"]]
        if len(issue_ids) != len(set(issue_ids)):
            raise StateDyneError("Duplicate audit issue IDs")
        known = set(self.active_claims()) | set(self.state["unknowns"])
        for issue in audit["issues"]:
            if not set(issue["target_ids"]).issubset(known) or not issue["finding"].strip() or not issue["repair_request"].strip():
                raise StateDyneError("Audit issue needs a concrete finding, valid targets and a repair request")
        # Evidence-to-causation and intervention-vs-no-extra-action are checked
        # against the *exact released draft*, not a narrative in a side report.
        from .delivery_quality import validate_delivery_quality
        from .conclusion_integrity import check_quantity_review
        from .numeric_provenance import validate_numeric_source_review
        from .objective_intersection import validate_objective_join_review
        validate_delivery_quality(self, audit, draft["output"])
        from .decision_tournament import check_audit_against_tournament
        check_audit_against_tournament(self, audit, draft["output"])
        check_quantity_review(audit, draft["output"])
        validate_numeric_source_review(audit, draft["output"])
        validate_objective_join_review(audit, draft["output"])
        if audit["verdict"] == "pass" and any(i["severity"] == "blocking" for i in audit["issues"]):
            raise StateDyneError("A blocking audit finding cannot be released as pass")
        if audit["verdict"] == "revise" and not audit["issues"]:
            raise StateDyneError("Revision requires a concrete issue, not a ritual 'think harder'")
        self.state["audit"] = {"job_id": jid, "output": audit, "draft_sha256": draft["sha256"],
                               "draft_payload_sha256": draft["payload_sha256"],
                               "cognition_hash": self.cognition_hash()}
        self.mark_result(jid)
        self.save("semantic_review_recorded_not_proven", {"job_id": jid, "verdict": audit["verdict"]})

    def update(self, text: str, supersedes: str | None = None, scope: str | None = None, *,
               source_kind="user_reported", source_label=None, source_url=None,
               interaction="feedback"):
        # This low-level operation is explicit; the conversational default
        # is receive_user_turn(), which routes before writing a task source.
        if interaction not in ("feedback", "side_question"):
            raise StateDyneError("Interaction must be feedback or side_question")
        if interaction == "side_question" and (self.state['phase'] != 'done' or supersedes is not None or source_kind != "user_reported"):
            raise StateDyneError("A side question must extend a completed conversation, not replace evidence or interrupt a live job")
        if supersedes is not None and (supersedes not in self.state["sources"] or not self.state["sources"][supersedes]["active"]):
            raise StateDyneError("Superseded source must be a currently active source")
        if source_kind not in ("user_reported", "retrieved_public", "provided_material"):
            raise StateDyneError("Unsupported source provenance")
        if source_kind == "retrieved_public" and (not isinstance(source_url, str) or not source_url.startswith(("https://", "http://"))):
            raise StateDyneError("A public-source import requires the original HTTP(S) source URL")
        if scope is not None and scope not in ("auto", "analysis", "points", "actions", "plan"):
            raise StateDyneError("Invalid scope")
        if self.state["draft"]:
            published = read_json(self.root / "release.json") if (self.root / "release.json").exists() else None
            self.state["turn_history"].append({"generation": self.state["generation"],
                "scope": self.state.get("delivery_scope", self.state["scope"]),
                "draft": deepcopy(self.state["draft"]), "audit": deepcopy(self.state["audit"]),
                "release": published,
                "answer": ((self.root / published["answer_file"]).read_text(encoding="utf-8") if published else "")})
        if supersedes:
            self.state["investigated_unknowns"] = []  # invalidating an old source reopens evidence work
            self.state["environment_questions_attempted"] = []
            self.state["sources"][supersedes]["active"] = False
            for item in self.state.get("exploration_opportunities", {}).values():
                if item["state"] != "stale":
                    item["state"] = "stale"  # Previous opportunities may depend on the corrected premise.
            stale = {cid for cid, c in self.state["claims"].items()
                     if any(e["source_id"] == supersedes for e in c["evidence"])}
            while True:
                expanded = stale | {cid for cid, c in self.state["claims"].items() if set(c["depends_on"]) & stale}
                if expanded == stale:
                    break
                stale = expanded
            for cid in stale:
                self.state["claims"][cid]["state"] = "stale"
            for q in self.state["unknowns"].values():
                if any(e["source_id"] == supersedes for e in q["disposition_evidence"]):
                    q["state"] = "open"
                    q["disposition_evidence"] = []
        # A new reported/verified fact can change where to look next. Earlier
        # attempts remain in event history, but the knowledge frontier reopens.
        if interaction != 'side_question':
            self.state["investigated_unknowns"] = []
            self.state["environment_questions_attempted"] = []
        sid = self.add_source(source_label or ("User update" if source_kind == "user_reported" else "Imported evidence"),
                              text, kind=source_kind,
                              precision="as_reported" if source_kind == "user_reported" else "as_provided",
                              is_task=(source_kind == "user_reported" and interaction != "side_question"), source_url=source_url)
        self.state['current_turn_source_id']=sid
        # Non-contradictory feedback to a fully completed analysis first enters
        # a *local impact* review; it does not erase all prior cognitive work.
        # Superseding a source or changing an in-flight run falls back to a
        # complete independent re-read because the original boundary changed.
        if supersedes is None and self.state['phase']=='done':
            previous_map=self.state.get('system_map')
            self.state['interaction_mode'] = ('side' if interaction == 'side_question' else 'primary')
            self.state['pending_delta_sources']=[sid]
            self.state['latest_question_resolution']=[]
            self.state['delivery_cycle']=self.state.get('delivery_cycle',0)+1
            self.state['phase']='delta_assess'
            if self.state['interaction_mode'] != 'side' or self.state.get('task_thread',{}).get('force_independent_continuation'):
                self.state['value_frontier_done']=False
            self.state.update(operations_done=0,repairs_done=0,entry_repairs_done=0,
                entry_round=0,schedule_round=0,entry_reviews=[],entry_unresolved=False,
                portfolio_complete=False,probe_portfolio=None,intervention_frontier_done=False,action_preflight=None,
                load_bearing_complete=False,load_bearing_audit=None,
                stop_reason='',budget_limited=False,draft=None,audit=None)
            for key in ('repair_issues','decisions','entry_review','delivery_scope',
                        'scope_intent','adoption_relevant','completed_operators','active_job_ids','last_error'):
                self.state.pop(key,None)
            if self.state['interaction_mode'] == 'side':
                self.state['scope'] = 'analysis'  # Answer the actual short question without repeating points/actions.
                self.state['delivery_scope'] = 'analysis'
            elif scope is not None:
                self.state['scope']=scope
            for name in ('answer.md','simulation-answer.md','release.json','draft-only.md'):
                (self.root/name).unlink(missing_ok=True)
            self.save('additive_fact_triggers_independent_impact_assessment_not_global_replay',
                {'source':sid,'previous_goal':previous_map['goal_text'] if previous_map else None})
            return sid
        self.state['latest_question_resolution']=[]
        self.state['interaction_mode'] = 'primary'
        self.state['value_frontier_done'] = False
        self.state['breakthrough_receipts'] = []
        self.state['task_navigation'] = {"last_primary_scope": None, "last_next_scope": None,
                                         "last_answer_anchor": "", "last_release_cycle": None}
        self.state.update(generation=self.state["generation"] + 1, phase="discover", operations_done=0,
                          repairs_done=0, entry_repairs_done=0, entry_round=0, schedule_round=0,
                          delivery_cycle=0,
                          foci=[], entry_reviews=[], entry_unresolved=False, sweep_complete=False,
                          portfolio_complete=False, probe_portfolio=None,
                          intervention_frontier_done=False,action_preflight=None,system_map=None,goal_review=None,pending_delta_sources=[],processed_delta_sources=[],
                          load_bearing_audit=None,load_bearing_complete=False,load_bearing_round=0,
                          stop_reason="", budget_limited=False, draft=None, audit=None)
        for key in ("repair_issues", "decision", "blind_job", "entry_review", "delivery_scope", "scope_intent", "adoption_relevant", "completed_operators", "blind_complete", "focus_job", "active_job_ids", "last_error"):
            self.state.pop(key, None)
        if scope is not None:
            self.state["scope"] = scope
        for name in ("answer.md", "simulation-answer.md", "release.json", "draft-only.md"):
            (self.root / name).unlink(missing_ok=True)
        self.save("new_evidence_reopens_model_space", {"source": sid,
                                                     "provenance_kind": source_kind,
                                                     "source_url": source_url,
                                                     "supersedes": supersedes})
        return sid

    def invalidate_delta_dependencies(self, assessment, jid: str):
        """Invalidate only relationships that actually depend on changed evidence.

        The decision to keep a causal relation is explicitly model-reviewed,
        not deduced by comparing strings. A contradictory input may still
        require a full rebuild, which delta_assess must report.
        """
        from .frontier import LOCAL_ID
        newly=[]
        exposed=self.exposed(jid,self.result(jid))
        for f in assessment['new_foci']:
            if not LOCAL_ID.fullmatch(f['local_id']) or not f['evidence']:
                raise StateDyneError('Delta focus must have a real anchored raw observation')
            self.check_evidence(f['evidence'], exposed=exposed)
            # An additive observation must actually depend on the new material;
            # prevent the worker from just echoing an old phenomenon.
            if not any(e['source_id'] in self.state.get('pending_delta_sources',[]) for e in f['evidence']):
                raise StateDyneError('Delta focus must cite the newly supplied source')
            if not all(f[k].strip() for k in ('observation','unexplained_difference','why_material')):
                raise StateDyneError('Delta focus must explain a concrete new difference')
            newly.append({**f,'id':f'{jid}:{f["local_id"]}'})
        # Every validation finishes before mutating prior accepted results.
        stale=set(assessment['affected_claim_ids'])
        while True:
            expanded=stale | {cid for cid,c in self.state['claims'].items()
                if c.get('state')=='current' and set(c['depends_on']) & stale}
            if expanded==stale:break
            stale=expanded
        for cid in stale:
            self.state['claims'][cid]['state']='stale'
        for uq in self.state['unknowns'].values():
            if uq['id'] in assessment['affected_unknown_ids'] or set(uq['related_claims']) & stale:
                uq.update(state='open',disposition_evidence=[])
        self.state['foci'].extend(newly)
        self.mark_result(jid)
        self.save('source_specific_delta_dependency_recalculation',{
            'job_id':jid,'stale_claims':sorted(stale),'new_foci':[f['id'] for f in newly]})

    def rebuild_after_delta(self, jid: str):
        """A changed user goal or model boundary merits fresh independent search."""
        for obj in self.state['claims'].values():
            obj['state']='stale'
        for obj in self.state['unknowns'].values():
            obj['state']='stale'
        for obj in self.state.get('exploration_opportunities',{}).values():
            obj['state']='stale'
        self.state.update(generation=self.state['generation']+1,phase='discover',
            operations_done=0,repairs_done=0,entry_repairs_done=0,entry_round=0,
            schedule_round=0,delivery_cycle=0,foci=[],entry_reviews=[],entry_unresolved=False,
            sweep_complete=False,portfolio_complete=False,probe_portfolio=None,
            environment_questions_attempted=[], priority_rotation=0,
            intervention_frontier_done=False,action_preflight=None,system_map=None,goal_review=None,processed_delta_sources=[],
            load_bearing_audit=None,load_bearing_complete=False,load_bearing_round=0,
            pending_delta_sources=[],stop_reason='',budget_limited=False,draft=None,audit=None)
        for k in ('repair_issues','decisions','blind_job','entry_review','delivery_scope',
                  'adoption_relevant','completed_operators','blind_complete','focus_job',
                  'active_job_ids','last_error'):
            self.state.pop(k,None)
        self.mark_result(jid)
        self.save('major_delta_changed_system_goal_or_boundary_requires_new_raw_blind_search',{'assessment_job_id':jid})

    def verify_events(self):
        previous = ""
        for entry in self.state["events"]:
            actual = dict(entry)
            expected = actual.pop("event_hash")
            if actual["previous_hash"] != previous or digest(actual) != expected:
                raise StateDyneError("Event chain mismatch")
            previous = expected
        for source in self.state["sources"].values():
            if text_digest(source["text"]) != source["sha256"]:
                raise StateDyneError("Source identity mismatch")
        for jid in self.state["jobs"]:
            self.job_request(jid)
            self.result(jid)
