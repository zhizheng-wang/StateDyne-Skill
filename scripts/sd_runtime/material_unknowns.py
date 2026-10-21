"""Keep pivotal but unresolved new information visible and alive.

A missing observation may be investigated, asked, or handled by an explicit
conditional account. The latter is not a license to demote a new mechanism
only because it does not immediately change today's action. Structural checks
cannot themselves decide whether a question matters in the real world.
"""
from __future__ import annotations
from .common import StateDyneError
from .inquiry_frontier import VALUE_EFFECTS


def unresolved_material(ws, draft: dict) -> list[dict]:
    found=[]
    chosen=set(draft['used_claim_ids'])
    for disp in draft['information_dispositions']:
        q=ws.state['unknowns'][disp['unknown_id']]
        # A completely rejected candidate need not be promoted merely because
        # it once produced an important question. An unlinked residual, however,
        # still deserves a disposition.
        if q['related_claims'] and not any(cid in chosen for cid in q['related_claims']):
            continue
        if (q['priority'] in ('blocking','important') and
                disp['decision_effect'] in VALUE_EFFECTS and
                disp['treatment'] in ('defer','unavailable')):
            found.append({'unknown':q,'disposition':disp})
    return found


def validate_material_unknowns(ws, draft: dict) -> None:
    pending=unresolved_material(ws,draft)
    answer=draft['answer']
    for record in pending:
        q=record['unknown']
        disp=record['disposition']
        link=disp['fallback_if_unknown'].strip()
        # A conditional inference can proceed without a missing fact, but
        # its current role and the cost of not knowing must reach the reader.
        if not link or len(link)<12 or link not in answer:
            raise StateDyneError('A deferred important discriminator needs a specific visible conditional consequence, not silent suppression')
        if q['route'] in ('materials','calculation') and q['id'] not in ws.state.get('investigated_unknowns',[]):
            raise StateDyneError('Important locally obtainable information was deferred without an acquisition attempt')
        if q['route']=='public_source' and ws.state['config'].get('web_search_enabled') and q['id'] not in ws.state.get('investigated_unknowns',[]):
            raise StateDyneError('Important accessible public evidence was deferred without a real research attempt')
    # Offer the user a choice of deeper research when there is an actual
    # deferred discriminator. This is not a mandatory generic CTA when no
    # additional valuable work remains; conditional final answers stay valid.
    from .research_agenda import agenda
    ready_ids = {x['id'] for x in agenda(ws.state) if x.get('ready')}
    actionable = any(r['disposition']['treatment'] == 'defer' and
                     r['unknown']['id'] in ready_ids for r in pending)
    quiet = bool(draft['navigation'].get('quiet_reply_quote', '').strip())
    if actionable and not quiet:
        nav=draft['navigation']
        if not nav['expansion_offer'].strip() or nav['expansion_offer'] not in answer:
            raise StateDyneError('A still-valuable deferred discriminator must be available as a concrete optional continued-search direction')
