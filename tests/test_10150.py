"""10.15 protocol negative controls, all synthetic and independent of personal cases."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import unittest
from sd_runtime.common import StateDyneError
from sd_runtime.delivery_quality import validate_delivery_quality
from sd_runtime.schemas import validate, SCHEMAS
from test_runtime import Base, claim, work, draft_for, audit_for


class EvidenceAndActionReviewTests(Base):
    def example(self, intervention=False, extra_unused=False):
        ws=self.workspace(scope='actions' if intervention else 'analysis')
        claims=[claim('M1')]
        if intervention:
            claims.extend([claim('P1',kind='point',deps=['M1']),
                           claim('A1',kind='action',deps=['P1'])])
        if extra_unused:
            claims.append(claim('R1', kind='prediction'))
        j=self.make_job(ws, 'discovery', 'work', ws.raw_view())
        self.receive(ws,j,work(claims=claims))
        ws.merge_work(j['id'])
        d=self.make_job(ws,'compose','draft',ws.current_view())
        answer=draft_for(d)
        if extra_unused:
            spare=next(c for c in ws.active_claims().values() if c['kind']=='prediction')
            answer['claim_dispositions']=[{'claim_id':c['id'],
                       'treatment':'not_selected' if c['id']==spare['id'] else 'conditional',
                       'reason':'Test alternative not selected' if c['id']==spare['id'] else 'Still conditional'}
                       for c in ws.active_claims().values()]
            answer['used_claim_ids']=[cid for cid in answer['used_claim_ids'] if cid!=spare['id']]
        self.receive(ws,d,answer)
        ws.set_draft(d['id'])
        inp=ws.current_view(); inp['draft']=answer; inp['draft_sha256']=ws.state['draft']['sha256']
        a=self.make_job(ws,'audit','audit',inp)
        reviewer=audit_for(a)
        return ws, answer, a, reviewer

    def test_schema_requires_both_final_review_sections(self):
        _,_,_,review=self.example()
        incomplete=deepcopy(review); incomplete.pop('causal_boundary_reviews')
        with self.assertRaises(StateDyneError): validate(incomplete,SCHEMAS['audit'])
        incomplete=deepcopy(review); incomplete.pop('strategy_challenge')
        with self.assertRaises(StateDyneError): validate(incomplete,SCHEMAS['audit'])

    def test_good_analysis_causal_caveat_passes(self):
        ws,draft,job,review=self.example()
        validate_delivery_quality(ws,review,draft)
        self.receive(ws,job,review)
        ws.set_audit(job['id'])
        self.assertEqual(ws.state['audit']['output']['verdict'],'pass')

    def test_good_action_bundle_with_comparator_passes(self):
        ws,draft,job,review=self.example(intervention=True)
        validate_delivery_quality(ws,review,draft)
        self.receive(ws,job,review)
        ws.set_audit(job['id'])
        self.assertEqual(review['strategy_challenge']['verdict'],'conditional')

    def test_disputed_history_cannot_be_certified_as_observed(self):
        ws,draft,_,review=self.example()
        item=review['causal_boundary_reviews'][0]
        item['narrative_treatment']='as_supported'; item['evidence_grade']='direct_observation'
        with self.assertRaisesRegex(StateDyneError,'hypothesized'):
            validate_delivery_quality(ws,review,draft)

    def test_indirect_bridge_cannot_be_promoted(self):
        ws,draft,_,review=self.example()
        item=review['causal_boundary_reviews'][0]
        ws.state['claims'][item['claim_id']]['epistemic_status']='inference'
        item['narrative_treatment']='as_supported'; item['evidence_grade']='partial_indirect'
        with self.assertRaisesRegex(StateDyneError,'indirectly'):
            validate_delivery_quality(ws,review,draft)

    def test_missing_visible_causal_boundary_fails(self):
        ws,draft,_,review=self.example()
        review['causal_boundary_reviews'][0]['user_visible_limit']='A caveat not visible to the user.'
        with self.assertRaisesRegex(StateDyneError,'visible'):
            validate_delivery_quality(ws,review,draft)

    def test_review_cannot_drop_selected_causal_claim(self):
        ws,draft,_,review=self.example(intervention=True)
        review['causal_boundary_reviews']=review['causal_boundary_reviews'][:1]
        with self.assertRaisesRegex(StateDyneError,'exactly every selected'):
            validate_delivery_quality(ws,review,draft)

    def test_unselected_candidate_does_not_require_artificial_review(self):
        ws,draft,_,review=self.example(extra_unused=True)
        validate_delivery_quality(ws,review,draft)
        self.assertEqual(len(review['causal_boundary_reviews']),1)

    def test_conditional_mechanism_cannot_be_used_certainly(self):
        ws,draft,_,review=self.example()
        draft['claim_dispositions'][0]['treatment']='use'
        with self.assertRaisesRegex(StateDyneError,'certain'):
            validate_delivery_quality(ws,review,draft)

    def test_revision_request_cannot_pass(self):
        ws,draft,_,review=self.example()
        review['causal_boundary_reviews'][0]['narrative_treatment']='requires_revision'
        with self.assertRaisesRegex(StateDyneError,'requires actual revision'):
            validate_delivery_quality(ws,review,draft)

    def test_actions_must_all_be_covered(self):
        ws,draft,_,review=self.example(intervention=True)
        review['strategy_challenge']['selected_action_claim_ids']=[]
        with self.assertRaisesRegex(StateDyneError,'exactly'):
            validate_delivery_quality(ws,review,draft)

    def test_action_comparison_must_reach_user(self):
        ws,draft,_,review=self.example(intervention=True)
        review['strategy_challenge']['visible_comparison']='This line did not appear in the response.'
        with self.assertRaisesRegex(StateDyneError,'visible'):
            validate_delivery_quality(ws,review,draft)

    def test_extra_action_without_extra_value_cannot_pass(self):
        ws,draft,_,review=self.example(intervention=True)
        review['strategy_challenge']['verdict']='prefer_no_extra_action'
        with self.assertRaisesRegex(StateDyneError,'silently pass'):
            validate_delivery_quality(ws,review,draft)

    def test_empty_burden_analysis_cannot_pass(self):
        ws,draft,_,review=self.example(intervention=True)
        review['strategy_challenge']['overlap_or_monitoring_risk']=' '
        with self.assertRaisesRegex(StateDyneError,'overlap_or_monitoring_risk'):
            validate_delivery_quality(ws,review,draft)

    def test_no_actions_requires_no_strategy_challenge(self):
        ws,draft,_,review=self.example()
        review['strategy_challenge']['verdict']='additional_action_justified'
        with self.assertRaisesRegex(StateDyneError,'no action'):
            validate_delivery_quality(ws,review,draft)

    def test_skill_prompts_and_schema_share_two_gates(self):
        root=Path(__file__).resolve().parents[1]
        skill=(root/'SKILL.md').read_text('utf-8')
        prompt=(root/'references/operators/audit.md').read_text('utf-8')
        self.assertIn('因果晋级',skill)
        self.assertIn('动作经济学',skill)
        self.assertIn('causal_boundary_reviews',prompt)
        self.assertIn('strategy_challenge',prompt)
        self.assertIn('组内差异', (root/'references/recognition.md').read_text('utf-8'))
        self.assertIn('不增加新动作', (root/'references/action-economy.md').read_text('utf-8'))

if __name__=='__main__': unittest.main()
