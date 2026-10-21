"""10.30 generative-search/continuation engineering regressions.

These tests verify *actual dispatched job boundaries and deliverable routing*.
The work contents are scripted negative controls, NOT tests of model brilliance.
No private personal case texts or expected real-world answers are stored here.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine
from sd_runtime.backends import write_result
from sd_runtime.common import StateDyneError
from sd_runtime.breakthrough import validate_breakthrough
from test_runtime import FixtureBackend, TASK, claim
from test_10290 import BranchBackend


class ActionsIntendedButSchedulerAnalyzes(FixtureBackend):
    def execute(self, job):
        if job['role'] != 'scope_intent':
            return super().execute(job)
        if self.ws.result(job['id']):
            return self.ws.result(job['id'])
        self.requests.append(deepcopy(job))
        latest=job['inputs']['task_sources'][-1]['text']
        # Independently cites the latest user request, never worker prose.
        quote='How can I fix the slowdown?' if 'How can I fix the slowdown?' in latest else ''
        result={
            'requested_scope':'actions' if quote else 'analysis',
            'request_basis':'explicit' if quote else 'missing',
            'user_request_quote':quote,
            'reason':'The user asks for a concrete correction in the task itself; a scheduler choosing analysis is not final authority.',
            'protected_user_objective':latest,
        }
        return write_result(self.ws.root, job, result, kind='fixture',
                            worker_ref=f'fixture-{job["id"]}',actual_model='scripted-fixture',
                            independent_context=True)


class GenerativeSearchTests(unittest.TestCase):
    def make_engine(self, *, task=TASK, scope='analysis', backend_cls=FixtureBackend, **opts):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        ws=Workspace.create(Path(tmp.name)/'run',task,scope=scope,backend='fixture')
        backend=backend_cls(ws,**opts)
        return ws, backend, Engine(ws,backend)

    def test_initial_blind_breakthrough_is_real_dispatched_job(self):
        ws,backend,eng=self.make_engine()
        released=eng.advance()
        self.assertEqual(released['status'],'complete')
        jobs=[j for j in backend.requests if j['role']=='breakthrough_scout']
        self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['schema_name'],'work')
        raw=jobs[0]['inputs']
        self.assertIn('task_sources',raw)
        self.assertNotIn('claims',raw)
        self.assertNotIn('goal_review',raw)
        self.assertNotIn('draft',raw)
        self.assertEqual(len(ws.state['breakthrough_receipts']),1)
        self.assertIn('breakthrough-raw',ws.state['jobs'][ws.state['breakthrough_receipts'][0]]['tag'])

    def test_breakthrough_source_is_not_intentionally_leaked_from_other_roles(self):
        ws,backend,eng=self.make_engine()
        eng.advance()
        blind=[x for x in backend.requests if x['role']=='breakthrough_scout'][0]
        incumbent=[x for x in backend.requests if x['role']=='frontier_scout'][0]
        self.assertNotIn('claims',blind['inputs'])
        self.assertIn('claims',incumbent['inputs'])
        self.assertNotEqual(blind['id'],incumbent['id'])

    def test_independent_scope_authority_runs_even_if_scheduler_finishes_analysis(self):
        task=TASK+' How can I fix the slowdown?'
        ws,backend,eng=self.make_engine(task=task,scope='auto',backend_cls=ActionsIntendedButSchedulerAnalyzes)
        released=eng.advance()
        self.assertEqual(released['status'],'complete')
        self.assertTrue([j for j in backend.requests if j['role']=='scope_intent'])
        self.assertEqual(ws.state['scope_intent']['requested_scope'],'actions')
        self.assertEqual(ws.state['delivery_scope'],'actions')
        kinds={x['kind'] for x in ws.state['draft']['output']['delivery_units']}
        self.assertIn('point',kinds)
        self.assertIn('action',kinds)

    def test_a_request_just_to_understand_does_not_force_action(self):
        ws,backend,eng=self.make_engine(scope='auto',backend_cls=ActionsIntendedButSchedulerAnalyzes)
        self.assertEqual(eng.advance()['status'],'complete')
        self.assertEqual(ws.state['delivery_scope'],'analysis')
        self.assertFalse([x for x in ws.state['draft']['output']['delivery_units'] if x['kind'] in ('point','action')])

    def test_expansion_searches_inside_and_outside_model_concurrently(self):
        ws,backend,eng=self.make_engine(scope='points',backend_cls=BranchBackend,route='expand')
        self.assertEqual(eng.advance()['status'],'complete')
        ws.expand_search('Investigate a competing upstream institution')
        self.assertEqual(eng.advance()['status'],'complete')
        expanded=[j for j in backend.requests if j['role']=='open_search']
        blind=[j for j in backend.requests if j['role']=='breakthrough_scout' and 'expand' in j['tag']]
        self.assertEqual(len(expanded),1)
        self.assertEqual(len(blind),1)
        self.assertEqual(expanded[0]['inputs']['expansion_focus'],'Investigate a competing upstream institution')
        self.assertIn('claims',expanded[0]['inputs'])
        self.assertNotIn('claims',blind[0]['inputs'])
        self.assertEqual(blind[0]['inputs']['expansion_focus'],'Investigate a competing upstream institution')
        self.assertTrue(ws.state['expansion_runs'][-1]['blind_job_id'])

    def test_refusal_keeps_primary_goal_and_reruns_independent_value_search(self):
        ws,backend,eng=self.make_engine(scope='points')
        self.assertEqual(eng.advance()['status'],'complete')
        before=len([j for j in backend.requests if j['role']=='value_frontier'])
        ws.receive_user_turn('我不想再提供私人细节，请自行继续研究')
        self.assertEqual(eng.advance()['status'],'complete')
        after=len([j for j in backend.requests if j['role']=='value_frontier'])
        self.assertGreater(after,before)
        self.assertFalse(ws.state['task_thread']['force_independent_continuation'])
        self.assertEqual(ws.state['task_thread']['user_input_policy'],'no_repeated_questions_without_invitation')
        self.assertEqual(ws.state['task_navigation']['last_primary_scope'],'points')

    def test_refusal_frontier_preserves_user_unavailable_conditions(self):
        ws,backend,eng=self.make_engine(scope='analysis',with_unknown=True)
        self.assertIn(eng.advance()['status'],('complete','needs_information'))
        ws.state['task_thread']['user_input_policy']='no_repeated_questions_without_invitation'
        frontier=ws.research_frontier()
        if any(x['kind']=='discriminator' and x['route']=='user' for x in frontier):
            self.fail('User-declined question must never be required as a route')

    def test_null_breakthrough_without_real_search_reason_fails(self):
        class Stub:
            def result(self,j):return {'output':{'claims':[],'unknowns':[],'opportunities':[],'no_increment_reason':'Nothing new'}}
        with self.assertRaises(StateDyneError):
            validate_breakthrough(Stub(),'fake')

    def test_novel_label_without_distinguishing_prediction_fails(self):
        c=claim();c['distinct_consequences']=[]
        class Stub:
            def result(self,j):return {'output':{'claims':[c],'unknowns':[],'opportunities':['Look for proof'], 'no_increment_reason':''}}
            def active_claims(self):return {}
        with self.assertRaises(StateDyneError):
            validate_breakthrough(Stub(),'fake')

    def test_reworded_claim_same_identity_is_not_accepted_as_two_breakthroughs(self):
        c=claim();c2=deepcopy(c);c2['local_id']='M2'
        class Stub:
            def result(self,j):return {'output':{'claims':[c,c2],'unknowns':[], 'opportunities':['Investigate outcome'], 'no_increment_reason':''}}
            def active_claims(self):return {}
        with self.assertRaises(StateDyneError):
            validate_breakthrough(Stub(),'fake')

    def test_every_active_package_has_exactly_one_skill_entry(self):
        self.assertEqual([p.relative_to(ROOT).as_posix() for p in ROOT.rglob('SKILL.md') if p.is_file()],['SKILL.md'])
        self.assertTrue((ROOT/'engineering/history/10.27.0/archived-entry-10.27.md').is_file())
        self.assertTrue((ROOT/'references/breakthrough-engine.md').is_file())
        self.assertTrue((ROOT/'references/operators/breakthrough_scout.md').is_file())

if __name__ == '__main__':
    unittest.main()
