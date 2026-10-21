"""Observable innovation follow-through, not a claim of semantic genius.

A new representation must carry a distinct test or honest null receipt. This
module cannot tell if a hypothesis is true or genuinely novel in the world.
"""
from __future__ import annotations
import re
from .common import StateDyneError


def _identity(claim):
    mechanism = claim.get('mechanism') or {}
    value=' '.join([claim.get('statement',''), mechanism.get('transformation',''),
                    *claim.get('distinct_consequences',[])])
    return re.sub(r'[\W_]+',' ',value.casefold(),flags=re.UNICODE).strip()


def validate_breakthrough(ws, job_id, *, baseline_claims=None):
    result=ws.result(job_id)
    if not result:
        raise StateDyneError('A breakthrough worker request without a real result is not discovery')
    product=result['output']
    claims=product['claims']
    if not claims and not product['unknowns'] and not product['opportunities']:
        if len(product['no_increment_reason'].strip()) < 65:
            raise StateDyneError('A null breakthrough needs concrete nontrivial alternative search and failure reason')
        return False
    existing={_identity(x) for x in (baseline_claims if baseline_claims is not None
                                    else ws.active_claims().values())}
    introduced=set()
    for c in claims:
        identity=_identity(c)
        if not c['distinct_consequences'] or not any(x.strip() for x in c['distinct_consequences']):
            raise StateDyneError('A claimed breakthrough needs a nonempty distinct, refutable consequence')
        if not identity or identity in existing or identity in introduced:
            raise StateDyneError('Restating an existing relation/prediction cannot be credited as a new breakthrough')
        introduced.add(identity)
    if claims and not (product['unknowns'] or product['opportunities']):
        raise StateDyneError('A proposed breakthrough needs a discriminating information route or actual research opportunity')
    # Honest research-route requirements; model semantic quality is reviewed separately.
    if not claims and not any(x.strip() for x in product['opportunities']) and not product['unknowns']:
        raise StateDyneError('No visible discovery or search opening')
    return True
