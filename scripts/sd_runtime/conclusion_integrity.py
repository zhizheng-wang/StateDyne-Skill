"""Structural coherence between major numeric conclusions and their sections.

This does not establish the truth of measurements, economic assumptions or
cross-section completeness. Independent writer and auditor still must check
meaning, denominators, sources, and counterfactual logic.
"""
from __future__ import annotations
import re
from .common import StateDyneError

_NUM = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_RANGE = re.compile(r"^\s*([+-]?[\d,]+(?:\.\d+)?)\s*(?:[–—~-]|至|到|\bto\b)\s*([+-]?[\d,]+(?:\.\d+)?)\s*$", re.I)


def quantity_value(raw: str) -> tuple[float, float]:
    raw = raw.strip()
    match = _RANGE.fullmatch(raw)
    parts = (match.group(1), match.group(2)) if match else (raw,raw)
    if not all(_NUM.fullmatch(part) for part in parts):
        raise StateDyneError('A significant quantity needs a reproducible scalar or two-ended interval')
    numbers = tuple(float(x.replace(',', '')) for x in parts)
    if numbers[0]>numbers[1]:
        raise StateDyneError('Numeric interval has reversed endpoints')
    return numbers


def check_pivotal_quantities(ws, draft: dict) -> None:
    answer = draft['answer']
    chosen = set(draft['used_claim_ids'])
    seen=set()
    for item in draft['pivotal_quantities']:
        name=item['local_id'].strip()
        if not name or name in seen:
            raise StateDyneError('Pivotal quantitative measures require unique nonempty IDs')
        seen.add(name)
        if not item['metric'].strip() or not item['measurement_basis'].strip() or not item['population_and_scope'].strip() or not item['period'].strip() or not item['unit'].strip() or not item['scenario'].strip() or not item['assumption_or_limit'].strip():
            raise StateDyneError('Quantitative bridge needs a named measure, scope, period, unit, scenario and assumptions')
        refs=item['claim_ids']
        if not refs or len(refs)!=len(set(refs)) or not set(refs).issubset(chosen):
            raise StateDyneError('A quantitative bridge must track real selected claims')
        spans=[]
        for section in ('headline','body','conclusion'):
            span=item[f'{section}_anchor'].strip()
            value=item[f'{section}_value'].strip()
            if bool(span)!=bool(value):
                raise StateDyneError('Numeric value and visible supporting anchor must either both be present or both absent')
            if span:
                if span not in answer or value not in span:
                    raise StateDyneError('A declared numeric quantity must actually be stated in its answer anchor')
                spans.append((section,quantity_value(value)))
        if not spans:
            raise StateDyneError('An audited quantity must exist in the delivered answer')
        if item['relation']=='same_measure':
            if len(spans)<2:
                raise StateDyneError('A repeated decisive measure must link at least two sections')
            if any(pair[1]!=spans[0][1] for pair in spans[1:]):
                raise StateDyneError('Headline, body and conclusion disagree on the same scoped measure')
        elif item['relation']=='different_measures_explained':
            if len(spans)<2 or not item['visible_reconciliation'].strip() or item['visible_reconciliation'] not in answer:
                raise StateDyneError('Different measures need an explicit user-visible denominator or scope reconciliation')
        elif len(spans)!=1:
            raise StateDyneError('A single-location numeric conclusion cannot silently skip repeated claims')

    # A selected numeric *decision/forecast claim* needs a visible bridge,
    # not merely one arithmetic calculation. Source facts mentioned in a
    # narrative mechanism are not automatically pivotal forecasts.
    active=ws.active_claims()
    markers=re.compile(r'(?:[%％$€£]|\b(?:USD|EUR|CNY|bn|bps|million|billion|units|customers|households|margin|profit|valuation)\b|[万亿套户吨元倍个百分点]|净新增|增长率|收益率)', re.I)
    for cid in chosen:
        claim=active.get(cid, {})
        statement=claim.get('statement','')
        if (claim.get('kind') in ('prediction','point','plan','inference')
                and any(x.isdigit() for x in statement) and markers.search(statement)):
            if not any(cid in item['claim_ids'] for item in draft['pivotal_quantities']):
                raise StateDyneError('An adopted numerical forecast or intervention claim needs a cross-section quantitative bridge')

    # An adopted quantified additional outcome needs a visible, reconciled
    # bridge even when an independent source/arithmetical check exists. This
    # does not falsely demand quantitative forecasts from qualitative tasks.
    load=ws.state.get('load_bearing_audit') or {}
    for net in load.get('net_effect_checks',[]):
        if net['status']!='reconciled':
            continue
        if any(cid in chosen for cid in net['claim_ids']):
            if not any(set(x['claim_ids']) & set(net['claim_ids']) for x in draft['pivotal_quantities']):
                raise StateDyneError('Adopted quantified net effect is missing the cross-section result bridge')


def check_quantity_review(audit: dict, draft: dict) -> None:
    indexed={r['quantity_id']:r for r in audit['quantity_reviews']}
    ids=[q['local_id'] for q in draft['pivotal_quantities']]
    if len(audit['quantity_reviews'])!=len(indexed) or set(indexed)!=set(ids):
        raise StateDyneError('Independent numeric review must inspect each adopted pivotal quantity')
    if not audit['numeric_coverage_reason'].strip():
        raise StateDyneError('Independent review must explain numeric coverage including any absent material quantities')
    for item in draft['pivotal_quantities']:
        review=indexed[item['local_id']]
        if not all(review[field].strip() for field in ('source_scope_and_units','competing_numeric_interpretation','effect_on_conclusion')):
            raise StateDyneError('Numeric reviewer must examine source/denominator and competing interpretation')
        if review['verdict']=='needs_revision' and audit['verdict']=='pass':
            raise StateDyneError('A detected material numerical contradiction cannot pass')
        if item['relation']=='different_measures_explained' and review['verdict']=='consistent':
            raise StateDyneError('Distinct quantities need an explicit distinct-metric review, not a false equality check')
        if item['relation']=='same_measure' and review['verdict']=='distinction_supported':
            raise StateDyneError('One comparable quantitative measure cannot be reviewed as different denominators')
