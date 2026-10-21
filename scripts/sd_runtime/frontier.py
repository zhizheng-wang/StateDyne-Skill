"""Source-anchored phenomenon coverage, not a semantic truth oracle.

The controller enforces coverage and references; independent model workers must
judge whether a proposed transformation or prediction *means* anything.
"""
from __future__ import annotations
import re
from .common import StateDyneError

LOCAL_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


def record_focus(ws, jid: str):
    """Admit an independent raw-material map only when all its anchors are real."""
    result = ws.result(jid)
    if result is None:
        raise StateDyneError("Unexecuted raw phenomena mapping cannot be admitted")
    output = result['output']
    if not output['foci'] and not output['no_focus_reason'].strip():
        raise StateDyneError("No focal phenomena and no grounded reason for their absence")
    ids = [f['local_id'] for f in output['foci']]
    if len(set(ids)) != len(ids) or any(not LOCAL_ID.fullmatch(fid) for fid in ids):
        raise StateDyneError("Duplicate or invalid focal phenomenon identifier")
    anchors = []
    exposed = ws.exposed(jid, result)
    for f in output['foci']:
        if not f['evidence'] or not all(f[k].strip() for k in ('observation', 'unexplained_difference', 'why_material')):
            raise StateDyneError("A focal phenomenon needs real evidence, an observation and the missing relation")
        # The material mapper gets the unfiltered original task, not private
        # sibling analyses; it cannot cite a file it has not actually read.
        ws.check_evidence(f['evidence'], exposed=exposed)
        anchors.append({**f, 'id':f"{jid}:{f['local_id']}"})
    ws.state['foci'] = anchors
    ws.state['focus_job'] = jid
    ws.mark_result(jid)
    ws.save('source_anchored_phenomena_mapped', {'job_id':jid, 'foci':[x['id'] for x in anchors]})


def check_boundary(ws, output: dict, reviewer_jid: str | None = None):
    """No unmentioned focal contrast may vanish behind a generic PASS."""
    expected = {x['id']: x for x in ws.state.get('foci', [])}
    # A reviewer may discover a source-anchored phenomenon the first mapper
    # missed; otherwise the map would become the very single-model bottleneck
    # this system is designed to escape. New items enter the same ledger.
    for f in output['new_foci']:
        fid = f['local_id']
        if not LOCAL_ID.fullmatch(fid):
            raise StateDyneError("Invalid independently discovered focus ID")
        if fid in expected:
            if {k:v for k,v in expected[fid].items() if k!='id'} != f:
                raise StateDyneError("Conflicting reused focus identifier")
        else:
            if not reviewer_jid or not f['evidence'] or not all(f[k].strip() for k in ('observation','unexplained_difference','why_material')):
                raise StateDyneError("Review-discovered focus requires an actual worker, evidence and a concrete difference")
            ws.check_evidence(f['evidence'], exposed=ws.exposed(reviewer_jid, ws.result(reviewer_jid)))
            expected[fid] = {**f, 'id': fid}
    # An independent review must explicitly receive and triage the material
    # *system* gaps, not merely applaud a source-anchored phenomenon ledger.
    world=ws.state.get('system_map') or {}
    expected_system={entry['dimension'] for entry in world.get('coverage', [])
                     if entry['state']=='open' and entry['priority'] in ('blocking','important')}
    dispositions=output.get('system_coverage_dispositions', [])
    names=[d['dimension'] for d in dispositions]
    if len(names)!=len(set(names)) or set(names)!=expected_system:
        raise StateDyneError('The independent boundary review must triage every material open system interface')
    for entry in dispositions:
        if not entry['rationale'].strip() or not entry['evidence_or_next_action'].strip():
            raise StateDyneError('A system gap cannot be dismissed or deferred with an empty relevance/next-step reason')
        if entry['resolution']=='search' and not any(q.get('system_dimension')==entry['dimension']
            and q.get('state')=='open' for q in ws.state['unknowns'].values()):
            raise StateDyneError('System research disposition requires an actually registered unknown')
    rows = output['coverage']
    ids = [x['focus_id'] for x in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise StateDyneError("First-pass review must explicitly cover every source-anchored phenomenon")
    known = ws.active_claims()
    # Every reviewed discovery portfolio must judge the difference between
    # new testable representation and a polished repetition of the baseline.
    # This checks only visible claim references, NOT whether a hypothesis is true.
    assessment = output.get('search_space_assessment')
    novel_search_missing = False
    if assessment is not None:
        judgment = assessment['judgment']
        for field in ('prior_representation_limit', 'tested_alternative_representation', 'comparison_reason'):
            if not assessment[field].strip():
                raise StateDyneError('Search-space review needs a concrete baseline limit, alternate model and comparison')
        cited = assessment['candidate_claim_ids']
        if len(cited) != len(set(cited)) or not set(cited).issubset(known):
            raise StateDyneError('Search-space review cites nonexistent or duplicate candidate')
        if judgment == 'new_testable_space':
            if not cited or not assessment['unreported_outcome'].strip() or not assessment['discriminating_observation'].strip():
                raise StateDyneError('Novel model space must cite an admitted candidate, unseen prediction and discriminator')
            recognized = {'reframe', 'contrast_probe', 'frontier_scout', 'breakthrough_scout', 'blind_challenge', 'environment_scout'}
            if not any(ws.job_request(known[cid]['origin_job'])['role'] in recognized for cid in cited):
                raise StateDyneError('A supposedly new model space must use an independently sourced outside candidate')
        elif judgment == 'missing_search':
            novel_search_missing = True
        elif cited:
            raise StateDyneError('A null model-space search cannot cite a candidate as accepted novelty')
    needs_repair = False
    for row in rows:
        focus = expected[row['focus_id']]
        candidates = row['candidate_claim_ids']
        if len(candidates) != len(set(candidates)) or not set(candidates).issubset(known):
            raise StateDyneError("Phenomenon coverage cites missing or repeated candidate IDs")
        if not row['reason'].strip():
            raise StateDyneError("Phenomenon coverage requires a real scope/relationship comparison")
        status = row['status']
        if status == 'explained':
            if not candidates or not row['missing_or_explained_bridge'].strip() or not row['unreported_prediction'].strip() or not row['discriminator'].strip():
                raise StateDyneError("A claimed explanation needs a supporting candidate, actual bridge, new prediction and discrimination path")
            # This catches direct copying of a known observation as 'new'.
            # Paraphrases require a genuinely independent semantic reviewer.
            known_quotes = [e['quote'] for e in focus['evidence']]
            if any(row['unreported_prediction'].strip() == q.strip() for q in known_quotes):
                raise StateDyneError("A known observation cannot be resubmitted verbatim as a novel prediction")
        elif status == 'not_material':
            if focus['priority'] == 'critical' and not row['missing_or_explained_bridge'].strip():
                raise StateDyneError("An allegedly immaterial critical phenomenon needs an explicit reason")
        else:  # partial / open: must change the next cognitive action.
            needs_repair = True
            if not row['missing_or_explained_bridge'].strip() or not row['discriminator'].strip():
                raise StateDyneError("An unresolved phenomenon needs a missing bridge and actionable discriminator")
    if (needs_repair or novel_search_missing) and output['verdict'] != 'reopen':
        raise StateDyneError("Partially explained / open phenomena cannot pass the first boundary gate")
    if output['verdict'] == 'reopen' and not (needs_repair or novel_search_missing):
        raise StateDyneError("A reopening verdict must identify a partially explained or open phenomenon")
    return [expected[f['local_id']] for f in output['new_foci'] if f['local_id'] not in
            {x['id'] for x in ws.state.get('foci', [])}]


def ensure_repair_changed_relation(ws, previous: dict, current: dict, repair_jid: str):
    """A second approval cannot merely re-label the old weak explanation.

    Structural lower bound: previously open/partial focal phenomena must be
    materially addressed by a *newly admitted* claim from the actual repair
    worker, or explicitly challenged as out-of-scope (still model-reviewed).
    It is not a semantic sufficiency proof.
    """
    before = {x['focus_id']: x for x in previous.get('coverage', [])}
    after = {x['focus_id']: x for x in current['coverage']}
    repaired = {c['id'] for c in ws.active_claims().values() if c['origin_job'] == repair_jid}
    # If an independent reviewer judged that a genuinely different search
    # never happened, a later PASS must be backed by a fresh prediction or an
    # explicit, grounded null-result artifact from the actual repair worker.
    # Structural evidence of work is not a proof that the hypothesis is true.
    old_search = previous.get('search_space_assessment', {})
    if old_search.get('judgment') == 'missing_search' and current['verdict'] == 'pass':
        repair_claims = [c for c in ws.active_claims().values() if c['origin_job'] == repair_jid
                         and c['kind'] in ('mechanism','prediction') and c.get('distinct_consequences')]
        repair_product = ws.result(repair_jid)
        null_reason = repair_product['output'].get('no_increment_reason', '') if repair_product else ''
        a = current.get('search_space_assessment', {})
        if not repair_claims and not (a.get('judgment') == 'no_new_space_after_search' and len(null_reason.strip()) >= 24):
            raise StateDyneError('A previously missing model-space search needs a real new prediction or grounded null-result')
    for focus_id, row in before.items():
        if row['status'] not in ('partial', 'open'):
            continue
        fixed = after.get(focus_id)
        if not fixed:
            raise StateDyneError("A former first-pass gap disappeared during recheck")
        if fixed['status'] == 'explained' and not repaired.intersection(fixed['candidate_claim_ids']):
            raise StateDyneError("First-pass gap recheck reused only old claims; no actual new relation was admitted")
        if fixed['status'] == 'not_material':
            # Prevent the easiest loophole: relabeling an unresolved critical
            # observation as irrelevant without a changed argument.
            if fixed['reason'].strip() == row['reason'].strip():
                raise StateDyneError("Recheck cannot dismiss an open phenomenon with its unchanged original reason")


def validate_final_focus(ws, draft: dict):
    """Require disposition in the *published text*, not just the hidden ledger.

    We intentionally avoid pretending that a string match verifies causation.
    The draft states what it has explained vs. what remains unknown.
    """
    mapped = {x['id']: x for x in ws.state.get('foci', [])}
    entries = draft['focus_dispositions']
    ids = [x['focus_id'] for x in entries]
    if len(ids) != len(set(ids)) or set(ids) != set(mapped):
        raise StateDyneError("Every focal phenomenon needs a final disposition")
    for entry in entries:
        if not entry['visible_resolution'].strip() or entry['visible_resolution'] not in draft['answer']:
            raise StateDyneError("The handling of a focal contrast must be visible in the answer")
        if not entry['rationale'].strip():
            raise StateDyneError("Focal disposition cannot consist only of a status label")
        if entry['status'] == 'explained' and not entry['linked_claim_ids']:
            raise StateDyneError("Claimed final explanation needs a candidate link")
        if not set(entry['linked_claim_ids']).issubset(ws.active_claims()):
            raise StateDyneError("Focal disposition points at an invalid candidate")
        if entry['status'] == 'open' and draft['status'] == 'complete':
            raise StateDyneError("Open focal phenomena prohibit claiming full completion")
