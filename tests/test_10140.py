"""10.14 structural tests. All scenarios are synthetic; no user private case facts."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import unittest
from copy import deepcopy

from sd_runtime.backends import write_result
from sd_runtime.common import StateDyneError
from sd_runtime.engine import Engine, instructions
from sd_runtime.frontstage import validate_frontstage
from sd_runtime.inquiry_frontier import validate_inquiry_dispositions, discovery_inquiries
from sd_runtime.probe_portfolio import register_portfolio
from fixture_helpers_10190 import search_for
from sd_runtime.store import Workspace
from sd_runtime.schemas import validate, SCHEMAS
from test_runtime import work, TASK


class IntentBackend:
    def __init__(self, ws, response):
        self.ws, self.response, self.calls = ws, response, 0
    def execute(self, job):
        self.calls += 1
        if job['role'] != 'scope_intent':
            raise RuntimeError('Only the narrow source-only intent reviewer is allowed')
        return write_result(self.ws.root, job, self.response,
                            kind='fixture', worker_ref=f'intent-review-{self.calls}',
                            actual_model='test-fixture')


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
    def setup_engine(self, task, scope, response):
        ws = Workspace.create(Path(self.temp.name)/'case', task, scope=scope, backend='fixture')
        backend = IntentBackend(ws, response)
        return ws, Engine(ws, backend), backend
    def response(self, stage, basis, quote):
        return {'requested_scope':stage, 'request_basis':basis,
                'user_request_quote':quote, 'reason':'Source-only inspection of what this speaker requested.',
                'protected_user_objective':'Preserve the actual requested outcome.'}

    def test_auto_analysis_also_requires_the_independent_stage_review(self):
        # 10.30: refusing to check user intent for a proposed analysis was a bug.
        ws, engine, backend = self.setup_engine('What explains this pattern?', 'auto',
                                                self.response('analysis','explicit','What explains'))
        scope, pending = engine.resolve_auto_stage('analysis', 'Current results justify another question')
        self.assertEqual((scope, pending), ('analysis', None))
        self.assertEqual(backend.calls, 1)

    def test_vague_interest_does_not_authorize_point_stage(self):
        ws, engine, backend = self.setup_engine('I want to understand what happened.', 'auto',
                                                self.response('analysis','implicit',''))
        scope, pending = engine.resolve_auto_stage('points', 'A candidate was found')
        self.assertEqual((scope, pending), ('analysis', None))
        self.assertEqual(backend.calls, 1)
        self.assertEqual(ws.state['scope_intent']['request_basis'],'implicit')
        # A second scheduler request reuses the same source-only intention review.
        self.assertEqual(engine.resolve_auto_stage('plan','A later scheduler insists on a plan')[0], 'analysis')
        self.assertEqual(backend.calls, 1)

    def test_real_explicit_user_action_approved_with_actual_quote(self):
        text = 'Please explain the defect. Then show me concrete steps to repair it.'
        ws, engine, backend = self.setup_engine(text, 'auto',
                                    self.response('actions','explicit','show me concrete steps to repair it'))
        self.assertEqual(engine.resolve_auto_stage('points','Old candidate wrote points')[0], 'actions')
        self.assertEqual(ws.state['scope_intent']['user_request_quote'], 'show me concrete steps to repair it')

    def test_hallucinated_user_quote_rejected(self):
        ws, engine, backend = self.setup_engine('Find the cause, please.', 'auto',
                                    self.response('plan','explicit','Please produce a training plan'))
        with self.assertRaisesRegex(StateDyneError, 'latest user turn'):
            engine.resolve_auto_stage('plan', 'Seemed useful')

    def test_old_intervention_request_does_not_override_latest_explanation_request(self):
        ws, engine, backend = self.setup_engine('Please give me a complete plan.', 'auto',
                                    self.response('plan','explicit','Please give me a complete plan.'))
        ws.add_source('Latest turn', 'Now please only explain the new observation.',
                      kind='user_reported',precision='as_reported',is_task=True)
        with self.assertRaisesRegex(StateDyneError, 'latest user turn'):
            engine.resolve_auto_stage('plan','Prior plan intention should not leak into the new turn')

    def test_explicit_scope_is_never_vetoed(self):
        ws, engine, backend = self.setup_engine('Explain it.', 'actions',
                                                 self.response('analysis','missing',''))
        self.assertEqual(engine.resolve_auto_stage('actions','Explicit configuration')[0], 'actions')
        self.assertEqual(backend.calls, 0)

    def test_update_clears_old_intent(self):
        ws, engine, backend = self.setup_engine('How should we change the system?', 'auto',
                                            self.response('actions','explicit','How should we change the system?'))
        engine.resolve_auto_stage('actions', 'User explicitly requested changing it')
        self.assertTrue(ws.state.get('scope_intent'))
        ws.update('New information changes the goal.', scope='analysis')
        self.assertIsNone(ws.state.get('scope_intent'))


class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Workspace.create(Path(self.temp.name)/'case',TASK,backend='fixture')
        source_job=self.ws.get_job('initial-representation','reframe','work',self.ws.raw_view(),instructions('reframe'))
        write_result(self.ws.root, source_job, work(), kind='fixture',worker_ref='first-worker',actual_model='fixture')
        self.ws.merge_work(source_job['id'])
        self.cid=next(iter(self.ws.active_claims()))

    def probe(self, **kwargs):
        item = {'local_id':'R1', 'claim_ids':[self.cid], 'model_gap':'',
                'question':'Does a remote queue create the latency even without shared resources?',
                'unreported_outcome':'The remote queue delays independent requests even when local tasks are quiet.',
                'rival_outcome':'Latency vanishes when local resource sharing stops.',
                'why_distinguishes':'An external bottleneck produces delay without local contention.',
                'recognition_prompt':'Besides these two tasks, have you ever seen an independent request wait when local activity was low? No or unsure is useful too.',
                'counter_cue':'If every delay disappears as soon as shared local work stops, the queue account is weaker.',
                'route':'user', 'importance':'important', 'advance':True,
                'reason':'This discriminates an external queue from a local resource conflict.'}
        item.update(kwargs)
        return item

    def register(self,item):
        job=self.ws.get_job('recognition-review','probe_portfolio','probe_portfolio',self.ws.current_view(),instructions('probe_portfolio'))
        write_result(self.ws.root,job,{'covered_representation':'Compared local and external waiting.',
                     'probes':[item],'exploration_attempts':search_for([item]),'null_search_reason':''},
                     kind='fixture',worker_ref='portfolio-worker',actual_model='fixture')
        register_portfolio(self.ws,job['id'])
        return f"{job['id']}:Q1"

    def test_user_memory_probe_preserved_for_composer(self):
        qid=self.register(self.probe())
        unknown=self.ws.state['unknowns'][qid]
        self.assertEqual(unknown['recognition_prompt'],self.probe()['recognition_prompt'])
        self.assertEqual(discovery_inquiries(self.ws)[0]['counter_cue'],self.probe()['counter_cue'])
        self.assertEqual(discovery_inquiries(self.ws)[0]['route'],'user')

    def test_user_cannot_be_sent_just_technical_discriminator(self):
        qid=self.register(self.probe())
        draft={'claim_dispositions':[{'claim_id':self.cid,'treatment':'conditional','reason':'Candidate not verified'}],
                'information_dispositions':[{'unknown_id':qid,'treatment':'ask',
                  'visible_question':self.probe()['question'], 'evidence':[],
                  'decision_effect':'changes_prediction','fallback_if_unknown':''}],
               'status':'needs_information','answer':self.probe()['question'],
               'question_payoff':{'covered_groups':[], 'evidence_gained':'', 'still_unknown':'', 'answer_anchor':''},
               'question_groups':[{'group_id':'G1','unknown_ids':[qid],
                 'analytic_purpose':'区分自主回忆的新现象与当前旧解释所作的不同预测。',
                 'if_first':'如果有跨情境的反差，则检查新的解释关系。',
                 'if_second':'如果完全没有类似反差，则削弱这条新猜想。',
                 'if_unknown':'如果没有可靠回忆，则维持条件性解释而不强行否定。'}]}
        with self.assertRaisesRegex(StateDyneError,'natural language'):
            validate_inquiry_dispositions(self.ws,draft)
        draft['information_dispositions'][0]['visible_question']=self.probe()['recognition_prompt']
        draft['answer']=self.probe()['recognition_prompt']
        with self.assertRaisesRegex(StateDyneError,'counter-cue'):
            validate_inquiry_dispositions(self.ws,draft)
        draft['answer'] = draft['answer'] + ' ' + self.probe()['counter_cue']
        validate_inquiry_dispositions(self.ws,draft)

    def test_unreported_result_cannot_be_stated_as_a_questionless_recollection(self):
        p=self.probe(recognition_prompt='It definitely happened when nobody used the shared lock.')
        with self.assertRaisesRegex(StateDyneError,'must be a question'):
            self.register(p)

    def test_question_must_offer_nonempty_counterhypothesis(self):
        p=self.probe(counter_cue='')
        with self.assertRaisesRegex(StateDyneError,'counter-cue'):
            self.register(p)

    def test_technical_copy_is_not_a_natural_recollection_prompt(self):
        p=self.probe(recognition_prompt=self.probe()['question'])
        with self.assertRaisesRegex(StateDyneError,'expand a technical discriminator'):
            self.register(p)

    def test_public_research_does_not_require_personal_recollection(self):
        self.register(self.probe(route='public_source',recognition_prompt='',counter_cue=''))
        self.assertEqual(next(iter(self.ws.state['unknowns'].values()))['recognition_prompt'], '')
        # It is still an ordinary self-research information task.
        self.assertEqual(next(iter(self.ws.state['unknowns'].values()))['route'],'public_source')


class FrontstageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
    def test_prose_does_not_leak_internal_identifiers(self):
        ws=Workspace.create(Path(self.temp.name)/'prose','Why does the service fail?',backend='fixture')
        with self.assertRaisesRegex(StateDyneError,'internal'):
            validate_frontstage(ws, {'answer':'The load_bearing_audit says there is a model_gap.'})
        validate_frontstage(ws,{'answer':'The upstream queue may be blocking requests.'})
    def test_actual_code_debugging_may_show_identifiers(self):
        ws=Workspace.create(Path(self.temp.name)/'code','请帮我审计代码：probe_portfolio',backend='fixture')
        validate_frontstage(ws, {'answer':'The probe_portfolio has no such record.'})
    def test_skill_has_frontstage_and_source_only_scope(self):
        root=Path(__file__).resolve().parents[1]
        skill=(root/'SKILL.md').read_text('utf-8')
        self.assertIn('自然发现与回忆唤起',skill)
        self.assertIn('前台翻译',skill)
        self.assertIn('独立原话意图核对',skill)
        self.assertIn('没有／记不清',skill)
        self.assertIn('自然', (root/'references/operators/probe_portfolio.md').read_text('utf-8'))

if __name__=='__main__':
    unittest.main()
