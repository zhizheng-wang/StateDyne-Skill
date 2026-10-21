"""High-value exploration work can enter the SAME independent batch.

Unlike the former one-model/one-evidence per cycle, this dispatcher does not
silently serialize unrelated unexplored relationships. Every worker reads the
same frozen pre-batch snapshot; no sibling's hypothesis leaks to another.
A bounded concurrent batch is a transport capacity, NOT a global search limit.
"""
from __future__ import annotations


def _unique(values):
    return list(dict.fromkeys(values))


def priority_batch(*, model_opportunities, research_unknowns, evidence_reframes,
                   capacity: int, environment_opportunities=(), environment_unknowns=(),
                   rotation: int = 0, opportunity_metadata=None):
    """Fair parallel discovery across model, environment and obtainable evidence.

    Novel opportunities are never silently omitted by provenance. The rotation
    is persisted by the caller across bounded batches, so a tiny concurrency
    limit cannot perpetually starve the same kind of investigation. Workers
    operate from a frozen common snapshot; dependent evidence is reconciled
    only AFTER the whole batch completes.
    """
    if capacity < 1:
        return []
    result = []
    env = [('opportunity',x) for x in _unique(environment_opportunities)] + [
        ('unknown',x) for x in _unique(environment_unknowns)]
    models = [oid for oid in _unique(model_opportunities) if ('opportunity',oid) not in env]
    facts = _unique(research_unknowns)
    if evidence_reframes:
        triggers = _unique([r['acquire_job'] for r in evidence_reframes])
        claims = _unique([cid for record in evidence_reframes for cid in record.get('claim_ids', [])])
        result.append({
            'operator': 'reframe', 'target_ids': claims, 'opportunity_ids': [],
            'rationale': 'New evidence may change the incumbent model: revisit causal structure and predictions.',
            'expected_difference': 'An updated mechanism, unreported cross-context prediction or evidence-grounded null result, not merely an appended citation.',
            'strongest_alternative': 'The incumbent model explains the acquired evidence without changing predictions.',
            'why_parallel_safe': 'The acquisition finished; each worker reads the same frozen snapshot.',
            'evidence_trigger_ids': triggers,
        })

    def model_task(oid):
        metadata = (opportunity_metadata or {}).get(oid, {})
        # Jury-originated obtainable evidence is genuinely ACQUIRED, not just
        # sent to another worker to explain the same story more elegantly.
        retrieve = metadata.get('evidence_route') in ('materials', 'calculation', 'public_source')
        return {'operator':'acquire' if retrieve else 'reframe',
            'target_ids':[],'opportunity_ids':[oid],
            'rationale':(f'Obtain the discriminating evidence for outcome-competition lead ({oid}).'
                         if retrieve else
                         f'Investigate an unexamined material relation ({oid}), independently of the first explanation.'),
            'expected_difference':'A new relationship, distinct prediction, rival test or evidence-grounded null finding.',
            'strongest_alternative':'The current representation already explains the same concrete outcomes.',
            'why_parallel_safe':'Each worker independently reads the frozen model and evidence snapshot.'}

    def environment_task(item):
        source,oid = item
        return {'operator':'environment',
            'target_ids':[oid] if source=='unknown' else [],
            'opportunity_ids':[oid] if source=='opportunity' else [],
            'rationale':f'Test an important environmental constraint/selection route ({oid}): who or what selects outcomes, with what actual rules and evidence.',
            'expected_difference':'A traceable real-world selection/constraint mechanism, discriminating evidence route, or a concrete no-increment finding.',
            'strongest_alternative':'Publicly known rules, ordinary variation or existing causal models fully explain the observed difference.',
            'why_parallel_safe':'Environment work reads the same frozen snapshot, without treating sibling claims as facts.'}

    def evidence_task(uid):
        return {'operator':'acquire','target_ids':[uid],'opportunity_ids':[],
            'rationale':f'Obtain or calculate an independently answerable key unknown ({uid}), without burdening the user.',
            'expected_difference':'Grounded source or calculation distinguishing mechanisms, or an explicit failed access attempt.',
            'strongest_alternative':'No admissible currently obtainable evidence distinguishes the current candidate models.',
            'why_parallel_safe':'Acquisition starts from the frozen source index.'}

    # Preserve the established model/evidence alternation when there is no
    # environment work. With three lanes, rotate the starting lane between
    # batches. Empty lanes are skipped without changing intellectual scope.
    lanes = [('model',models,model_task)]
    if env:
        lanes.append(('environment',env,environment_task))
    lanes.append(('evidence',facts,evidence_task))
    offset = rotation % len(lanes)
    while len(result) < capacity and any(queue for _,queue,_ in lanes):
        for step in range(len(lanes)):
            _, queue, make = lanes[(offset + step) % len(lanes)]
            if queue and len(result) < capacity:
                result.append(make(queue.pop(0)))
        # Advance origin to maintain fairness if the batch stops early.
        offset = (offset + 1) % len(lanes)
    return result
