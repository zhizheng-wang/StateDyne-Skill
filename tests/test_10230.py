"""10.23: backstage action preview, cached stage transition, natural frontstage.

All tests are synthetic protocol checks, NOT evidence of real LLM efficacy.
"""
from __future__ import annotations
import tempfile
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sd_runtime.engine import Engine, instructions
from sd_runtime.store import Workspace
from sd_runtime.frontstage import validate_frontstage
from sd_runtime.common import StateDyneError, digest
from test_runtime import TASK, FixtureBackend

ROOT = Path(__file__).resolve().parents[1]


class PreflightStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace.create(Path(self.tmp.name)/'run', TASK, backend='fixture', scope='points')
        self.backend = FixtureBackend(self.ws)
    def tearDown(self): self.tmp.cleanup()
    def start_points(self):
        release = Engine(self.ws, self.backend).advance()
        self.assertEqual(release['assurance'], 'simulation_only')
        return release

    def test_competition_and_action_probe_are_separate_workers_on_same_snapshot(self):
        self.start_points()
        portfolio = [j for j in self.backend.requests if j['role']=='change_portfolio']
        probes = [j for j in self.backend.requests if j['role']=='change_action_probe']
        self.assertEqual((len(portfolio),len(probes)),(1,1))
        self.assertNotEqual(portfolio[0]['id'], probes[0]['id'])
        self.assertEqual(digest(portfolio[0]['inputs']),digest(probes[0]['inputs']))
        self.assertIn('action_preflight', self.ws.state)
        r = self.ws.state['action_preflight']
        self.assertEqual(r['portfolio_job_id'], portfolio[0]['id'])
        self.assertEqual(r['action_probe_job_id'], probes[0]['id'])
        self.assertTrue(r['action_candidate_ids'])
        self.assertTrue(all(self.ws.active_claims()[x]['kind']=='action' for x in r['action_candidate_ids']))

    def test_preflight_actions_are_backend_only_during_points(self):
        self.start_points()
        draft=self.ws.state['draft']['output']
        self.assertTrue(any(c['kind']=='action' for c in self.ws.active_claims().values()))
        self.assertEqual({x['kind'] for x in draft['delivery_units']},{'point'})
        self.assertTrue(all(self.ws.active_claims()[x]['kind']!='action' for x in draft['used_claim_ids']))
        self.assertNotIn('独立动作:',draft['answer'])

    def test_next_actions_reuses_all_three_point_searches_and_preflight(self):
        self.start_points()
        old = self.ws.state['action_preflight']['action_probe_job_id']
        self.ws.continue_stage('actions')
        self.assertTrue(self.ws.state['intervention_frontier_done'])
        self.assertTrue(self.ws.state['preflight_reused_from_prior_stage'])
        self.assertEqual(self.ws.state['action_preflight']['action_probe_job_id'],old)
        Engine(self.ws, self.backend).advance()
        roles=[j['role'] for j in self.backend.requests]
        for role in ('change_forward','change_backward','change_portfolio','change_action_probe'):
            self.assertEqual(roles.count(role),1)
        draft=self.ws.state['draft']['output']
        self.assertEqual({x['kind'] for x in draft['delivery_units']},{'action'})
        self.assertNotIn('干预点:',draft['answer'])

    def test_actions_then_plan_reuses_point_and_action_search(self):
        self.start_points();self.ws.continue_stage('actions')
        Engine(self.ws,self.backend).advance()
        self.ws.continue_stage('plan')
        self.assertTrue(self.ws.state['intervention_frontier_done'])
        Engine(self.ws,self.backend).advance()
        roles=[j['role'] for j in self.backend.requests]
        for role in ('change_forward','change_backward','change_portfolio','change_action_probe'):
            self.assertEqual(roles.count(role),1)
        self.assertEqual({x['kind'] for x in self.ws.state['draft']['output']['delivery_units']},{'plan'})

    def test_new_additive_information_invalidates_cached_preflight(self):
        self.start_points()
        self.assertIsNotNone(self.ws.state['action_preflight'])
        self.ws.update('An observed rate-limit may explain the delay.')
        self.assertIsNone(self.ws.state['action_preflight'])
        self.assertFalse(self.ws.state['intervention_frontier_done'])
        self.assertEqual(self.ws.state['phase'],'delta_assess')

    def test_superseding_old_source_invalidates_cached_preflight(self):
        self.start_points()
        self.ws.update('Corrected reported slowdown timing.', supersedes='S1')
        self.assertIsNone(self.ws.state['action_preflight'])
        self.assertFalse(self.ws.state['intervention_frontier_done'])
        self.assertEqual(self.ws.state['phase'],'discover')

    def test_repeated_points_stage_reopens_point_search(self):
        self.start_points()
        self.ws.continue_stage('points')
        self.assertFalse(self.ws.state['intervention_frontier_done'])
        self.assertFalse(self.ws.state['preflight_reused_from_prior_stage'])
        Engine(self.ws,self.backend).advance()
        self.assertEqual(sum(x['role']=='change_forward' for x in self.backend.requests),2)


class NaturalFrontstageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=Workspace.create(Path(self.tmp.name)/'run',TASK,backend='fixture',scope='points')
        self.ws.state['delivery_scope']='points'
    def tearDown(self):self.tmp.cleanup()

    def test_generic_intervention_audit_matrix_is_rejected(self):
        for field in ('排名','旧传导','干预点','目标传导','具体动作'):
            with self.subTest(field=field),self.assertRaisesRegex(StateDyneError,'causal prose'):
                validate_frontstage(self.ws,{'answer':f'| {field} | 背景 | 理由 |\n| --- | --- | --- |\n| 1 | x | y |'})

    def test_natural_narrative_is_allowed_without_technical_label(self):
        sample=('目前先考虑现有资源拥堵，因为这一段队列直接决定所有任务的等待，'
                '而改一个没有进入关键路径的显示设置影响较小。'
                '如果新日志显示等待发生在外部限流，则排序应当改变。')
        validate_frontstage(self.ws,{'answer':sample})

    def test_explicit_requested_table_allowed(self):
        self.ws.add_source('User request','请用表格列出可改变位置和排序依据。',kind='user_reported',precision='as_reported',is_task=True)
        validate_frontstage(self.ws,{'answer':'| 排名 | 位置 |\n| --- | --- |\n| 1 | queue |'})

    def test_numerical_research_table_allowed_in_analysis_scope(self):
        self.ws.state['delivery_scope']='analysis'
        validate_frontstage(self.ws,{'answer':'| 排名 | 经营数据 |\n| --- | --- |\n| 1 | 100 |'})

    def test_no_generic_intervention_domain_is_hard_coded(self):
        names=['fixture-key-a','fixture-key-b','fixture-subject-a','fixture-domain-a','fixture-company-a']
        for role in ('change_forward','change_backward','change_portfolio','change_action_probe','compose','audit'):
            payload=instructions(role)
            self.assertIn('intervention',str((ROOT/'references/intervention-leverage.md').name))
            for name in names:
                self.assertNotIn(name,payload)
        self.assertIn('change_action_probe', (ROOT/'scripts/sd_runtime/engine.py').read_text())

if __name__=='__main__': unittest.main()
