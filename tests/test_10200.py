"""10.20.0 deterministic regressions, not LLM semantic or intervention proof."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.backends import write_result
from sd_runtime.load_bearing import check_draft_against_load_bearing
from sd_runtime.common import StateDyneError
from test_10190 import PivotalRobustnessTest
from test_runtime import TASK, work

ROOT=Path(__file__).resolve().parents[1]

class IncrementalityBridgeTests(unittest.TestCase):
    def setUp(self):
        # Reuse the verified synthetic infrastructure, not its unittest suite.
        helper=PivotalRobustnessTest('test_valid_pivotal_forecast_sensitivity_accepted')
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.helper=helper
        self.cid=helper.cid

    def payload(self):
        obj=self.helper.payload(role='intervention')
        obj['tests'][0]['quantified_incremental_claim']=True
        obj['robustness_checks']=[self.helper.stress('incrementality_counterfactual')]
        return obj

    def net(self,known=True):
        return {'local_id':'N1','claim_ids':[self.cid],
           'status':'reconciled' if known else 'counterfactual_unavailable',
           'gross_with_program':'6000',
           'gross_without_program':'2500' if known else '',
           'displaced_or_transferred':'500' if known else '',
           'stated_net_increment':'3000' if known else '',
           'absolute_tolerance':'0' if known else '',
           'unit':'completed qualifying units over five years',
           'input_basis':'All numbers are synthetic conditional examples, not actual policy inputs.',
           'visible_limit':'净新增要扣除无方案基线和转移效应；没有真实基线不能把交付总量当成净增。'}

    def test_quantified_claim_needs_explicit_net_bridge(self):
        with self.assertRaisesRegex(StateDyneError,'reconcile gross'):
            self.helper.register(self.payload())

    def test_valid_synthetic_net_bridge_is_arithmetically_recomputed(self):
        obj=self.payload();obj['net_effect_checks']=[self.net()]
        self.helper.register(obj)
        row=self.helper.ws.state['load_bearing_audit']['net_effect_checks'][0]
        self.assertEqual(row['computed_net_increment'],3000)
        self.assertTrue(row['arithmetic_only'])

    def test_gross_mislabeled_as_net_is_rejected(self):
        obj=self.payload();wrong=self.net();wrong['stated_net_increment']='6000'
        obj['net_effect_checks']=[wrong]
        with self.assertRaisesRegex(StateDyneError,'does not reconcile'):
            self.helper.register(obj)

    def test_no_counterfactual_can_yield_only_conditional_claim(self):
        obj=self.payload();obj['net_effect_checks']=[self.net(False)]
        self.helper.register(obj)
        row=self.helper.ws.state['load_bearing_audit']['net_effect_checks'][0]
        self.assertIsNone(row['computed_net_increment'])
        draft={'answer':'The proposed program could expand deliveries. '+self.helper.stress('incrementality_counterfactual')['visible_limit'],
               'claim_dispositions':[{'claim_id':self.cid,'treatment':'use'}]}
        with self.assertRaisesRegex(StateDyneError,'unknown net baseline'):
            check_draft_against_load_bearing(self.helper.ws,draft)
        draft['answer']+=' '+row['visible_limit']
        check_draft_against_load_bearing(self.helper.ws,draft)

    def test_unknown_counterfactual_cannot_claim_net_number(self):
        obj=self.payload();wrong=self.net(False);wrong['stated_net_increment']='4000'
        obj['net_effect_checks']=[wrong]
        with self.assertRaisesRegex(StateDyneError,'cannot carry'):
            self.helper.register(obj)

    def test_not_quantified_intervention_preserves_old_workflow(self):
        obj=self.payload();obj['tests'][0]['quantified_incremental_claim']=False
        self.helper.register(obj)
        self.assertEqual(self.helper.ws.state['load_bearing_audit']['net_effect_checks'],[])

class EvidenceReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.ws=Workspace.create(Path(self.tmp.name)/'case', TASK, backend='fixture',scope='analysis')
        self.ws.state.update(phase='schedule',sweep_complete=True,
             portfolio_complete=True, blind_complete=True,
             entry_review={'output':{'verdict':'pass'}}, operations_done=0)

    def test_pending_actual_acquisition_changes_next_operation(self):
        self.ws.state['pending_evidence_reframes']=[{
            'acquire_job':'J0101','claim_ids':[], 'unknown_ids':['J0099:U1']}]
        class Backend:
            def execute(self,job):
                if job['role']=='reframe_informed':
                    self.hit=job
                    raise StateDyneError('REOPEN_AFTER_EVIDENCE')
                raise StateDyneError('WRONG_FIRST_OPERATION')
        backend=Backend()
        with self.assertRaisesRegex(StateDyneError,'REOPEN_AFTER_EVIDENCE'):
            Engine(self.ws,backend).advance()
        self.assertEqual(backend.hit['inputs']['operation'],'reframe')
        self.assertEqual(backend.hit['inputs']['requested_difference'],
            'An updated mechanism, unreported cross-context prediction or evidence-grounded null result, not merely an appended citation.')
        self.assertEqual(self.ws.state['pending_evidence_reframes'][0]['acquire_job'],'J0101')

    def test_new_real_acquisition_claim_forces_revisit_not_only_report(self):
        self.ws.state['phase']='operate'
        self.ws.state['decisions']=[{'operator':'acquire','target_ids':[],
            'opportunity_ids':[], 'expected_difference':'Check new information',
            'rationale':'Synthetic fixture', 'strongest_alternative':'Nothing changes',
            'why_parallel_safe':''}]
        class Backend:
            def __init__(self,ws):self.ws=ws
            def execute(self,job):
                if job['role']=='acquire':
                    output=work()
                    return write_result(self.ws.root,job,output,kind='fixture',
                        worker_ref=f'acquire-{job["id"]}',actual_model='synthetic-fixture')
                if job['role']=='reframe_informed':
                    self.hit=job
                    raise StateDyneError('ACQUIRED_CLAIM_REOPENED')
                raise StateDyneError('Wrong worker after acquiring evidence')
        backend=Backend(self.ws)
        with self.assertRaisesRegex(StateDyneError,'ACQUIRED_CLAIM_REOPENED'):
            Engine(self.ws,backend).advance()
        self.assertTrue(self.ws.state['pending_evidence_reframes'])
        self.assertEqual(len(backend.hit['inputs']['targets']),1)

    def test_revisit_ledger_consumes_only_actual_completed_triggers(self):
        self.ws.state['phase']='operate'
        self.ws.state['pending_evidence_reframes']=[
            {'acquire_job':'J1','claim_ids':[],'unknown_ids':[]},
            {'acquire_job':'J2','claim_ids':[],'unknown_ids':[]}]
        self.ws.state['decisions']=[{'operator':'reframe','target_ids':[],
            'opportunity_ids':[],'expected_difference':'Revisit',
            'evidence_trigger_ids':['J1']}]
        class Backend:
            def __init__(self,ws):self.ws=ws;self.count=0
            def execute(self,job):
                if job['role']=='reframe_informed':
                    self.count+=1
                    if self.count==2:
                        raise StateDyneError('STOP_AFTER_REVISIT')
                    result=work(claims=[],unknowns=[])
                    result['opportunities']=[]
                    result['no_increment_reason']='The synthetic data did not distinguish alternatives.'
                    return write_result(self.ws.root,job,result,kind='fixture',
                        worker_ref=f'reframe-{job["id"]}',actual_model='fixture')
                raise StateDyneError('STOP_AFTER_REVISIT')
        with self.assertRaisesRegex(StateDyneError,'STOP_AFTER_REVISIT'):
            Engine(self.ws,Backend(self.ws)).advance()
        self.assertEqual([r['acquire_job'] for r in self.ws.state['pending_evidence_reframes']],['J2'])

class KnowledgeDisciplineTests(unittest.TestCase):
    def test_first_wave_inference_not_hardcoded_private_history(self):
        skill=(ROOT/'SKILL.md').read_text(encoding='utf8')
        guide=(ROOT/'references/inference-and-discovery.md').read_text(encoding='utf8')
        self.assertIn('用户补充之前',skill)
        self.assertIn('用户披露该事实之前',guide)
        self.assertIn('另一类现实',guide)
        self.assertIn('证据缺失',guide)
    def test_public_loop_and_strong_rivals_preserved(self):
        text=(ROOT/'references/autonomous-evidence-loop.md').read_text(encoding='utf8')
        for key in ('一手财报','交叉核对','新的模型','净新增','条件预测'):
            self.assertIn(key,text)

if __name__=='__main__':unittest.main()
