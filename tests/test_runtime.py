"""Deterministic software/protocol tests. NOT real model capability tests."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sd_runtime.common import StateDyneError, controller_lock, digest, loads, read_json, save_json, within
from sd_runtime.schemas import SCHEMAS, WORK, obj, I, validate
from sd_runtime.store import Workspace
from sd_runtime.backends import NativeBackend, OpenAIBackend, write_result
from sd_runtime.evidence import EvidenceTools, calculate
from sd_runtime.engine import Engine, instructions
from sd_runtime.evaluation import load_cases, blind_export, score_summary

TASK = "The system is slow only when two processes run together."


def claim(local="M1", kind="mechanism", deps=None, evidence=None):
    return {"local_id": local, "kind": kind, "statement": "A shared resource could serialize these processes.",
            "epistemic_status": "hypothesis", "mechanism": {"inputs": ["two requests"],
             "conditions": ["shared resource exists"], "transformation": "A request waits while another owns the resource.",
             "intermediate_states": ["waiting"], "outputs": ["greater latency"],
             "feedback": "No feedback is asserted.", "scope": "overlapping processes"},
            "evidence": evidence if evidence is not None else [{"source_id": "S1", "quote": TASK}],
            "depends_on": deps or [], "alternatives": ["external rate limiting"],
            "distinct_consequences": ["waiting time grows only during overlap"]}


def unknown(local="Q1", priority="important"):
    return {"local_id": local, "question": "Do the processes share a lock?", "why_it_matters": "It distinguishes waiting from independent compute load.",
            "origin": "model_discrimination", "route": "user", "priority": priority, "related_claims": []}


def work(claims=None, unknowns=None):
    return {"summary": "A conditional shared-resource candidate was constructed.",
            "claims": [claim()] if claims is None else claims, "unknowns": unknowns or [],
            "opportunities": [], "no_increment_reason": "" if claims != [] else "No additional mechanism is needed for this test-only repair."}


def draft_for(job):
    inputs = job["inputs"]
    claims = inputs.get("claims", [])
    qs = inputs.get("unknowns", [])
    answer = "Conditional analysis: investigate the shared-resource hypothesis, not a proven cause."
    # Fixture must not reintroduce the historic three-question ceiling.
    asked = (qs if inputs.get('user_input_policy','open')=='open' else [])
    question_groups=[]
    if asked:
        purpose='询问这些情况，是为了区别共享锁与外部限流是否产生不同的并发等待结果。'
        answer += "\n" + "\n".join(q["question"] for q in asked)
        question_groups=[{'group_id':'G1','unknown_ids':[q['id'] for q in asked],
                          'analytic_purpose':purpose,
                          'if_first':'如果确实共享锁，则优先检查串行等待机制。',
                          'if_second':'如果没有共享锁，则转向外部限流或竞争资源机制。',
                          'if_unknown':'如果用户没有这些数据，就保留两个候选并寻找系统记录。'}]
    foci = inputs.get("foci", [])
    resolution = "The overlap difference is conditionally accounted for by shared-resource serialization; alternative mechanisms remain possible."
    if foci: answer += "\n" + resolution
    # Only the requested stage is shown. A later actions turn can link to
    # points actually published in a PREVIOUS audited turn, not repeat them.
    scope=inputs.get('delivery_scope') or inputs.get('output_scope','analysis')
    recent = inputs.get('recent_turns',[])
    previously = {'point':set(),'action':set()}
    for past in recent:
        if past.get('release') and past.get('audit',{}).get('output',{}).get('verdict')=='pass':
            for u in (past.get('draft') or {}).get('output',{}).get('delivery_units',[]):
                if u['kind'] in previously:
                    previously[u['kind']].add(u['claim_id'])
    # Routing may pass through arbitrarily many side replies. The durable
    # audited ledger, not a short recent-turn cache, authorizes the next stage.
    for kind in previously:
        previously[kind].update(inputs.get('previously_delivered_interventions',{}).get(kind,[]))
    if scope == 'auto': scope='analysis'
    if scope == 'analysis': allowed=set()
    elif scope == 'points': allowed={'point'}
    elif scope == 'actions': allowed={'action'} if previously['point'] else {'point','action'}
    else: allowed={'plan'} if previously['action'] else {'action','plan'} if previously['point'] else {'point','action','plan'}
    selected=[c for c in claims if c['kind'] not in ('point','action','plan') or c['kind'] in allowed]
    units = []
    for c in sorted(selected, key=lambda c: {"point": 0, "action": 1, "plan": 2}.get(c["kind"], 3)):
        if c["kind"] in ("point", "action", "plan"):
            marker = {"point": "干预点", "action": "独立动作", "plan": "实施方案"}[c["kind"]]
            visible = f"{marker}: {c['statement']} ({c['id']})；改变资源等待的关系能影响本次并发延迟，实际仍需证据。"
            comparison = f"{marker}优先级/选择依据: 相对于不改变锁队列，此点值得检查，因为它直接关系并发等待；若根因是外部限流则会下调。({c['id']})."
            value = f"{marker}的独立收益：若此处的等待确实存在，调整它才有机会降低并发耗时，而不是只改写任务名称。({c['id']})"
            answer += "\n" + visible + "\n" + value + "\n" + comparison
            if c["kind"] == "plan":
                answer += "\n" + "本测试的组合顺序：先核实共享等待，再单独核验外部限制，避免两种动作争用同一窗口。"
                answer += "\n" + "组合方案的增益比较：只有两项约束确实并存时，组合才比只做其中一项有增益；否则保留单项更省成本。"
            units.append({"kind": c["kind"], "claim_id": c["id"], "visible_text": visible,
                          "comparison": comparison})
    map_goal=(inputs.get('system_map') or {}).get('goal_text','')
    if scope in ('points','actions','plan'):
        goal_line='本轮目标：'+(map_goal or '对系统并发延迟找到有效改变位置。')
        answer=goal_line+'\n'+answer
    else:
        goal_line=''
    receipts=inputs.get('latest_question_resolution', [])
    payoff={'covered_groups':[x['group_id'] for x in receipts], 'evidence_gained':'', 'still_unknown':'', 'answer_anchor':''}
    if receipts:
        payoff['evidence_gained']='这次材料仍然没有验证共享锁是发生拥堵的唯一原因。'
        payoff['still_unknown']='没有独立运行记录，尚无法排除外部限流。'
        payoff['answer_anchor']='并发时变慢还不能说明一定存在共享锁，也可能是外部限流；需要日志才能进一步区分。'
        answer+='\n'+payoff['answer_anchor']
    mode = inputs.get('interaction_mode', 'primary')
    prior_scope = (inputs.get('task_navigation') or {}).get('last_primary_scope')
    primary_scope = prior_scope if mode == 'side' and prior_scope else scope
    next_stage = {'analysis': 'points', 'points': 'actions', 'actions': 'plan', 'plan': 'none'}[primary_scope]
    next_offer = (f"接下来可以继续完成{next_stage}阶段，以刚才确认的关系作为依据。" if next_stage != 'none' else '')
    expansion_offer = '如果有新的关键事实，也可以继续扩大搜索检验原判断。' if next_stage != 'none' else ''
    visible_anchor = ' '.join(x for x in (next_offer, expansion_offer) if x)
    if inputs.get('task_thread',{}).get('status','active') in ('paused','closed'):
        next_offer=''; expansion_offer=''; visible_anchor=''
    if visible_anchor:
        answer += "\n" + visible_anchor
    nav = {'mode': mode, 'primary_stage': primary_scope, 'next_stage': next_stage,
           'next_offer': next_offer, 'expansion_offer': expansion_offer,
           'visible_anchor': visible_anchor,
           'reason': 'Scripted stage continuity based on the last verified primary deliverable, not a new diagnosis.'}
    draft = {"answer": answer, "goal_line":goal_line, "question_groups":question_groups,
             "pivotal_quantities": [], "objective_joins": [], "numeric_source_checks": [],
             "navigation": nav,
             "question_payoff":payoff,
            "delivery_units": units, "delivery_limit_reason": "",
            "focus_dispositions": [{"focus_id": f["id"], "status": "conditional", "linked_claim_ids": [c["id"] for c in claims[:1]],
                                    "visible_resolution": resolution, "rationale": "The proposed relation predicts latency under overlap, but not uniquely."} for f in foci],
            "status": "provisional" if inputs.get("budget_limited") else "needs_information" if qs else "complete",
            "claim_dispositions": [{"claim_id": c["id"], "treatment": "conditional" if c in selected else "not_selected", "reason": "Useful conditional process; not identified uniquely." if c in selected else "Previously delivered or beyond this turn's requested stage."} for c in claims],
            "information_dispositions": [{"unknown_id": q["id"], "treatment": "ask" if q in asked else "defer", "reason": "User-held evidence could distinguish models; the highest-priority questions are asked first.", "visible_question": q["question"] if q in asked else "", "evidence": [],
                                      "decision_effect": "changes_current_choice" if q in asked else "refines_only",
                                      "fallback_if_unknown": ""} for q in qs],
            "used_claim_ids": [c["id"] for c in selected]}
    if any(c["kind"] == "action" for c in selected):
        answer += "\n" + "本测试的无新增动作替代方案：先观察现有任务是否已能继续；若能则不额外增加程序。"
        draft["answer"] = answer
    if inputs.get('adoption_relevant') and scope in ('points','actions','plan'):
        draft['answer'] += "\n" + "本测试的采用关系：应先了解保护的利益和预期损失，再用可核验反馈判断新行为是否比旧行为更可信；不假定必须小步改变。"
    for q, disp in zip(qs, draft["information_dispositions"]):
        if disp["treatment"] != "addressed" and q["priority"] == "blocking" and disp["decision_effect"] == "refines_only":
            fallback = "Current decision remains conditional and does not require this additional unknown: " + q["id"]
            draft["answer"] += "\n" + fallback
            disp["fallback_if_unknown"] = fallback
    return draft


def regroup_questions(draft):
    """Only for legacy fixtures that explicitly alter ask/defer membership.

    This does not repair unknown or missing groups in the production runtime.
    """
    asked=[d['unknown_id'] for d in draft['information_dispositions'] if d['treatment']=='ask']
    draft['question_groups']=[]
    if asked:
        purpose='这几项信息帮助区分共享锁与外部流量限制，因为两者会改变下一步查证位置。'
        # Internal purpose stays in the fixture contract, not frontstage text.
        draft['question_groups']=[{'group_id':'G1','unknown_ids':asked,'analytic_purpose':purpose,
         'if_first':'如果确认只有并发时才变慢，就优先调查共享资源等待。',
         'if_second':'如果单任务也变慢，就优先调查独立负载或外部限制。',
         'if_unknown':'如果当前无法确认，就分别保留这两条不同的待验证解释。'}]
    return draft


def audit_for(job, revise=False):
    ids = [c["id"] for c in job["inputs"].get("claims", [])]
    draft = job["inputs"]["draft"]
    chosen = set(draft["used_claim_ids"])
    causal = [c for c in job["inputs"].get("claims", [])
              if c["id"] in chosen and c["kind"] in ("mechanism", "inference", "prediction", "point")]
    actions = [c["id"] for c in job["inputs"].get("claims", [])
               if c["id"] in chosen and c["kind"] == "action"]
    comparison = "本测试的无新增动作替代方案：先观察现有任务是否已能继续；若能则不额外增加程序。"
    return {"verdict": "revise" if revise else "pass",
            "causal_boundary_reviews": [{"claim_id": c["id"],
                 "contested_link": "The underlying shared-resource mechanism has not been directly established.",
                 "evidence_grade": "partial_indirect", "narrative_treatment": "explicitly_conditional",
                 "user_visible_limit": "Conditional analysis: investigate the shared-resource hypothesis, not a proven cause.",
                 "consequence_if_wrong": "An external limiting mechanism may need a different intervention."}
                 for c in causal],
            "point_value_reviews": [
                {"point_claim_id": u['claim_id'],
                 "intervention_location":"Contention on a shared resource could be changed.",
                 "causal_transmission":"Changing the lock/queue constraint could reduce the overlap wait.",
                 "incremental_value":"A causal timing reduction would address the requested outcome.",
                 "rank_reason":"Testing the shared wait gives clearer evidence than generic speed tuning.",
                 "strongest_competitor":"External limiting or doing nothing if tasks already run normally.",
                 "conditions_that_reorder":"Evidence of external rate limiting would reverse the priority.",
                 "combination_mode":"none_found", "companion_point_ids":[],
                 "joint_value":"Synthetic fixture does not establish a distinct joint effect.",
                 "action_feasibility_or_gap":"Synthetic fixture can only verify link integrity.",
                 "user_visible_leverage":u['visible_text'],
                 "user_visible_value":next(line for line in draft["answer"].splitlines() if line.startswith("干预点的独立收益：") and f"({u['claim_id']})" in line),
                 "user_visible_priority":u['comparison'],
                 "user_visible_combination":""}
                for u in draft.get('delivery_units',[]) if u['kind']=='point'],
            "plan_combination_reviews": [
                {"plan_claim_id":u["claim_id"],
                 "action_claim_ids":[aid for aid in next(c for c in job["inputs"].get("claims",[]) if c["id"]==u["claim_id"])["depends_on"]
                     if aid in {c["id"] for c in job["inputs"].get("claims",[]) if c["kind"]=="action"}],
                 "combination_mode":"combined" if len(next(c for c in job["inputs"].get("claims",[]) if c["id"]==u["claim_id"])["depends_on"]) >= 2 else "single_preferred",
                 "dependency_and_sequence":"Sequence separates resource contention work from external-limit checks.",
                 "gain_vs_best_single_or_no_action":"Joint effect arises only when both bottlenecks really contribute.",
                 "feasibility_or_failure_boundary":"If only one bottleneck is real, the extra action wastes effort.",
                 "user_visible_composition":"本测试的组合顺序：先核实共享等待，再单独核验外部限制，避免两种动作争用同一窗口。",
                 "user_visible_comparison":"组合方案的增益比较：只有两项约束确实并存时，组合才比只做其中一项有增益；否则保留单项更省成本。"}
                for u in draft.get("delivery_units",[]) if u["kind"]=="plan"],
            "change_adoption_review": {
                "status":"analysed" if job['inputs'].get('adoption_relevant') and (job['inputs'].get('delivery_scope') or job['inputs'].get('output_scope')) in ('points','actions','plan') else "not_relevant",
                "relevance_reason":"Adoption is material only when a real actor must change behavior; fixture otherwise omits it.",
                "protected_value_or_expected_loss":"Avoid losing continuity or operator flexibility.",
                "why_change_is_credible":"A comparable scenario could show the gain without assuming instant certainty.",
                "start_while_old_state_persists":"A new action can begin while the old interpretation remains; no cure is assumed.",
                "feedback_to_new_default":"Observe actual throughput and errors and update a future choice.",
                "pace_and_threshold_alternatives":"Some changes are incremental; some alter a threshold or incentive at once.",
                "user_visible_anchor":"本测试的采用关系：应先了解保护的利益和预期损失，再用可核验反馈判断新行为是否比旧行为更可信；不假定必须小步改变。" if job['inputs'].get('adoption_relevant') and (job['inputs'].get('delivery_scope') or job['inputs'].get('output_scope')) in ('points','actions','plan') else ""},
            "stage_boundary_review": {
                "delivered_scope":('analysis' if (job['inputs'].get('delivery_scope') or job['inputs'].get('output_scope','analysis'))=='auto' else (job['inputs'].get('delivery_scope') or job['inputs'].get('output_scope','analysis'))),
                "premature_future_content":False,
                "reason":"Fixture checks visible stage order and stage-specific content without semantic grading."},
            "strategy_challenge": {
                 "selected_action_claim_ids": actions,
                 "no_extra_action_alternative": "Continue without an additional new intervention.",
                 "distinct_gain": "Testing a targeted change may reduce latency.",
                 "added_burden": "A new procedure can consume operator attention.",
                 "overlap_or_monitoring_risk": "Repeated inspections may not add independent value.",
                 "when_alternative_wins": "When normal tasks already work and no new action is needed.",
                 "visible_comparison": comparison if actions else "",
                 "verdict": "conditional" if actions else "not_applicable"},
            "action_point_reviews": [
                 {"action_claim_id":u['claim_id'],
                  "point_claim_ids":[p for p in next(c for c in job['inputs'].get('claims',[])
                                                      if c['id']==u['claim_id'])['depends_on']
                                     if p in {c['id'] for c in job['inputs'].get('claims',[]) if c['kind']=='point'}],
                  "changed_relation_and_path":"Reducing the shared wait changes the selected causal point, conditional on a lock existing.",
                  "distinct_gain_vs_no_action":"Could reduce concurrent queue wait beyond continuing current operations.",
                  "strongest_competing_action":"Keep present workload while first identifying any external rate limit.",
                  "burden_and_failure_boundary":"Operator work can be wasted if the bottleneck is external.",
                  "user_visible_path":u['visible_text'],
                  "verdict":"conditional"}
                 for u in draft.get('delivery_units',[]) if u['kind']=='action'],
            "quantity_reviews":[], "objective_join_reviews":[],
            "objective_join_coverage_reason":"Fixture only uses one-condition timing claims and no adopted multi-condition outcomes.", "numeric_source_reviews":[],
            "source_fact_coverage_reason":"Fixture contains no source-anchored numeric conclusions.",
            "numeric_coverage_reason":"The scripted fixture contains no pivotal quantitative decision claim.",
            "issues": [{"issue_id": "I1", "severity": "blocking", "target_ids": ids[:1],
                        "finding": "The drafted sentence needs a sharper conditional distinction.",
                        "next_operator": "counterfactual", "repair_request": "Compare an external rate limit with a shared lock."}] if revise else [],
            "examined_claim_ids": ids,
            "examined_focus_ids": [f["id"] for f in job["inputs"].get("foci", [])],
            "examined_unknown_ids": [q["id"] for q in job["inputs"].get("unknowns", [])],
            "remaining_limits": ["Scripted fixture; no real semantic judgment occurred."]}


class FixtureBackend:
    kind = "fixture"
    def __init__(self, ws, *, revise_once=False, always_revise=False, with_unknown=False, schedule_op="finish", shared_refs=False, independence=True, reopen_first_pass=False):
        self.ws = ws
        self.revise_once, self.always_revise = revise_once, always_revise
        self.with_unknown, self.schedule_op = with_unknown, schedule_op
        self.shared_refs, self.independence = shared_refs, independence
        self.reopen_first_pass = reopen_first_pass
        self.requests = []

    def execute(self, job):
        cached = self.ws.result(job["id"])
        if cached:
            return cached
        self.requests.append(deepcopy(job))
        role = job["role"]
        if role == "frame":
            src = job["inputs"]["task_sources"][0]
            output = {"foci": [{"local_id": "F1", "evidence": [{"source_id":src["id"],"quote":src["text"]}],
                                   "observation": "The system is slow when two processes run concurrently.",
                                   "unexplained_difference": "The slowdown depends on concurrency, not just one process.",
                                   "why_material": "A shared bottleneck would change what intervention is useful.",
                                   "priority": "critical"}], "no_focus_reason": ""}
        elif role in ('system_map','system_reconcile'):
            from sd_runtime.schemas import SYSTEM_DIMENSIONS
            src=job['inputs']['task_sources'][0]
            covered=[]
            for dim in SYSTEM_DIMENSIONS:
                active=dim in ('goal','internal_process')
                covered.append({'dimension':dim,'state':'represented' if active else 'not_material',
                    'basis':'reported' if active else 'not_applicable',
                    'observed_or_hypothesized':('User seeks an explanation of the overlapping slowdown.' if active else ''),
                    'missing':'', 'why_material':('Describes user objective or core process.' if active else 'Not necessary to decide the causal test in this fixture.'),
                    'evidence':[{'source_id':src['id'],'quote':src['text']}] if active else [],
                    'route':'unavailable','priority':'optional'})
            output={'goal_text':'Explain why two overlapping processes slow down.',
                    'goal_basis':'inferred','goal_evidence':[{'source_id':src['id'],'quote':src['text']}],
                    'success_condition':'Find a verifiable process-level explanation for the slowdown.',
                    'protected_constraints':['Do not falsely assert a hidden lock exists.'],
                    'working_boundary':'Two simultaneous processes and any shared dependency.',
                    'boundary_reason':'The actual reported symptom depends on overlapping tasks.',
                    'coverage':covered,'links':[{'from_dimension':'goal','to_dimension':'internal_process',
                        'link':'The observed concurrency symptom defines what the internal hypothesis should explain.',
                        'kind':'observed_relation','evidence':[{'source_id':src['id'],'quote':src['text']}]}],
                    'whole_model_gap':'','no_material_gap_reason':'Scripted fixture: no additional high-impact system dimensions are established.'}
        elif role == 'goal_scout':
            src=job['inputs']['task_sources'][0]
            output={
                'current_target':'Explain the observed concurrency-specific slowdown.',
                'basis':'explicit', 'source_evidence':[{'source_id':src['id'],'quote':src['text']}],
                'observable_success':'A tested causal explanation predicts whether delays persist without overlap.',
                'valued_dimensions':[{'label':'time_to_response', 'content':'Reduce delays',
                   'basis':'inferred','evidence':[], 'distinct_from':'system_truth',
                   'loss_if_collapsed':'A fast response is not evidence that a causal diagnosis is correct.'},
                    {'label':'system_truth','content':'Find the true cause',
                     'basis':'inferred','evidence':[], 'distinct_from':'time_to_response',
                     'loss_if_collapsed':'A correct cause may be separate from immediate speed.'}],
                'alternatives':[], 'unresolved':[], 'gap_or_conflict':'',
                'adequate_existing_goal_reason':'The reported investigation objective is clear; no replacement goal is warranted.'}
        elif role == 'delta_assess':
            output={'impact':'local','reason':'The new observation refines the existing overlapping-process account.',
                    'affected_claim_ids':[], 'affected_unknown_ids':[],
                    'goal_or_boundary_changed':False,
                    'newly_relevant_difference':'A newly described timing observation merits a local update.',
                    'new_foci':[],
                    'question_results':[{'group_id':g['group_id'],'outcome':'unknown',
                         'evidence_change':'The new timing observation did not directly verify the alleged shared lock.',
                         'revised_judgment':'Both shared-lock and external-rate-limit mechanisms remain conditional.'}
                         for g in (job['inputs'].get('recent_turns') or [{}])[-1].get('draft',{}).get('output',{}).get('question_groups',[])]}
        elif role == "breakthrough_scout":
            output = work(claims=[])
            output['no_increment_reason'] = (
                'This scripted negative control tested a reversed outcome and an outside actor ' 
                'but found no independent differing prediction or observable route; it is not a live breakthrough test.')
        elif role == "scope_intent":
            latest=job['inputs']['task_sources'][-1]['text']
            output={'requested_scope':'analysis','request_basis':'missing',
                    'user_request_quote':'','reason':'No explicit intervention deliverable in this synthetic fixture.',
                    'protected_user_objective':latest}
        elif role == "value_frontier":
            output = work(claims=[])
            output['no_increment_reason'] = ('The independent synthetic fixture compared an outside-resource solution '
                    'with direct lock repair; it has no evidence for an additional change in user value or feasibility.')
        elif job["schema_name"] == "work":
            claims = [claim()]
            # A change job uses separate point and action artifacts.
            if role in ('change', 'change_forward', 'change_backward'):
                prior = self.ws.previously_delivered_interventions()
                active_scope = self.ws.state.get('delivery_scope') or self.ws.state['scope']
                if active_scope == 'actions' and prior['point']:
                    # The next turn changes HOW, not the already released WHERE.
                    claims = [claim('A1','action',[sorted(prior['point'])[0]])]
                elif active_scope == 'plan' and prior['action']:
                    claims = [claim('L1','plan',[sorted(prior['action'])[0]])]
                else:
                    claims = [claim('P1','point'),claim('A1','action',['P1'])]
                    if active_scope == 'plan':
                        claims.append(claim('L1','plan',['A1']))
            source = job["inputs"]["task_sources"][0]
            for c in claims:
                c["evidence"] = [{"source_id": source["id"], "quote": source["text"]}]
            qs = [unknown(priority="blocking")] if self.with_unknown else []
            output = work(claims, qs)
            # Negative-control fixture deliberately repeats the same hypothesis
            # across independent workers. Label that null increment explicitly;
            # it is NOT evidence that real autonomous discovery succeeded.
            if role in ('reframe', 'contrast_probe', 'environment_scout', 'selection_scout', 'relation_scout', 'blind_challenge'):
                output['no_increment_reason'] = (
                    'Scripted fixture: this role offered no new mechanism, question, '
                    'prediction or opportunity beyond the shared-resource baseline.')
        elif role == "change_action_probe":
            # Backstage action feasibility from real point IDs, not a second
            # catalogue of points. The points-stage draft must NOT show it.
            points = sorted(cid for cid, c in self.ws.active_claims().items()
                            if c['kind'] == 'point')
            if points:
                a = claim('PREVIEW_A1', 'action', [points[0]])
                source = job['inputs']['task_sources'][0]
                a['evidence'] = [{'source_id': source['id'], 'quote': source['text']}]
                output = work(claims=[a])
            else:
                output = work(claims=[])
                output['no_increment_reason'] = 'No grounded point can be tested yet in this scripted negative control.'
        elif role == "change_portfolio":
            # No constructed synergy in this generic negative control. This
            # role must still run; absence of a joint gain is a valid result.
            output = work(claims=[])
            output['no_increment_reason'] = ('Independent combination search compared present constraints '
                                             'and found no demonstrably stronger joint point in this synthetic example.')
        elif role == "turn_router":
            latest=job['inputs']['new_user_turn']['text']
            mode='side' if 'side:' in latest.casefold() or '不想' in latest else ('next' if latest.strip()=='下一步' else 'main_update')
            output={'route':mode,'quoted_trigger':latest.strip(),'reason':'Synthetic routed follow-up preserves the preceding primary goal.',
                'preserves_primary_goal':True,'user_declines_more_questions':'不想' in latest,
                'user_invites_questions':False,'expansion_focus':'',
                'no_new_information_route':'Continue with the previously reviewed conditional evidence and other feasible paths.'}
        elif role == "probe_portfolio":
            output = {"covered_representation": "Tested local locking against an independent external queue and other as-yet unobserved processes.",
                      "probes": [],
                      "exploration_attempts": [{"local_id":"S1","focus":"outside_current_model",
                       "incumbent_limit":"Local shared-lock explanation does not cover external infrastructure.",
                       "alternative_representation":"An upstream service might serialize unrelated jobs.",
                       "distinct_prediction":"","rival_prediction":"","evidence_route":"materials",
                       "outcome":"null_after_search","probe_local_ids":[],
                       "reason":"Synthetic null search: tried an external-queue account, but no new causal evidence is available in the fixture."}],
                      "null_search_reason": "This deterministic fixture supplies no real model-side new discovery; it cannot serve as a capability result."}
        elif role == "load_bearing":
            claims=job['inputs'].get('claims',[])
            output={
                'thesis_at_risk':'The overlap effect might be a shared lock or external queue.',
                'as_of_scope':'No dated cutoff is present in this synthetic test.',
                'as_of_handling':'No temporal claims are used in the fixture.',
                'examined_claim_ids':[c['id'] for c in claims],
                'tests':[{'local_id':'T1','claim_ids':[claims[0]['id']] if claims else [],
                    'proposition':'Shared locking is only one potential mechanism.',
                    'role':'causal_bridge','support':'conditional','evidence':[],
                    'importance':'important','hidden_premise':'A shared lock exists.',
                    'strongest_rival':'External queue serialization alone can cause overlap delay.',
                    'differentiated_outcome':'Latency remains despite bypassing the local lock.',
                    'decisive_test':'Compare external wait and local-lock ownership across overlap.',
                    'route':'materials','disposition':'retain',
                    'reason':'There is no direct lock/queue observation; no claimed verification.',
                    'quantified_incremental_claim':False}],
                'recalculations':[], 'robustness_checks':[], 'net_effect_checks':[],
                'best_countermodel':'A rate-limited external queue can mimic local lock contention.',
                'decision_reversal':'Independent external waits would reverse local-lock intervention.',
                'discovery_limit':'This fixture does not possess real process traces.'}
        elif role == "entry_review":
            reopened = self.reopen_first_pass and not job["inputs"].get("previous_gate_reviews")
            candidates = job["inputs"]["claims"]
            if job["inputs"].get("previous_gate_reviews"):
                repaired_candidates = [c for c in candidates if c["origin_job"] in
                                       {r["job_id"] for r in job["inputs"]["work_results"]
                                        if r["job_id"] in self.ws.state['jobs'] and
                                        self.ws.job_request(r['job_id'])['role'] == 'entry_repair'}]
                candidates = repaired_candidates or candidates
            world=job['inputs'].get('system_map') or {}
            open_system=[x for x in world.get('coverage',[]) if x['state']=='open' and x['priority'] in ('blocking','important')]
            output = {"system_coverage_dispositions":[{'dimension':x['dimension'],
                       'resolution':'search','rationale':'The missing interface can change the causal finding.',
                       'evidence_or_next_action':x['missing']} for x in open_system],
                      "search_space_assessment": {
                         "judgment": "no_new_space_after_search", "candidate_claim_ids": [],
                         "prior_representation_limit": "Local shared-lock explanation does not exhaust concurrency alternatives.",
                         "tested_alternative_representation": "A separate independent queue was tested conceptually, but this synthetic fixture offered no distinct evidence.",
                         "unreported_outcome": "", "discriminating_observation": "",
                         "comparison_reason": "Scripted independent scouts repeated the same hypothesis and recorded a justified null discovery."},
                      "verdict": "reopen" if reopened else "pass", "new_foci": [],
                      "coverage": [{"focus_id": f["id"], "status": "partial" if reopened else "explained",
                                    "candidate_claim_ids": [c["id"] for c in candidates[:1]],
                                    "missing_or_explained_bridge": "Shared ownership delays the second overlapping request.",
                                    "unreported_prediction": "If the shared lock is bypassed, overlap latency would fall.",
                                    "discriminator": "Compare response times with and without the shared lock.",
                                    "reason": "The overlap is predicted conditionally by shared serialization."}
                                   for f in job["inputs"].get("foci", [])],
                      "examined_contrasts": ["Only when two processes overlap do response times grow."],
                      "missing_relation": "A plausible separate mechanism may generate the overlap effect." if reopened else "",
                      "why_material": "An unseen dependency could reverse the proposed resolution." if reopened else "",
                      "next_operator": "reframe",
                      "required_new_prediction_or_test": "Predict an outcome if the shared lock is removed." if reopened else "",
                      "no_gap_reason": "All major raw contrasts have distinct conditional candidates in this fixture." if not reopened else ""}
        elif role == "schedule":
            scope = job["inputs"]["output_scope"]
            output = {"decisions": [] if self.schedule_op == "finish" else [
                      {"operator": self.schedule_op, "target_ids": [], "opportunity_ids": [],
                       "rationale": "Current scope is supportable.",
                       "expected_difference": "Explore the remaining distinct mechanism.",
                       "strongest_alternative": "Ask for external observations when needed.",
                       "why_parallel_safe": ""}],
                      "finish": self.schedule_op == "finish",
                      "finish_reason": "No higher-value work remains in fixture" if self.schedule_op == "finish" else "",
                      "delivery_scope": "analysis" if scope == "auto" else scope,
                      "adoption_relevant": False, "scope_reason": "Follows the requested scope."}
        elif role == "decision_tournament":
            # A negative-control fixture cannot certify semantic innovation.
            # It compares alternatives and records a real NULL result without
            # pretending scripted results are independent model discoveries.
            output = {
                'goal_at_stake':"Explain the user's concurrency slowdown.",
                'comparison_basis':'Distinguish actual process bottlenecks using different observable outcomes.',
                'entries':[], 'biggest_reversal_condition':'A traced external bottleneck would change the mechanism.',
                'no_independent_value_reason':'The scripted workers repeated a local-lock candidate and did not supply an independently evidenced, meaningfully different outcome family. This negative control asserts no novelty.',
                'research_opening':{'needed':False,'focus':'','expected_difference':'','evidence_route':'unavailable'}}
        elif role == "compose":
            output = draft_for(job)
        elif role == "audit":
            is_first = job["tag"].endswith("review-0")
            output = audit_for(job, self.always_revise or (self.revise_once and is_first))
        else:
            raise AssertionError(role)
        return write_result(self.ws.root, job, output, kind="fixture",
                            worker_ref="same-ref" if self.shared_refs else f"fixture-{job['id']}",
                            actual_model="scripted-fixture-not-a-model", independent_context=self.independence)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def workspace(self, **kwargs):
        return Workspace.create(self.root / "run", TASK, **kwargs)
    def make_job(self, ws, role="discovery", schema="work", inputs=None):
        return ws.get_job(role, role, schema, inputs or ws.raw_view(), instructions(role))
    def receive(self, ws, job, output, **kwargs):
        return write_result(ws.root, job, output, kind="fixture", worker_ref=f"fixture-{job['id']}", actual_model="fixture", **kwargs)


class JsonAndToolsTests(Base):
    def test_reject_duplicate_json_keys(self):
        with self.assertRaises(StateDyneError): loads('{"x":1,"x":2}')
    def test_reject_nonfinite_json(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token), self.assertRaises(StateDyneError): loads('{"x":'+token+'}')
    def test_reject_schema_extra_fields(self):
        with self.assertRaises(StateDyneError): validate({"x": 1, "y": 2}, obj(x=I))
    def test_bool_is_not_integer(self):
        with self.assertRaises(StateDyneError): validate({"x": True}, obj(x=I))
    def test_lock_is_exclusive(self):
        with controller_lock(self.root):
            with self.assertRaises(StateDyneError):
                with controller_lock(self.root): pass
        self.assertFalse((self.root / ".controller.lock").exists())
    def test_path_escape_blocked(self):
        with self.assertRaises(StateDyneError): within(self.root, "../secret.txt")
    def test_arithmetic_is_real(self): self.assertEqual(calculate("(7 + 3) / 2")["result"], 5)
    def test_arithmetic_no_code_execution(self):
        for expr in ("__import__('os').system('whoami')", "[x for x in range(3)]", "True", "10**100000", "1/0", "(-1)**0.5"):
            with self.subTest(expr=expr), self.assertRaises(StateDyneError): calculate(expr)
    def test_only_registered_materials(self):
        ws = self.workspace()
        tools = EvidenceTools(ws.state["sources"])
        self.assertIn("error", tools.call("read_material", {"source_id": "../../secret", "start": 0, "length": 20}))
        self.assertIn("error", tools.call("shell", {"command": "whoami"}))
    def test_read_records_actual_passage(self):
        ws = self.workspace()
        tools = EvidenceTools(ws.state["sources"])
        result = tools.call("read_material", {"source_id": "S1", "start": 0, "length": 10})
        self.assertTrue(result["truncated"])
        self.assertEqual(tools.seen["S1"], [TASK[:10]])
    def test_search_is_explicitly_literal(self):
        ws = self.workspace()
        result = EvidenceTools(ws.state["sources"]).call("search_materials", {"query": "SLOW"})
        self.assertEqual(result["search_type"], "literal_local")
        self.assertEqual(result["matches"][0]["source_id"], "S1")
    def test_superseded_material_not_readable(self):
        ws = self.workspace()
        ws.state["sources"]["S1"]["active"] = False
        result = EvidenceTools(ws.state["sources"]).call("read_material", {"source_id": "S1", "start": 0, "length": 20})
        self.assertIn("error", result)


class WorkspaceTests(Base):
    def test_empty_existing_directory_allowed_but_data_not_overwritten(self):
        self.workspace()
        with self.assertRaises(StateDyneError): self.workspace()
    def test_blind_inputs_have_no_candidates(self):
        ws = self.workspace()
        job = self.make_job(ws)
        self.receive(ws, job, work()); ws.merge_work(job["id"])
        raw = ws.raw_view()
        self.assertNotIn("claims", raw)
        self.assertNotIn("unknowns", raw)
        self.assertNotIn("shared resource could", json.dumps(raw))
    def test_independent_candidates_admitted_without_veto(self):
        ws = self.workspace()
        jobs = [self.make_job(ws, "discovery"), self.make_job(ws, "reframe"), self.make_job(ws, "contrast_probe")]
        for job in jobs:
            output = work(); output["claims"][0]["statement"] = f"Competing mechanism from {job['role']}"
            self.receive(ws, job, output); ws.merge_work(job["id"])
        self.assertEqual(len(ws.active_claims()), 3)
        self.assertEqual(len(ws.state["work_results"]), 3)
    def test_complete_products_retained(self):
        ws = self.workspace(); job = self.make_job(ws)
        output = work(); output["opportunities"] = ["Important opportunity beyond the initial model"]
        self.receive(ws, job, output); ws.merge_work(job["id"])
        self.assertEqual(ws.result(job["id"])["output"], output)
        self.assertEqual(ws.state["work_results"][0]["opportunities"], output["opportunities"])
    def test_duplicate_merge_is_idempotent(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work()); ws.merge_work(job["id"]); ws.merge_work(job["id"])
        self.assertEqual(len(ws.active_claims()), 1)
    def test_unknown_does_not_become_negative_fact(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work(unknowns=[unknown()])); ws.merge_work(job["id"])
        self.assertEqual(next(iter(ws.state["unknowns"].values()))["state"], "open")
    def test_fabricated_quote_rejected_atomically(self):
        ws = self.workspace(); job = self.make_job(ws)
        good, bad = claim("M1"), claim("M2", evidence=[{"source_id": "S1", "quote": "fabricated observation"}])
        self.receive(ws, job, work([good, bad]))
        with self.assertRaises(StateDyneError): ws.merge_work(job["id"])
        self.assertEqual(ws.active_claims(), {})
    def test_unread_material_citation_rejected(self):
        ws = self.workspace(materials=[("notes", "Unique unseen material.")]); job = self.make_job(ws)
        output = work([claim(evidence=[{"source_id": "S2", "quote": "Unique unseen material."}])])
        self.receive(ws, job, output)
        with self.assertRaises(StateDyneError): ws.merge_work(job["id"])
    def test_actually_read_material_citation_accepted(self):
        ws = self.workspace(materials=[("notes", "Unique unseen material.")]); job = self.make_job(ws)
        output = work([claim(evidence=[{"source_id": "S2", "quote": "Unique unseen material."}])])
        self.receive(ws, job, output, exposed={"S2": ["Unique unseen material."]}); ws.merge_work(job["id"])
        self.assertEqual(len(ws.active_claims()), 1)
    def test_circular_justification_rejected(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work([claim("M1", deps=["M2"]), claim("M2", deps=["M1"])]))
        with self.assertRaises(StateDyneError): ws.merge_work(job["id"])
    def test_real_temporal_feedback_is_allowed(self):
        ws = self.workspace(); job = self.make_job(ws)
        output = work(); output["claims"][0]["mechanism"]["feedback"] = "Output at time t changes state at t+1."
        self.receive(ws, job, output); ws.merge_work(job["id"])
        self.assertEqual(len(ws.active_claims()), 1)
    def test_action_must_map_to_point(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work([claim("A1", "action")]))
        with self.assertRaises(StateDyneError): ws.merge_work(job["id"])
    def test_action_point_many_to_many_allowed(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work([claim("P1", "point"), claim("P2", "point"), claim("A1", "action", ["P1", "P2"])]))
        ws.merge_work(job["id"])
        self.assertEqual(len(ws.active_claims()), 3)
    def test_correction_invalidates_declared_downstream(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work([claim("M1"), claim("M2", deps=["M1"], evidence=[])])); ws.merge_work(job["id"])
        ws.update("The original observation was incorrect.", supersedes="S1")
        self.assertFalse(ws.active_claims())
        self.assertTrue(all(c["state"] == "stale" for c in ws.state["claims"].values()))
        self.assertEqual(ws.state["phase"], "discover")
    def test_append_reopens_space_without_deleting_valid_candidates(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work()); ws.merge_work(job["id"])
        ws.update("There is also a different symptom.")
        self.assertEqual(len(ws.active_claims()), 1)
        self.assertEqual(ws.state["generation"], 2)
    def test_source_precision_is_not_invented(self):
        ws = self.workspace()
        sid = ws.add_source("imprecise time", "around the middle of a month", kind="user_reported", precision="month_part")
        self.assertEqual(ws.state["sources"][sid]["precision"], "month_part")
        self.assertNotIn("date", ws.state["sources"][sid])
    def test_unknown_dependency_rejected(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work([claim(deps=["J9999:missing"])]))
        with self.assertRaises(StateDyneError): ws.merge_work(job["id"])
    def test_empty_label_is_not_a_transformation(self):
        ws = self.workspace(); job = self.make_job(ws)
        output = work(); output["claims"][0]["mechanism"]["transformation"] = ""
        self.receive(ws, job, output)
        with self.assertRaises(StateDyneError): ws.merge_work(job["id"])
    def test_tampered_result_rejected(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work())
        path = ws.root / "jobs" / job["id"] / "result.json"
        record = read_json(path); record["output"]["summary"] = "tampered"; save_json(path, record)
        with self.assertRaises(StateDyneError): ws.result(job["id"])
    def test_tampered_request_rejected(self):
        ws = self.workspace(); job = self.make_job(ws)
        path = ws.root / "jobs" / job["id"] / "request.json"
        data = read_json(path); data["inputs"]["claims"] = ["leak"]; save_json(path, data)
        with self.assertRaises(StateDyneError): ws.job_request(job["id"])
    def test_event_chain_detects_edit(self):
        ws = self.workspace(); ws.verify_events()
        ws.state["events"][0]["detail"] = "tampered"
        with self.assertRaises(StateDyneError): ws.verify_events()


class EngineTests(Base):
    def test_unexecuted_native_jobs_pause_without_success(self):
        ws = self.workspace(); engine = Engine(ws, NativeBackend(ws.root, ws.state["sources"], ws.state["config"]))
        result = engine.advance()
        self.assertEqual(result["status"], "waiting_for_real_workers")
        self.assertEqual(len(result["jobs"]), 10)
        self.assertFalse((ws.root / "answer.md").exists())
        self.assertFalse((ws.root / "release.json").exists())
    def test_pending_resume_does_not_create_extra_jobs(self):
        ws = self.workspace(); engine = Engine(ws, NativeBackend(ws.root, ws.state["sources"], ws.state["config"]))
        engine.advance(); engine.advance()
        self.assertEqual(len(ws.state["jobs"]), 10)
    def test_simulated_end_to_end_is_not_capability_success(self):
        ws = self.workspace(backend="fixture"); provider = FixtureBackend(ws)
        result = Engine(ws, provider).advance()
        self.assertEqual(result["assurance"], "simulation_only")
        self.assertFalse(result["capability_evaluation_passed"])
        self.assertTrue((ws.root / "simulation-answer.md").exists())
        self.assertFalse((ws.root / "answer.md").exists())
        self.assertEqual(len(provider.requests), 23)
        self.assertIn("breakthrough_scout", {j["role"] for j in provider.requests})
        self.assertEqual(sum(j["role"] == "value_frontier" for j in provider.requests), 1)
        Engine(ws, provider).verify_release()
    def test_exact_draft_is_reaudited_after_targeted_repair(self):
        ws = self.workspace(backend="fixture"); provider = FixtureBackend(ws, revise_once=True)
        Engine(ws, provider).advance()
        roles = [r["role"] for r in provider.requests]
        self.assertEqual(roles.count("audit"), 2)
        self.assertEqual(roles.count("compose"), 2)
        self.assertEqual(roles.count("repair"), 1)
        self.assertEqual(ws.state["repairs_done"], 1)
        self.assertIn("review-1", ws.job_request(ws.state["audit"]["job_id"])["tag"])
    def test_failing_review_never_publishes(self):
        ws = self.workspace(backend="fixture", config={"max_repairs": 0}); provider = FixtureBackend(ws, always_revise=True)
        result = Engine(ws, provider).advance()
        self.assertEqual(result["status"], "blocked")
        self.assertFalse((ws.root / "answer.md").exists())
        self.assertFalse((ws.root / "simulation-answer.md").exists())
        self.assertTrue((ws.root / "draft-only.md").exists())
    def test_operation_budget_is_not_semantic_completion(self):
        ws = self.workspace(backend="fixture", config={"max_operations": 0}); provider = FixtureBackend(ws)
        result = Engine(ws, provider).advance()
        self.assertEqual(result["status"], "provisional")
        self.assertEqual(result["stop_reason"], "exploration_budget_exhausted")
    def test_model_requesting_endless_work_hits_budget(self):
        ws = self.workspace(backend="fixture", config={"max_operations": 2}); provider = FixtureBackend(ws, schedule_op="deepen")
        result = Engine(ws, provider).advance()
        self.assertEqual(ws.state["operations_done"], 2)
        self.assertEqual(result["status"], "provisional")
    def test_declared_blocking_questions_are_visible(self):
        ws = self.workspace(backend="fixture"); provider = FixtureBackend(ws, with_unknown=True)
        result = Engine(ws, provider).advance()
        self.assertEqual(result["status"], "needs_information")
        self.assertIn("Do the processes share a lock?", (ws.root / "simulation-answer.md").read_text())
    def test_change_scope_forces_actual_change_work(self):
        ws = self.workspace(backend="fixture", scope="actions"); provider = FixtureBackend(ws)
        Engine(ws, provider).advance()
        self.assertTrue({"change_forward", "change_backward"}.issubset({r["role"] for r in provider.requests}))
        self.assertTrue(any(c["kind"] == "action" for c in ws.active_claims().values()))
    def test_reused_worker_reference_blocks_release(self):
        ws = self.workspace(backend="fixture"); provider = FixtureBackend(ws, shared_refs=True)
        with self.assertRaises(StateDyneError): Engine(ws, provider).advance()
        self.assertFalse((ws.root / "release.json").exists())
    def test_non_independent_receipt_blocks_release(self):
        ws = self.workspace(backend="fixture"); provider = FixtureBackend(ws, independence=False)
        with self.assertRaises(StateDyneError): Engine(ws, provider).advance()
    def test_final_answer_tamper_detected(self):
        ws = self.workspace(backend="fixture"); engine = Engine(ws, FixtureBackend(ws))
        engine.advance(); (ws.root / "simulation-answer.md").write_text("changed")
        with self.assertRaises(StateDyneError): engine.verify_release()
    def test_feedback_removes_old_release(self):
        ws = self.workspace(backend="fixture"); Engine(ws, FixtureBackend(ws)).advance()
        ws.update("Additional new observation.")
        self.assertFalse((ws.root / "release.json").exists())
        self.assertFalse((ws.root / "simulation-answer.md").exists())
        self.assertIsNone(ws.state["audit"])
    def test_native_hash_mismatch_rejected(self):
        ws = self.workspace(); job = self.make_job(ws)
        provider = NativeBackend(ws.root, ws.state["sources"], ws.state["config"])
        with self.assertRaises(StateDyneError): provider.submit(job, work(), input_sha="bad", worker_ref="host-call", actual_model="host model", independent_context=True)
    def test_native_submission_is_attestation_not_proof(self):
        ws = self.workspace(); job = self.make_job(ws)
        provider = NativeBackend(ws.root, ws.state["sources"], ws.state["config"])
        result = provider.submit(job, work(), input_sha=job["input_sha256"], worker_ref="host-call", actual_model="host model", independent_context=True)
        self.assertEqual(result["backend_kind"], "native_attested")
    def test_native_result_cannot_be_overwritten(self):
        ws = self.workspace(); job = self.make_job(ws)
        provider = NativeBackend(ws.root, ws.state["sources"], ws.state["config"])
        kwargs = dict(input_sha=job["input_sha256"], worker_ref="host-call", actual_model="host model", independent_context=True)
        provider.submit(job, work(), **kwargs)
        with self.assertRaises(StateDyneError): provider.submit(job, work(), **kwargs)
    def test_native_tool_records_actual_exposure(self):
        ws = self.workspace(materials=[("notes", "visible passage")]); job = self.make_job(ws)
        provider = NativeBackend(ws.root, ws.state["sources"], ws.state["config"])
        provider.tool(job, "read_material", {"source_id": "S2", "start": 0, "length": 20})
        product = work([claim(evidence=[{"source_id": "S2", "quote": "visible passage"}])])
        provider.submit(job, product, input_sha=job["input_sha256"], worker_ref="host-call", actual_model="host model", independent_context=True)
        ws.merge_work(job["id"])
        self.assertEqual(len(ws.active_claims()), 1)


class DraftGateTests(Base):
    def draft_job(self, with_unknown=False):
        ws = self.workspace()
        j = self.make_job(ws); self.receive(ws, j, work(unknowns=[unknown(priority="blocking")] if with_unknown else [])); ws.merge_work(j["id"])
        d = self.make_job(ws, "compose", "draft", ws.current_view())
        return ws, d, draft_for(d)
    def test_silent_candidate_drop_rejected(self):
        ws, job, output = self.draft_job(); output["claim_dispositions"] = []
        self.receive(ws, job, output)
        with self.assertRaises(StateDyneError): ws.set_draft(job["id"])
    def test_silent_unknown_drop_rejected(self):
        ws, job, output = self.draft_job(True); output["information_dispositions"] = []
        self.receive(ws, job, output)
        with self.assertRaises(StateDyneError): ws.set_draft(job["id"])
    def test_asked_but_not_visible_rejected(self):
        ws, job, output = self.draft_job(True); output["answer"] = "No question was actually asked."
        self.receive(ws, job, output)
        with self.assertRaises(StateDyneError): ws.set_draft(job["id"])
    def test_addressed_without_source_rejected(self):
        ws, job, output = self.draft_job(True); output["information_dispositions"][0]["treatment"] = "addressed"
        self.receive(ws, job, output)
        with self.assertRaises(StateDyneError): ws.set_draft(job["id"])
    def test_unresolved_blocker_cannot_claim_complete(self):
        ws, job, output = self.draft_job(True); output["status"] = "complete"
        self.receive(ws, job, output)
        with self.assertRaises(StateDyneError): ws.set_draft(job["id"])
    def test_used_disposition_mismatch_rejected(self):
        ws, job, output = self.draft_job(); output["used_claim_ids"] = []
        self.receive(ws, job, output)
        with self.assertRaises(StateDyneError): ws.set_draft(job["id"])
    def test_blocking_issue_cannot_be_pass(self):
        ws, job, output = self.draft_job(); self.receive(ws, job, output); ws.set_draft(job["id"])
        inputs = ws.current_view(); inputs["draft_sha256"] = ws.state["draft"]["sha256"]; inputs["draft"] = ws.state["draft"]["output"]
        a = self.make_job(ws, "audit", "audit", inputs); audit = audit_for(a, True); audit["verdict"] = "pass"
        self.receive(ws, a, audit)
        with self.assertRaises(StateDyneError): ws.set_audit(a["id"])
    def test_stale_draft_audit_rejected(self):
        ws, job, output = self.draft_job(); self.receive(ws, job, output); ws.set_draft(job["id"])
        inputs = ws.current_view(); inputs["draft_sha256"] = "different-draft"; inputs["draft"] = ws.state["draft"]["output"]
        a = self.make_job(ws, "audit", "audit", inputs); self.receive(ws, a, audit_for(a))
        with self.assertRaises(StateDyneError): ws.set_audit(a["id"])


class ApiTransportTests(Base):
    def setup_api(self, transport, config=None):
        ws = self.workspace(backend="openai", model="explicit-test-id", config={"allow_remote": True, **(config or {})})
        return ws, OpenAIBackend(ws.root, ws.state["sources"], ws.state["config"], transport=transport, sleeper=lambda _: None)
    def response(self, product=None, **kwargs):
        return {"id": "resp-fixture-1", "status": "completed", "model": "test-model-id",
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
                "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(product or work())}]}], **kwargs}
    def test_no_credentials_no_call(self):
        ws = self.workspace(config={"allow_remote": True})
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(StateDyneError): OpenAIBackend(ws.root, ws.state["sources"], ws.state["config"])
    def test_no_consent_no_call(self):
        ws = self.workspace()
        with self.assertRaises(StateDyneError): OpenAIBackend(ws.root, ws.state["sources"], ws.state["config"], transport=lambda *_: None)
    def test_actual_transport_format_and_model_recorded(self):
        seen = []
        def call(payload, key, timeout):
            seen.append(deepcopy(payload)); return self.response()
        ws, provider = self.setup_api(call); job = self.make_job(ws)
        result = provider.execute(job)
        self.assertEqual(seen[0]["model"], "explicit-test-id")
        self.assertFalse(seen[0]["store"])
        self.assertTrue(seen[0]["text"]["format"]["strict"])
        self.assertNotIn("previous_response_id", seen[0])
        self.assertEqual(result["actual_model"], "test-model-id")
        self.assertEqual(result["backend_kind"], "fixture")
        self.assertEqual(result["usage"]["total_tokens"], 30)
    def test_tool_loop_executes_and_preserves_protocol_not_private_log(self):
        seen=[]
        def call(payload, key, timeout):
            seen.append(deepcopy(payload))
            if len(seen)==1:
                return self.response(id="resp-first", **{"output":[
                    {"type":"reasoning","id":"opaque-reasoning","encrypted_content":"OPAQUE_PRIVATE_ITEM"},
                    {"type":"function_call","name":"read_material","call_id":"call-read","arguments":json.dumps({"source_id":"S1","start":0,"length":500})}]})
            return self.response(id="resp-second")
        ws, provider=self.setup_api(call); job=self.make_job(ws); result=provider.execute(job)
        self.assertIn(TASK,result["exposed_passages"]["S1"])
        self.assertEqual(seen[1]["input"][-1]["type"],"function_call_output")
        self.assertTrue(any(x.get("type")=="reasoning" for x in seen[1]["input"]))
        self.assertNotIn("OPAQUE_PRIVATE_ITEM",(ws.root/'jobs'/job['id']/'transport.json').read_text())
        self.assertEqual(result["usage"]["total_tokens"],60)
    def test_incomplete_output_is_not_accepted(self):
        ws,p=self.setup_api(lambda *_:self.response(status="incomplete")); job=self.make_job(ws)
        with self.assertRaises(StateDyneError): p.execute(job)
        self.assertIsNone(ws.result(job["id"]))
        self.assertTrue((ws.root/'jobs'/job['id']/'failure.json').exists())
    def test_refusal_is_not_replaced(self):
        ws,p=self.setup_api(lambda *_:self.response(**{"output":[{"type":"message","content":[{"type":"refusal","refusal":"declined"}]}]}));job=self.make_job(ws)
        with self.assertRaises(StateDyneError):p.execute(job)
    def test_invalid_json_is_preserved_not_repaired_silently(self):
        ws,p=self.setup_api(lambda *_:self.response(**{"output":[{"type":"message","content":[{"type":"output_text","text":"not-json"}]}]}));job=self.make_job(ws)
        with self.assertRaises(StateDyneError):p.execute(job)
        self.assertEqual((ws.root/'jobs'/job['id']/'raw-output.txt').read_text(),"not-json")
    def test_429_retry_is_counted(self):
        count=[]
        def call(*_):
            count.append(1)
            if len(count)==1:raise HTTPError("https://api.openai.com",429,"rate limit",{},None)
            return self.response()
        ws,p=self.setup_api(call);p.execute(self.make_job(ws))
        self.assertEqual(read_json(ws.root/'api-ledger.json')["requests_attempted"],2)
    def test_auth_failure_not_retried_or_substituted(self):
        count=[]
        def call(*_):count.append(1);raise HTTPError("https://api.openai.com",401,"auth",{},None)
        ws,p=self.setup_api(call)
        with self.assertRaises(StateDyneError):p.execute(self.make_job(ws))
        self.assertEqual(len(count),1)
    def test_unknown_delivery_network_error_not_automatically_retried(self):
        count=[]
        def call(*_):count.append(1);raise URLError("timeout")
        ws,p=self.setup_api(call)
        with self.assertRaises(StateDyneError):p.execute(self.make_job(ws))
        self.assertEqual(len(count),1)
    def test_api_budget_blocks_extra_request(self):
        ws,p=self.setup_api(lambda *_:self.response(),{"max_api_requests":1})
        p.execute(self.make_job(ws,"discovery"))
        with self.assertRaises(StateDyneError):p.execute(self.make_job(ws,"reframe"))
    def test_sibling_model_contexts_do_not_share_messages(self):
        seen=[]
        def call(payload,*_):seen.append(deepcopy(payload));return self.response(id=f"resp-{len(seen)}")
        ws,p=self.setup_api(call)
        for role in ("discovery","reframe", "contrast_probe"):
            p.execute(self.make_job(ws,role))
        self.assertTrue(all(len(x["input"]) == 1 for x in seen))
        self.assertEqual(seen[0]["input"],seen[1]["input"])
        self.assertEqual(seen[0]["input"],seen[2]["input"])


class EvaluationTests(Base):
    def test_rubric_cannot_enter_solver_case_schema(self):
        p=self.root/'cases.json';save_json(p,[{"id":"x","task":"task","materials":[],"expected_answer":"HIDDEN"}])
        with self.assertRaises(StateDyneError):load_cases(p)
    def test_synthetic_examples_are_valid_public_inputs(self):
        cases=load_cases(ROOT/'examples/public-cases.json')
        self.assertEqual(len(cases),6)
        self.assertTrue(all(set(c)=={"id","task","materials"} for c in cases))
    def test_blind_export_hides_arm_labels(self):
        p=self.root/'samples.json';save_json(p,[{"sample_id":"secret","case_id":"case","arm":"statedyne","repetition":0,"status":"answered","answer":"An explanation."}])
        out=self.root/'blind';blind_export(p,out)
        review=read_json(out/'review.json')
        self.assertNotIn("arm",review[0])
        self.assertNotIn("statedyne",(out/'review.json').read_text())
        self.assertTrue((out/'keep-from-reviewer-key.json').exists())
    def test_scores_need_actual_evidence_notes(self):
        samples=self.root/'samples.json';save_json(samples,[{"sample_id":"s","case_id":"c","arm":"baseline","repetition":0,"status":"answered","answer":"Answer"}])
        out=self.root/'blind';blind_export(samples,out)
        review=read_json(out/'review.json');review[0]["scores"]["discovery"]=4;save_json(out/'review.json',review)
        with self.assertRaises(StateDyneError):score_summary(out/'review.json',out/'keep-from-reviewer-key.json',"Reviewer A")

if __name__ == '__main__':
    unittest.main(verbosity=2)
