"""10.25 relational-discovery and multi-turn navigation contracts.

These are deterministic engineering regressions, not real-model reasoning tests.
They use an unrelated shared-resource task as a negative control and contain
no case-specific personal history or preordained hidden mechanism.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sd_runtime.common import StateDyneError, digest
from sd_runtime.engine import Engine, instructions
from sd_runtime.schemas import SCHEMAS, validate
from sd_runtime.store import Workspace
from test_runtime import TASK,FixtureBackend


class DiscoveryArchitecture(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.ws=Workspace.create(Path(t.name)/'run', TASK, backend='fixture')

    def test_ten_raw_jobs_are_independent_and_same_source_boundary(self):
        engine=Engine(self.ws,FixtureBackend(self.ws))
        self.assertEqual(engine.advance()['assurance'],'simulation_only')
        roles=('frame','system_map','goal_scout','selection_scout','relation_scout',
               'discovery','reframe','contrast_probe','environment_scout','blind_challenge')
        jobs=[j for j in self.ws.state['jobs'].values() if j['role'] in roles]
        self.assertEqual(len(jobs),10)
        self.assertEqual({j['role'] for j in jobs},set(roles))
        inputs=[self.ws.job_request(j['id'])['inputs'] for j in jobs]
        self.assertEqual(len({digest(v) for v in inputs}),1)
        self.assertIn('关系',instructions('relation_scout'))
        self.assertIn('不同',instructions('relation_scout'))

    def test_abstract_relational_difference_without_forcing_mystery(self):
        intro=(ROOT/'references/relational-structure.md').read_text('utf8')
        self.assertIn('关系',intro)
        self.assertIn('不同',intro)
        self.assertIn('无增量',intro)
        # Case-specific names or explanations never become general workers' rules.
        for name in ('fixture-key-a','fixture-key-b','fixture-persona-a','fixture-persona-b','fixture-response-a'):
            self.assertNotIn(name,intro)
            self.assertNotIn(name,(ROOT/'references/operators/relation_scout.md').read_text('utf8'))

    def test_new_role_can_return_synthetic_null_without_fake_discovery(self):
        Engine(self.ws,FixtureBackend(self.ws)).advance()
        jobs=[j for j in self.ws.state['jobs'].values() if j['role']=='relation_scout']
        self.assertEqual(len(jobs),1)
        output=self.ws.result(jobs[0]['id'])['output']
        self.assertIn('no_increment_reason',output)
        self.assertTrue(output['no_increment_reason'])

    def test_composer_and_auditor_keep_all_relevant_rule_documents(self):
        for role in ('compose','audit'):
            text=instructions(role)
            for sub in ('关系结构', '接续', '干预', '目标', '实际选择'):
                self.assertIn(sub,text)


class NavigationAndSideQuestion(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.ws=Workspace.create(Path(t.name)/'run',TASK,backend='fixture',scope='points')
        self.backend=FixtureBackend(self.ws)
        self.engine=Engine(self.ws,self.backend)
        self.engine.advance()

    def test_audited_point_answer_has_real_navigation_and_persistence(self):
        nav=self.ws.state['draft']['output']['navigation']
        self.assertEqual(nav['mode'],'primary')
        self.assertEqual(nav['primary_stage'],'points')
        self.assertEqual(nav['next_stage'],'actions')
        self.assertIn(nav['visible_anchor'],self.ws.state['draft']['output']['answer'])
        self.assertEqual(self.engine.verify_release()['navigation'],nav)

    def test_draft_requires_navigation_schema(self):
        sample=deepcopy(self.ws.state['draft']['output'])
        sample.pop('navigation')
        with self.assertRaisesRegex(StateDyneError,'navigation'):
            validate(sample,SCHEMAS['draft'])

    def test_navigation_rejects_wrong_phase_and_unseen_next_offer(self):
        d=deepcopy(self.ws.state['draft']['output'])
        d['navigation']['primary_stage']='analysis'
        with self.assertRaisesRegex(StateDyneError,'last verified primary stage'):
            self.ws.check_navigation_contract(d)
        d=deepcopy(self.ws.state['draft']['output'])
        d['navigation']['next_stage']='plan'
        with self.assertRaisesRegex(StateDyneError,'incorrectly advanced'):
            self.ws.check_navigation_contract(d)
        d=deepcopy(self.ws.state['draft']['output'])
        d['answer']=d['answer'].replace(d['navigation']['visible_anchor'],'')
        with self.assertRaisesRegex(StateDyneError,'not present in the reviewed answer'):
            self.ws.check_navigation_contract(d)

    def test_side_answer_then_next_resumes_prior_points_without_repeating_raw_ten(self):
        first_ids={u['claim_id'] for u in self.ws.state['draft']['output']['delivery_units'] if u['kind']=='point'}
        self.assertTrue(first_ids)
        self.ws.update('What does the alternative explanation predict?',interaction='side_question')
        self.assertEqual(self.ws.state['scope'],'analysis')
        self.assertEqual(self.ws.state['interaction_mode'],'side')
        before=len([j for j in self.ws.state['jobs'].values() if j['role']=='relation_scout'])
        self.engine.advance()
        nav=self.ws.state['draft']['output']['navigation']
        self.assertEqual((nav['mode'],nav['primary_stage'],nav['next_stage']),('side','points','actions'))
        self.assertIn('next_offer',nav)
        self.assertEqual(self.ws.state['task_navigation']['last_primary_scope'],'points')
        self.assertEqual(self.ws.previously_delivered_interventions()['point'],first_ids)
        self.ws.continue_stage('next')
        self.assertEqual(self.ws.state['scope'],'actions')
        # A side question may bring fresh evidence; do not *force* stale
        # preflight reuse before its causal relevance is independently checked.
        self.engine.advance()
        nav=self.ws.state['draft']['output']['navigation']
        self.assertEqual((nav['mode'],nav['primary_stage'],nav['next_stage']),('primary','actions','plan'))
        self.assertEqual(before,len([j for j in self.ws.state['jobs'].values() if j['role']=='relation_scout']))
        self.assertEqual({u['kind'] for u in self.ws.state['draft']['output']['delivery_units']},{'action'})
        self.assertTrue(self.engine.verify_release())

    def test_side_question_does_not_recycle_prior_scheduler_job(self):
        initial_schedule=[j['id'] for j in self.ws.state['jobs'].values() if j['role']=='schedule']
        self.ws.update('A small request for clarification',interaction='side_question')
        self.engine.advance()
        current_schedule=[j['id'] for j in self.ws.state['jobs'].values() if j['role']=='schedule']
        self.assertGreater(len(current_schedule),len(initial_schedule))
        old_tags={self.ws.state['jobs'][i]['tag'] for i in initial_schedule}
        new_tags={self.ws.state['jobs'][i]['tag'] for i in current_schedule}
        self.assertTrue(new_tags-old_tags)

    def test_expand_after_side_question_retains_last_primary_points(self):
        point_ids={u['claim_id'] for u in self.ws.state['draft']['output']['delivery_units'] if u['kind']=='point'}
        self.ws.update('Could you clarify the current conclusion?',interaction='side_question')
        self.engine.advance()
        self.ws.expand_search('Look for a distinct more valuable lever')
        self.assertEqual(self.ws.state['expansion_target_scope'],'points')
        self.assertEqual(set(self.ws.state['expansion_base_point_ids']),point_ids)
        self.assertEqual(self.ws.state['interaction_mode'],'primary')

    def test_cli_offers_next_and_side_question(self):
        cli=(ROOT/'scripts/sd_runtime/cli.py').read_text('utf8')
        self.assertIn('--side-question',cli)
        self.assertIn('"next"',cli)

if __name__=='__main__':
    unittest.main()
