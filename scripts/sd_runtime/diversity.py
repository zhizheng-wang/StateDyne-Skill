"""Observable negative control for repeated 'independent' raw discoveries.

This detects exact or near-exact lexical duplication of the *outputs*, not
semantic independence or the truth of a mechanism. It never requires a hidden
cause to exist; a worker may explicitly report a grounded no-increment result.
"""
from __future__ import annotations
import re
from .common import StateDyneError


def _key(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.casefold(), flags=re.UNICODE).strip()


def _signals(work: dict) -> set[tuple[str, str]]:
    signals = set()
    for claim in work['claims']:
        mech = claim['mechanism']
        # A changed prediction/actual conversion counts as a new proposal even
        # when the high-level statement resembles a sibling's hypothesis.
        descriptor = ' '.join([claim['statement'], mech['transformation'],
                              *claim['distinct_consequences']])
        signals.add(('claim', _key(descriptor)))
    for unknown in work['unknowns']:
        signals.add(('unknown', _key(unknown['question'] + ' ' + unknown['why_it_matters'])))
    for opportunity in work['opportunities']:
        signals.add(('opportunity', _key(opportunity)))
    return {signal for signal in signals if signal[1]}


def check_raw_discovery_diversity(ws, jobs: list[dict]) -> None:
    """Prevent unchanged sibling copies from silently being credited as breadth.

    Run before admitting any raw batch results; failure doesn't mutate the
    cognition state. A justified null discovery is accepted; finding new
    relationships can never be guaranteed by string checks or more workers.
    """
    by_role = {j['role']: ws.result(j['id'])['output'] for j in jobs if j['role'] != 'frame'}
    base = by_role.get('discovery')
    if not base:
        raise StateDyneError('Missing completed baseline discovery output')
    seen = _signals(base)
    # Contrasting independent roles must contribute an additional observable
    # prediction/question/opportunity, or report explicitly why none arises.
    for role in ('reframe', 'contrast_probe', 'environment_scout', 'selection_scout', 'relation_scout', 'blind_challenge'):
        result = by_role.get(role)
        if result is None:
            raise StateDyneError(f'Missing genuinely executed raw worker: {role}')
        proposed = _signals(result)
        if not proposed.difference(seen):
            reason = result['no_increment_reason'].strip()
            if len(reason) < 24:
                raise StateDyneError(
                    f'Independent {role} only repeated previous signals without a specific '
                    'no-increment explanation; do not count duplicate reports as breadth')
        seen.update(proposed)
