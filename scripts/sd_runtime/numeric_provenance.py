"""Bounded, deterministic checks for source-to-report numerical transformations.

This module establishes unit arithmetic and same-source matching for registered
materials. An external URL or a worker's quote is NOT cryptographic proof of
retrieval: the independent semantic reviewer must still open the cited source.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import re
from .common import StateDyneError
from .evidence import calculate

# Important: expand ONLY with well-defined units; do not infer a unit from a
# loose number or invent a local currency conversion rate.
SCALES = {
    'USD': ('usd', 1), '美元': ('usd', 1), '美元/年': ('usd_per_year', 1),
    'USD/year': ('usd_per_year', 1),
    'USD million': ('usd', 1_000_000), '百万美元': ('usd', 1_000_000),
    'USD billion': ('usd', 1_000_000_000), '十亿美元': ('usd', 1_000_000_000),
    '亿美元': ('usd', 100_000_000), '万亿美元': ('usd', 1_000_000_000_000),
    '股': ('shares', 1), 'shares': ('shares', 1),
    '万股': ('shares', 10_000), '百万股': ('shares', 1_000_000),
    'million shares': ('shares', 1_000_000),
    '套': ('housing_units', 1), '住房套': ('housing_units', 1),
    'units': ('housing_units', 1), '千套': ('housing_units', 1000),
    '万套': ('housing_units', 10_000),
    '%': ('percent', 1), '％': ('percent', 1),
}


def decimal_number(value, what):
    try:
        n = Decimal(str(value).strip().replace(',', '').replace('，', ''))
        if not n.is_finite():
            raise InvalidOperation
        return n
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise StateDyneError(f'{what} must be a finite decimal number') from exc


def normalize(value, unit):
    if unit not in SCALES:
        raise StateDyneError(f'Unsupported numeric unit {unit!r}; use a declared unit rather than guessing a conversion')
    dimension, multiplier = SCALES[unit]
    return dimension, decimal_number(value, 'quantity') * multiplier


def number_occurs(number: str, excerpt: str) -> bool:
    """Match numeric tokens independently of separators, not substrings."""
    needle = decimal_number(number, 'source number')
    matches = re.findall(r'(?<![\w.])[+-]?\d(?:\d|,(?=\d))*(?:\.\d+)?(?!\d|,|\.\d)', excerpt)
    for match in matches:
        try:
            if decimal_number(match, 'quoted numeric token') == needle:
                return True
        except StateDyneError:
            pass
    return False


def validate_numeric_sources(ws, draft: dict):
    used_ids = {entry['local_id'] for entry in draft['numeric_source_checks']}
    if len(used_ids) != len(draft['numeric_source_checks']):
        raise StateDyneError('Duplicate numeric source check ID')
    for fact in draft['numeric_source_checks']:
        anchor = fact['visible_anchor'].strip()
        if not anchor or anchor not in draft['answer'] or not fact['displayed_value'].strip() or not fact['displayed_unit'].strip():
            raise StateDyneError('Numeric source check needs its actual answer text, number and unit')
        if fact['displayed_value'] not in anchor or fact['displayed_unit'] not in anchor:
            raise StateDyneError('Numeric source check must quote the printed value AND unit, not just an internal number')
        dimension, printed = normalize(fact['displayed_value'], fact['displayed_unit'])
        if dimension != fact['base_dimension']:
            raise StateDyneError('Displayed numeric unit has the wrong physical/economic dimension')
        if not fact['formula'].strip() or not fact['source_locator'].strip() or not fact['period'].strip() or not fact['population_and_scope'].strip():
            raise StateDyneError('Numeric source chain needs a reproducible formula and source/date/scope route')
        computed = decimal_number(calculate(fact['formula'])['result'], 'computed numeric amount')
        tolerance = decimal_number(fact['absolute_tolerance_base'], 'numeric tolerance')
        if tolerance < 0 or abs(computed - printed) > tolerance:
            raise StateDyneError('Numeric source-to-display unit or computation mismatch')
        tier = fact['source_tier']
        if tier in ('registered_material','retrieved_primary','retrieved_secondary'):
            source_value = fact['source_value']
            source_unit = fact['source_unit']
            source_quote = fact['source_quote']
            if not source_value or not source_unit or not source_quote:
                raise StateDyneError('Observed source data require a quoted value and its original unit')
            if not number_occurs(source_value, source_quote):
                raise StateDyneError('Claimed source number cannot be found in the supplied source quotation')
            # Only comparable direct source facts can be checked by unit arithmetic.
            # Derived formulas may combine several independent original inputs.
            sd, source_in_base = normalize(source_value, source_unit)
            if fact['kind'] == 'sourced_fact':
                if sd != dimension:
                    raise StateDyneError('Source fact and displayed fact refer to incompatible units')
                if abs(source_in_base - printed) > tolerance:
                    raise StateDyneError('Original primary source value disagrees with the displayed number')
            if tier == 'registered_material':
                source_id = fact['source_locator']
                source = ws.state.get('sources', {}).get(source_id)
                if not source or not source.get('active') or source_quote not in source.get('text',''):
                    raise StateDyneError('A registered source quotation must occur in the actual active source text')
        elif tier == 'unverified_assumption':
            if fact['kind'] != 'scenario' or not fact['user_visible_limit'].strip() or fact['user_visible_limit'] not in draft['answer']:
                raise StateDyneError('Unverified assumptions cannot be presented as observed numeric facts')
        elif tier != 'derived_from_checked_inputs':
            raise StateDyneError('Unknown numeric source tier')
        if fact['kind'] == 'sourced_fact' and tier in ('unverified_assumption','derived_from_checked_inputs'):
            raise StateDyneError('A claimed observed number needs an actual original source route')
    check_declared_equity_identity(draft['answer'])
    # This is only an observed-source ledger; semantic completeness cannot be
    # guaranteed by deterministic checking. The independent reviewer must find
    # material numeric facts omitted from the writer's ledger.


def validate_numeric_source_review(audit: dict, draft: dict):
    indexed = {entry['local_id']: entry for entry in audit['numeric_source_reviews']}
    expected = {item['local_id'] for item in draft['numeric_source_checks']}
    if len(indexed) != len(audit['numeric_source_reviews']) or set(indexed) != expected:
        raise StateDyneError('Independent review must inspect every recorded numeric source chain')
    if not audit['source_fact_coverage_reason'].strip():
        raise StateDyneError('Independent numeric source review must evaluate missing decisive empirical facts')
    for source in draft['numeric_source_checks']:
        review = indexed[source['local_id']]
        if not all(review[k].strip() for k in ('verified_source_locator','actual_source_measure',
                              'original_unit_and_date','independent_unit_reconciliation',
                              'consequence_if_wrong')):
            raise StateDyneError('Each numerical fact requires a real independent source, time and unit review')
        if review['verdict'] == 'needs_revision' and audit['verdict'] == 'pass':
            raise StateDyneError('An independently flagged numerical source discrepancy cannot pass')
        if source['source_tier'] == 'unverified_assumption' and review['verdict'] == 'verified_fact':
            raise StateDyneError('A conditional assumption is not an independently verified fact')
        if source['source_tier'] in ('retrieved_primary','retrieved_secondary') and review['verdict']=='verified_fact':
            if not review['independent_retrieval_receipt'].strip():
                raise StateDyneError('Public empirical facts require an independent actual retrieval reference')


# A deliberately conservative stock-equity identity check. The tripwire is
# active only if one local explanation states price, share count, and computed
# market capitalisation. It does not need the writer to register a claim.
_PRICE = re.compile(r'(?:收盘价|股价|share price|closing price)[^\d]{0,28}([\d,]+(?:\.\d+)?)', re.I)
_SHARE = re.compile(r'([\d,]+(?:\.\d+)?)\s*(万股|亿股|百万股|million shares)', re.I)
_CAP = re.compile(r'(?:股权市值|总市值|market cap(?:italization)?|市值)[^\d]{0,32}([\d,]+(?:\.\d+)?)\s*(亿美元|十亿美元|百万美元|美元|USD billion|bn|亿)', re.I)


def check_declared_equity_identity(answer: str) -> None:
    clean = re.sub(r'\*|_|`|\u200b', '', answer)
    for match in re.finditer(r'(?:股权市值|总市值|市值|market cap(?:italization)?)', clean, re.I):
        # In a cohesive local claim the pricing inputs should appear nearby.
        prefix = clean[max(0, match.start()-360):match.start()]
        # Do not cut off the entire claim because its sentence ends *after*
        # the cap field. Only discard prior completed sentences.
        prefix = prefix[prefix.rfind('。')+1:]
        suffix = clean[match.start():match.start()+120].split('。',1)[0]
        block = prefix + suffix
        if not (re.search(r'(?:按|以|乘以|based on|using)', block, re.I)):
            continue
        price = list(_PRICE.finditer(block))
        shares = list(_SHARE.finditer(block))
        cap = list(_CAP.finditer(block))
        if not (price and shares and cap):
            continue
        px, sc, mc = price[-1], shares[-1], cap[-1]
        if px.start() > mc.start() or sc.start() > mc.start():
            continue
        # Understood units intentionally narrow: avoid spurious failures on
        # market cap in currencies other than USD or diluted share adjustments.
        try:
            stock_price = decimal_number(px.group(1),'stock price')
            sh_kind, stock_count = normalize(sc.group(1), {'万股':'万股','亿股':'亿股','百万股':'百万股',
                                                'million shares':'million shares'}[sc.group(2)])
            cap_unit = mc.group(2)
            if cap_unit in ('亿','bn'):
                cap_unit = '亿美元' if cap_unit=='亿' else 'USD billion'
            cap_kind, cap_amount = normalize(mc.group(1), cap_unit)
            expected = stock_price * stock_count
            if sh_kind == 'shares' and cap_kind=='usd' and expected > 0:
                if abs(cap_amount-expected)/expected > Decimal('0.015'):
                    raise StateDyneError('Headline market capitalization is inconsistent with price × shares or the 亿/billion scale; independently recalculate before publishing')
        except (KeyError, InvalidOperation):
            continue
