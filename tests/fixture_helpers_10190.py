"""Deterministic protocol records. NOT an LLM model's independent searches."""

def null_search():
    return [{'local_id':'S1','focus':'outside_current_model',
      'incumbent_limit':'The local explanation cannot alone exclude independent environmental causes.',
      'alternative_representation':'Tried an upstream gate independent of local task timing.',
      'distinct_prediction':'', 'rival_prediction':'', 'evidence_route':'materials',
      'outcome':'null_after_search','probe_local_ids':[],
      'reason':'Synthetic fixture: no genuinely independent outside-model hypothesis or evidence was established in this replay.'}]

def search_for(probes):
    if not probes: return null_search()
    return [{'local_id':'S1','focus':'outside_current_model',
      'incumbent_limit':'Local resource contention alone does not account for independent upstream waiting.',
      'alternative_representation':'An independent service queue causes delays without shared local locks.',
      'distinct_prediction':'Delays persist when local locks are absent.',
      'rival_prediction':'Delays disappear when local locks are absent.',
      'evidence_route':'materials',
      'outcome':'advanced' if probes[0]['advance'] else 'deferred',
      'probe_local_ids':[probes[0]['local_id']],
      'reason':'The fixture associates this alternative with a unique test probe; no real search was executed.'}]
