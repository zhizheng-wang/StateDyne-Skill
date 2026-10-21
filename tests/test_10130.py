"""Domain-independent 10.13 protocol tests, not evidence of LLM reasoning quality."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from test_runtime import TASK, FixtureBackend, work
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.backends import write_result
from sd_runtime.load_bearing import (register_load_bearing, snapshot_signature,
                                    check_draft_against_load_bearing)
from sd_runtime.inquiry_frontier import discovery_inquiries, pending_self_research
from sd_runtime.common import StateDyneError


class BurdenChecks(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.ws=Workspace.create(Path(d.name)/'case',TASK,backend='fixture')
        rawjob=self.ws.get_job('raw-candidate','discovery','work',self.ws.raw_view(),instructions('discovery'))
        write_result(self.ws.root,rawjob,work(),kind='fixture',worker_ref='raw-fx',actual_model='fixture')
        self.ws.merge_work(rawjob['id'])
        self.cid=next(iter(self.ws.active_claims()))

    def payload(self):
        return {'thesis_at_risk':'Shared lock is responsible for the concurrent slowdown.',
            'as_of_scope':'No historical cutoff was specified.',
            'as_of_handling':'Synthetic task has no dated sources or forward facts.',
            'examined_claim_ids':[self.cid],
            'tests':[{'local_id':'T1','claim_ids':[self.cid],
                'proposition':'Lock contention is not uniquely proven by concurrent slowdown.',
                'role':'causal_bridge','support':'conditional', 'evidence':[],
                'importance':'critical','hidden_premise':'Both processes use one lock.',
                'strongest_rival':'Remote upstream queue serializes the requests.',
                'differentiated_outcome':'Bypassing the local lock does not remove the delay.',
                'decisive_test':'Compare lock occupancy and remote queue wait in overlapping runs.',
                'route':'materials','disposition':'retain',
                'reason':'The overlap observation alone cannot establish a local lock.',
                'quantified_incremental_claim':False}],
            'recalculations':[], 'robustness_checks':[], 'net_effect_checks':[],
            'best_countermodel':'An external scheduler can create identical timing behavior.',
            'decision_reversal':'Remote queue saturation would reverse the local lock repair decision.',
            'discovery_limit':'There is no actual lock or network trace in these materials.'}

    def register(self,payload,tag='load-check'):
        job=self.ws.get_job(tag,'load_bearing','load_bearing',self.ws.current_view(),instructions('load_bearing'))
        write_result(self.ws.root,job,payload,kind='fixture',worker_ref='auditor-'+tag,actual_model='fixture')
        register_load_bearing(self.ws,job['id'])
        return job

    def test_architecture_requires_distinct_semantic_challenge(self):
        instructions_text=instructions('load_bearing')
        for keyword in ('反事实', '口径', 'as-of', '计算复现', 'hidden'):
            if keyword=='hidden':
                self.assertIn('hidden_premise',(Path(__file__).resolve().parents[1]/'scripts/sd_runtime/schemas.py').read_text())
            else:
                self.assertIn(keyword,instructions_text)

    def test_conditional_challenge_is_traceable_not_claimed_as_fact(self):
        job=self.register(self.payload())
        audit=self.ws.state['load_bearing_audit']
        self.assertEqual(audit['job_id'],job['id'])
        self.assertEqual(audit['signature'],snapshot_signature(self.ws))
        self.assertEqual(audit['tests'][0]['support'],'conditional')
        self.assertEqual(self.ws.state['load_bearing_history'][-1]['new_unknown_ids'],[])

    def test_unverified_pivotal_premise_generates_real_research_task(self):
        p=self.payload()
        t=p['tests'][0]
        t.update(support='unsupported',disposition='investigate',route='calculation')
        job=self.register(p)
        uid=f'{job["id"]}:T1'
        u=self.ws.state['unknowns'][uid]
        self.assertEqual(u['priority'],'blocking')
        self.assertEqual(u['origin'],'load_bearing')
        self.assertEqual(u['related_claims'],[self.cid])
        self.assertIn(uid,[v['unknown_id'] for v in discovery_inquiries(self.ws)])
        self.assertIn(uid,pending_self_research(self.ws))

    def test_arithmetic_is_recomputed_with_tolerance_and_unit(self):
        p=self.payload()
        p['recalculations']=[{'local_id':'N1','claim_ids':[self.cid],
            'expression':'(18-15)/15*100','stated_result':'20.0',
            'absolute_tolerance':'0.01','unit':'percent',
            'input_basis':'Hypothetical numbers are used only to test arithmetic.',
            'evidence':[],'interpretation_limit':'Arithmetic does not prove why a system slowed down.'}]
        self.register(p)
        receipt=self.ws.state['load_bearing_audit']['recalculations'][0]
        self.assertAlmostEqual(receipt['computed_result'],20)
        self.assertTrue(receipt['arithmetic_only'])

    def test_arithmetic_mismatch_blocks_without_publishing(self):
        p=self.payload()
        p['recalculations']=[{'local_id':'N1','claim_ids':[self.cid],
            'expression':'(18-15)/15*100','stated_result':'25',
            'absolute_tolerance':'0.01','unit':'percent',
            'input_basis':'Hypothetical input values.', 'evidence':[],
            'interpretation_limit':'Arithmetic says nothing about source correctness.'}]
        with self.assertRaisesRegex(StateDyneError,'not reproduced'):
            self.register(p)
        self.assertIsNone(self.ws.state['load_bearing_audit'])

    def test_anchored_without_actual_source_rejected(self):
        p=self.payload()
        p['tests'][0]['support']='anchored'
        with self.assertRaisesRegex(StateDyneError,'unsupported assertion'):
            self.register(p)

    def test_unknown_source_reference_rejected(self):
        p=self.payload()
        p['tests'][0]['evidence']=[{'source_id':'S900','quote':'Imaginary quote'}]
        with self.assertRaisesRegex(StateDyneError,'Source/quote mismatch'):
            self.register(p)

    def test_bad_claim_reference_rejected(self):
        p=self.payload()
        p['tests'][0]['claim_ids']=['fake:claim']
        with self.assertRaisesRegex(StateDyneError,'stale or invented'):
            self.register(p)

    def test_false_factual_confidence_fails(self):
        p=self.payload()
        p['tests'][0].update(support='unsupported',disposition='retain')
        with self.assertRaisesRegex(StateDyneError,'Unsupported evidence'):
            self.register(p)

    def test_rejected_claim_must_not_reappear_as_established(self):
        p=self.payload()
        p['tests'][0].update(support='contradicted',disposition='reject')
        self.register(p)
        with self.assertRaisesRegex(StateDyneError,'silently used'):
            check_draft_against_load_bearing(self.ws,{'claim_dispositions':[
                {'claim_id':self.cid,'treatment':'use'}],'answer':'The lock is proven.'})

    def test_conditional_claim_requires_visible_reason(self):
        p=self.payload()
        p['tests'][0].update(support='unsupported',disposition='downgrade')
        self.register(p)
        with self.assertRaisesRegex(StateDyneError,'visible risk'):
            check_draft_against_load_bearing(self.ws,{'claim_dispositions':[
                {'claim_id':self.cid,'treatment':'conditional'}], 'answer':'Lock might be involved.'})
        check_draft_against_load_bearing(self.ws,{'claim_dispositions':[
            {'claim_id':self.cid,'treatment':'conditional'}],
            'answer':'Lock might be involved. '+p['tests'][0]['reason']})

    def test_probe_review_precedes_first_entry_review(self):
        # Real model workers are not simulated as evidence here; the fixture
        # checks stage order, not the model's ability to find a new mechanism.
        fresh=Workspace.create(Path(self.ws.root.parent)/'end-to-end',TASK,backend='fixture')
        backend=FixtureBackend(fresh)
        result=Engine(fresh,backend).advance()
        self.assertEqual(result['assurance'],'simulation_only')
        roles=[j['role'] for j in backend.requests]
        self.assertLess(roles.index('probe_portfolio'),roles.index('load_bearing'))
        self.assertLess(roles.index('load_bearing'),roles.index('entry_review'))
        self.assertGreaterEqual(roles.count('load_bearing'),1)
        self.assertEqual(fresh.state['load_bearing_audit']['signature'],snapshot_signature(fresh))

    def test_important_external_evidence_is_not_sent_to_user_by_default(self):
        p=self.payload()
        p['tests'][0].update(support='unsupported',disposition='investigate',route='public_source')
        job=self.register(p)
        uid=f'{job["id"]}:T1'
        self.assertNotIn(uid,pending_self_research(self.ws))
        self.ws.state['config']['web_search_enabled']=True
        self.assertIn(uid,pending_self_research(self.ws))

    def test_missing_reviewed_claim_id_is_a_real_audit_failure(self):
        p=self.payload()
        p['examined_claim_ids']=[]
        with self.assertRaisesRegex(StateDyneError,'inspect every active'):
            self.register(p)

    def test_duplicate_reviewed_claims_cannot_fake_coverage(self):
        p=self.payload()
        p['examined_claim_ids']=[self.cid,self.cid]
        with self.assertRaisesRegex(StateDyneError,'inspect every active'):
            self.register(p)

    def test_repeated_same_inquiry_is_not_asked_twice_under_new_job_id(self):
        p=self.payload()
        p['tests'][0].update(support='unsupported',disposition='investigate',route='user')
        first=self.register(p,'first')
        first_uid=f'{first["id"]}:T1'
        self.register(p,'second')
        self.assertEqual([x for x in self.ws.state['unknowns'] if x.endswith(':T1')],[first_uid])
        self.assertEqual(self.ws.state['unknowns'][first_uid]['state'],'open')

    def test_raw_new_claim_requires_fresh_premise_audit(self):
        self.register(self.payload())
        old=snapshot_signature(self.ws)
        job=self.ws.get_job('other-candidate','reframe','work',self.ws.raw_view(),instructions('reframe'))
        from test_runtime import claim
        extra=work([claim('New')])
        write_result(self.ws.root,job,extra,kind='fixture',worker_ref='second-raw',actual_model='fixture')
        self.ws.merge_work(job['id'])
        self.assertNotEqual(snapshot_signature(self.ws),old)

    def test_time_scope_changed_claim_or_sources_requires_fresh_audit(self):
        self.register(self.payload())
        old=snapshot_signature(self.ws)
        self.ws.add_source('New response','A new independent timing measurement',kind='user_reported',precision='as_reported')
        self.assertNotEqual(snapshot_signature(self.ws),old)
        self.assertNotEqual(self.ws.state['load_bearing_audit']['signature'],snapshot_signature(self.ws))


if __name__=='__main__':
    unittest.main()
