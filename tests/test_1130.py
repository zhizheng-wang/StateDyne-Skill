"""Outcome-tournament architecture: real-worker gate and anti-smoothing tests.

These are structural regressions, NOT live tests of creative intelligence.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from sd_runtime.backends import NativeBackend, write_result
from sd_runtime.common import StateDyneError
from sd_runtime.decision_tournament import (register_tournament,
    check_draft_against_tournament, tournament_signature)
from sd_runtime.engine import Engine, instructions
from sd_runtime.store import Workspace


def output(c1='C1',c2='C2',opening=False):
    def item(local,cid,other,verdict):
        return {'local_id':local,'claim_ids':[cid],'rival_claim_ids':[other],
                'generation_path':'The environment condition changes which decision-maker controls the result.',
                'distinct_prediction':'Without this rule the same product performance would lead to a different choice.',
                'evidence_boundary':'A conditional hypothesis based on reported contrast; the choice records are unavailable.',
                'implementation_path':'Identify decision rights and test the feasibility of an alternative entry.',
                'user_value_delta':'Could preserve maker time without postponing a real product experiment.',
                'compared_to_baseline':'The ordinary service-first route consumes more continuous founder labour.',
                'verdict':verdict,
                'why_this_disposition':'The condition could reverse the first recommendation and must remain explicit.'}
    return {'goal_at_stake':'Earn money while preserving control and creation time.',
        'comparison_basis':'Net outcome, real accessibility and controlled downside; never majority vote.',
        'entries':[item('J1',c1,c2,'preferred'),item('J2',c2,c1,'serious_rival')],
        'biggest_reversal_condition':'A partner will not allow retained IP or a bounded support obligation.',
        'no_independent_value_reason':'',
        'research_opening':{'needed':opening,
            'focus':'Check who signs procurement contracts and why performance does not convert to purchase' if opening else '',
            'expected_difference':'Contract-signature evidence would reverse an assumed buyer mechanism.' if opening else '',
            'evidence_route':'public_source' if opening else 'unavailable'}}


class OutcomeTournamentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.ws=Workspace.create(Path(self.temp.name)/'research', 'Investigate a complex decision.',backend='fixture')
        self.ws.state['claims']={'C1':{'id':'C1','kind':'mechanism','statement':'Partner-mediated payments', 'state':'current'},
                                 'C2':{'id':'C2','kind':'mechanism','statement':'Direct founder-delivered services','state':'current'}}
        self.ws.save('fixture_claims')
    def tearDown(self): self.temp.cleanup()

    def receipt(self, product=None, independent=True):
        job=self.ws.get_job('jury','decision_tournament','decision_tournament',
             self.ws.current_view(),instructions('decision_tournament'))
        write_result(self.ws.root,job,product or output(),kind='fixture',
                     worker_ref='independent-test-worker',actual_model='synthetic-fixture',
                     independent_context=independent)
        return job

    def test_jury_is_real_distinct_role_and_requires_true_receipt(self):
        job=self.ws.get_job('jury','decision_tournament','decision_tournament',
             self.ws.current_view(),instructions('decision_tournament'))
        with self.assertRaises(StateDyneError): register_tournament(self.ws,job['id'])
        self.ws.state['phase']='decision_tournament'
        answer=Engine(self.ws,NativeBackend(self.ws.root,self.ws.state['sources'],self.ws.state['config'])).advance()
        self.assertEqual(answer['status'],'waiting_for_real_workers')
        self.assertEqual(len(answer['jobs']),1)
        self.assertEqual(self.ws.job_request(answer['jobs'][0])['role'],'decision_tournament')

    def test_independent_context_must_be_real(self):
        job=self.receipt(independent=False)
        with self.assertRaises(StateDyneError): register_tournament(self.ws,job['id'])

    def test_minor_rival_cannot_disappear_in_final_answer(self):
        job=self.receipt()
        self.assertFalse(register_tournament(self.ws,job['id']))
        draft={'answer':'Partner-mediated payments may preserve ownership.',
               'claim_dispositions':[
                {'claim_id':'C1','treatment':'use',
                 'reason':'Partner-mediated payments may preserve ownership.'},
                {'claim_id':'C2','treatment':'not_selected',
                 'reason':'Direct service delivery might bring cash sooner but consume creation time.'}],
               'used_claim_ids':['C1']}
        with self.assertRaisesRegex(StateDyneError,'minority'):
            check_draft_against_tournament(self.ws,draft)
        draft['answer'] += ' Direct service delivery might bring cash sooner but consume creation time.'
        check_draft_against_tournament(self.ws,draft)

    def test_preferring_a_claim_requires_visible_value_reason(self):
        job=self.receipt(); register_tournament(self.ws,job['id'])
        draft={'answer':'Use C1.',
          'claim_dispositions':[
            {'claim_id':'C1','treatment':'use', 'reason':'This alternative changes who bears deployment risk and founder workload.'},
            {'claim_id':'C2','treatment':'reject', 'reason':'The rival needs personal delivery every time.'}],
          'used_claim_ids':['C1']}
        with self.assertRaisesRegex(StateDyneError,'user-visible'):
            check_draft_against_tournament(self.ws,draft)

    def test_new_material_relation_reopens_search_only_once(self):
        job=self.receipt(output(opening=True))
        self.assertTrue(register_tournament(self.ws,job['id']))
        opportunities=self.ws.state['exploration_opportunities']
        self.assertEqual(len(opportunities),1)
        self.assertTrue(register_tournament(self.ws,job['id']) is False)
        self.assertEqual(len(self.ws.state['exploration_opportunities']),1)

    def test_jury_evidence_is_routed_to_actual_acquisition(self):
        from sd_runtime.priority_dispatch import priority_batch
        job=self.receipt(output(opening=True))
        register_tournament(self.ws,job['id'])
        ids=list(self.ws.state['exploration_opportunities'])
        chosen=priority_batch(model_opportunities=ids, research_unknowns=[],
            evidence_reframes=[], opportunity_metadata=self.ws.state['exploration_opportunities'],
            capacity=1)
        self.assertEqual(chosen[0]['operator'],'acquire')
        self.assertEqual(chosen[0]['opportunity_ids'],ids)

    def test_invalid_competitor_reference_rejected(self):
        product=output(); product['entries'][0]['claim_ids']=['invented_id']
        job=self.receipt(product)
        with self.assertRaisesRegex(StateDyneError,'source-worker'):
            register_tournament(self.ws,job['id'])

    def test_changed_claim_content_forces_fresh_tournament(self):
        job=self.receipt(); register_tournament(self.ws,job['id'])
        previous=self.ws.state['decision_tournament']['signature']
        self.ws.state['claims']['C1']['statement']='A materially changed prediction'
        self.assertNotEqual(previous,tournament_signature(self.ws))


if __name__=='__main__':unittest.main()
