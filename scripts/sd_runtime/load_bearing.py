"""Adversarial claim/decision audit with real source and arithmetic gates.

Model judgment identifies pivotal premises; deterministic checks guarantee only
reference validity and reproducible stated arithmetic, NOT epistemic truth.
"""
from __future__ import annotations
from math import isfinite
import re
from .common import StateDyneError, digest
from .evidence import calculate
from .schemas import SCHEMAS, validate

IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")


def snapshot_signature(ws):
    """Tracks real changed evidence, active claims, goal map and requested scope."""
    return digest({"claim_ids": sorted(ws.active_claims()),
                   "source_hashes": sorted((k, v['sha256'], v['active'])
                                           for k, v in ws.state['sources'].items()),
                   "system_map_job": (ws.state.get('system_map') or {}).get('job_id'),
                   "scope": ws.state.get('delivery_scope', ws.state['scope'])})


def _float(s: str, label: str) -> float:
    try:
        value = float(s)
    except (ValueError, TypeError):
        raise StateDyneError(f'{label} must be an explicit finite decimal number')
    if not isfinite(value):
        raise StateDyneError(f'{label} must be finite')
    return value


def register_load_bearing(ws, jid: str) -> None:
    job = ws.job_request(jid)
    if job['role'] != 'load_bearing':
        raise StateDyneError('Load-bearing audit must come from its independent role')
    result = ws.result(jid)
    if not result or not result['independent_context']:
        raise StateDyneError('Independent execution receipt required for a load-bearing audit')
    out = result['output']
    validate(out, SCHEMAS['load_bearing'])
    active = ws.active_claims()
    seen = ws.exposed(jid, result)
    if (not out['thesis_at_risk'].strip() or not out['as_of_handling'].strip()
        or not out['best_countermodel'].strip() or not out['decision_reversal'].strip()):
        raise StateDyneError('A load-bearing audit needs an actual thesis, countermodel, reversal and date boundary')
    if (set(out['examined_claim_ids'])!=set(active) or
        len(out['examined_claim_ids'])!=len(set(out['examined_claim_ids']))):
        raise StateDyneError('The independent premise audit must at least inspect every active claim ID')
    if active and not out['tests']:
        raise StateDyneError('An empty audit is not an examination of existing causal/decision claims')
    ids = [i['local_id'] for i in out['tests']+out['recalculations']+out['net_effect_checks']]
    if len(ids) != len(set(ids)) or any(not IDENTIFIER.fullmatch(x) for x in ids):
        raise StateDyneError('Load-bearing local IDs must be unique and well formed')
    # Impact testing is a second job from checking arithmetic. An error-free
    # base-case DCF can still depend almost entirely on a fragile terminal
    # assumption, and a credible innovation needs an explicit baseline.
    robustness=[]; seen_robust=set()
    for item in out['robustness_checks']:
        cid_list=item['claim_ids']
        if item['local_id'] in seen_robust or not IDENTIFIER.fullmatch(item['local_id']):
            raise StateDyneError('Robustness check local IDs must be unique and well formed')
        seen_robust.add(item['local_id'])
        if len(cid_list)!=len(set(cid_list)) or not set(cid_list).issubset(active):
            raise StateDyneError('Robustness check cites an unknown, stale or repeated claim')
        if not all(item[k].strip() for k in ('base_assumption','changed_assumption',
                       'base_outcome','changed_outcome','impact_on_judgment',
                       'evidence_or_test','visible_limit')):
            raise StateDyneError('Robustness check requires an explicit change, consequence, test and user-facing limitation')
        if item['base_assumption'].strip()==item['changed_assumption'].strip() or \
           item['base_outcome'].strip()==item['changed_outcome'].strip():
            raise StateDyneError('Robustness scenarios must differ in assumptions AND consequences')
        robustness.append({**item,'id':f'{jid}:{item["local_id"]}',
            'epistemic_validation':'structured_assumption_test_only'})
    tests_needing_stress=[x for x in out['tests']
        if x['role']=='forecast' and x['importance'] in ('critical','important')]
    tests_needing_baseline=[x for x in out['tests']
        if x['role']=='intervention' and x['importance'] in ('critical','important')]
    def matched_stress(test, kinds):
        return any(c['kind'] in kinds and
                   (set(c['claim_ids']) & set(test['claim_ids'])
                    if test['claim_ids'] else not c['claim_ids'])
                   for c in out['robustness_checks'])
    if any(not matched_stress(x, {'forecast_sensitivity'}) for x in tests_needing_stress):
        raise StateDyneError('A pivotal forecast needs at least one alternate-assumption sensitivity test linked to the forecast')
    if any(not matched_stress(x, {'incrementality_counterfactual','strong_alternative_baseline'})
           for x in tests_needing_baseline):
        raise StateDyneError('A pivotal intervention needs a no-intervention/strong-existing-alternative comparison linked to the intervention')
    # 10.20: Quantified impact is not automatically net new impact.
    # Check the numeric *bridge* when the independent auditor states a
    # quantitative claim, or force an explicit unknown counterfactual.
    net_checks = []
    for item in out['net_effect_checks']:
        if not item['claim_ids'] or len(set(item['claim_ids'])) != len(item['claim_ids']) \
                or not set(item['claim_ids']).issubset(active):
            raise StateDyneError('Net-effect bridge must cite actual unique active claims')
        if not item['input_basis'].strip() or not item['unit'].strip() or not item['visible_limit'].strip():
            raise StateDyneError('Net-effect bridge needs common unit, input provenance and visible interpretive limit')
        if item['status'] == 'reconciled':
            for key in ('gross_with_program', 'gross_without_program',
                        'displaced_or_transferred', 'stated_net_increment', 'absolute_tolerance'):
                if not item[key].strip():
                    raise StateDyneError('A reconciled net increment needs all gross/counterfactual/displacement quantities')
            gross = calculate(item['gross_with_program'])['result']
            counterfactual = calculate(item['gross_without_program'])['result']
            displaced = calculate(item['displaced_or_transferred'])['result']
            declared = _float(item['stated_net_increment'], 'declared net increment')
            tolerance = _float(item['absolute_tolerance'], 'net increment tolerance')
            if tolerance < 0 or abs(gross - counterfactual - displaced - declared) > tolerance:
                raise StateDyneError('Claimed net increment does not reconcile gross, no-program baseline and displacement')
            net_checks.append({**item, 'id':f'{jid}:{item["local_id"]}',
                'computed_net_increment':gross-counterfactual-displaced,
                'arithmetic_only':True})
        else:
            # An unknown baseline is valid. It is *not* permission to call
            # all gross delivered outputs incremental.
            if item['stated_net_increment'].strip():
                raise StateDyneError('Unknown counterfactual cannot carry a claimed numerical net increment')
            net_checks.append({**item, 'id':f'{jid}:{item["local_id"]}',
                               'computed_net_increment':None, 'arithmetic_only':True})
    for item in out['tests']:
        if not (item['role']=='intervention' and item['importance'] in ('critical','important')
                and item['quantified_incremental_claim']):
            continue
        if not any(set(x['claim_ids']) & set(item['claim_ids']) for x in net_checks):
            raise StateDyneError('Quantified pivotal intervention must reconcile gross vs counterfactual net impact or admit an unknown baseline')
    new_questions = {}
    # The same unresolved premise must not silently become a new user
    # question every time a later stage requests a refreshed audit.
    prior_queries = {(q['question'].casefold().strip(), q['route']):qid
        for qid,q in ws.state['unknowns'].items()
        if q.get('origin')=='load_bearing' and q.get('state')!='stale'}
    reused_queries=set()
    tests = []
    for item in out['tests']:
        if not item['proposition'].strip() or not item['reason'].strip() or not item['decisive_test'].strip():
            raise StateDyneError('A challenge must identify a specific vulnerable claim and discriminating test')
        if not set(item['claim_ids']).issubset(active):
            raise StateDyneError('An audit cannot cite stale or invented claims')
        if not item['claim_ids'] and not item['hidden_premise'].strip():
            raise StateDyneError('Unmodelled assumptions need a concrete hidden premise')
        ws.check_evidence(item['evidence'], exposed=seen)
        if item['support'] in ('anchored','recomputed') and not item['evidence']:
            # An independently calculated premise can provide an arithmetic
            # receipt instead of a quoted external source; checked below.
            if not (item['support']=='recomputed' and
                    any(set(item['claim_ids']) & set(x['claim_ids']) for x in out['recalculations'])):
                raise StateDyneError('Do not mark an unsupported assertion as observed or verified')
        if item['support']=='contradicted' and item['disposition']=='retain':
            raise StateDyneError('A contradictory pivotal premise cannot be retained as established')
        if item['support'] in ('unsupported','contradicted') and item['disposition']=='retain':
            raise StateDyneError('Unsupported evidence cannot be retained without a conditional downgrade')
        if item['disposition']=='investigate' and item['importance'] in ('critical','important'):
            key=(item['decisive_test'].casefold().strip(),item['route'])
            existing=prior_queries.get(key)
            if existing:
                reused_queries.add(existing)
            else:
                qid=f'{jid}:{item["local_id"]}'
                new_questions[qid] = {'id':qid, 'question':item['decisive_test'],
                'why_it_matters':item['reason']+' Reversal: '+out['decision_reversal'],
                'origin':'load_bearing', 'route':item['route'],
                'related_claims':list(item['claim_ids']),
                'priority':'blocking' if item['importance']=='critical' else 'important',
                'state':'open', 'origin_job':jid, 'disposition_evidence':[],
                'audited_premise_id':item['local_id']}
        tests.append({**item,'id':f'{jid}:{item["local_id"]}'})
    verified=[]
    for c in out['recalculations']:
        if not set(c['claim_ids']).issubset(active) or not c['claim_ids']:
            raise StateDyneError('Numeric audit must point to a real quantitative claim')
        if not all(c[x].strip() for x in ('expression','unit','input_basis','interpretation_limit')):
            raise StateDyneError('Calculation must disclose its exact expression, unit, input origin and interpretive limit')
        ws.check_evidence(c['evidence'], exposed=seen)
        computed = calculate(c['expression'])['result']
        stated = _float(c['stated_result'],'stated result')
        tolerance = _float(c['absolute_tolerance'],'absolute tolerance')
        if tolerance < 0 or abs(computed-stated) > tolerance:
            raise StateDyneError('Numerical claim was not reproduced within its declared tolerance')
        verified.append({**c,'id':f'{jid}:{c["local_id"]}',
                         'computed_result':computed, 'arithmetic_only':True})
    # Validate completely before mutating the workspace. Never convert an
    # investigator's unsupported premise to a confirmed fact by registration.
    old=ws.state.get('load_bearing_audit')
    if old and old['job_id'] != jid:
        for q in ws.state['unknowns'].values():
            if (q.get('origin')=='load_bearing' and q.get('state')=='open'
                    and q['id'] not in reused_queries):
                q['state']='stale'
    ws.state['unknowns'].update(new_questions)
    ws.state.setdefault('load_bearing_history',[]).append({'job_id':jid,
        'signature':snapshot_signature(ws), 'new_unknown_ids':list(new_questions)})
    ws.state['load_bearing_audit'] = {'job_id':jid, 'signature':snapshot_signature(ws),
        'thesis_at_risk':out['thesis_at_risk'],
        'examined_claim_ids':out['examined_claim_ids'], 'as_of_scope':out['as_of_scope'],
        'as_of_handling':out['as_of_handling'],
        'tests':tests, 'recalculations':verified, 'robustness_checks':robustness, 'net_effect_checks':net_checks,
        'best_countermodel':out['best_countermodel'],
        'decision_reversal':out['decision_reversal'],
        'discovery_limit':out['discovery_limit']}
    ws.mark_result(jid)
    ws.save('independent_material_assumptions_and_decision_thresholds_audited',
        {'job_id':jid, 'unresolved':list(new_questions),
         'reproduced_arithmetic':len(verified), 'robustness_checks':len(robustness),
         'net_effect_checks':len(net_checks), 'limit':'Structural tests do not certify semantic truth.'})


def check_draft_against_load_bearing(ws, draft):
    audit=ws.state.get('load_bearing_audit')
    if not audit:
        return
    dispositions={d['claim_id']:d['treatment'] for d in draft['claim_dispositions']}
    for case in audit.get('robustness_checks',[]):
        if case['would_reverse'] and any(dispositions.get(cid) in ('use','conditional')
                                         for cid in case['claim_ids']):
            if case['visible_limit'].strip() not in draft['answer']:
                raise StateDyneError('An adopted pivotal conclusion must display the alternative-assumption limit')
    for check in audit.get('net_effect_checks', []):
        if check['status']=='counterfactual_unavailable' and any(
                dispositions.get(cid) in ('use','conditional') for cid in check['claim_ids']):
            if check['visible_limit'].strip() not in draft['answer']:
                raise StateDyneError('An unknown net baseline must remain visible with any adopted quantified intervention')
    for item in audit['tests']:
        if item['importance'] not in ('critical','important'):
            continue
        if item['support'] in ('unsupported','contradicted') or item['disposition'] in ('reject','downgrade'):
            for cid in item['claim_ids']:
                if dispositions.get(cid)=='use':
                    raise StateDyneError('A disputed load-bearing premise cannot be silently used as an established conclusion')
            if any(dispositions.get(cid)=='conditional' for cid in item['claim_ids']):
                note=item['reason'].strip()
                if note not in draft['answer']:
                    raise StateDyneError('An unverified premise used conditionally needs its visible risk/reversal reason')
