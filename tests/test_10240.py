"""10.24 domain-neutral goal, selection and staged expansion protocol tests.

Synthetic controller tests only; no actual model reasoning is implied.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sd_runtime.common import StateDyneError, digest
from sd_runtime.engine import Engine, instructions
from sd_runtime.backends import write_result
from sd_runtime.store import Workspace
from sd_runtime.goal_review import register_goal_review
from test_runtime import TASK, FixtureBackend


class GoalAndSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws=Workspace.create(Path(self.tmp.name)/'work', TASK, backend='fixture')

    def goal_sample(self):
        job = self.ws.get_job('goal-scout-manual', 'goal_scout','goal_review',self.ws.raw_view(),instructions('goal_scout'))
        out = FixtureBackend(self.ws).execute(job)['output']
        return job, deepcopy(out)

    def register(self, job, out):
        # A fresh submitted receipt must match the real job; use a new job ID.
        if self.ws.result(job['id']) is not None:
            self.ws.state['jobs'][job['id']]['status']='rejected'
            job=self.ws.get_job('new-goal-scout', 'goal_scout','goal_review',self.ws.raw_view(),instructions('goal_scout'))
        write_result(self.ws.root, job, out, kind='fixture', worker_ref='independent-goal-test', actual_model='fixture')
        register_goal_review(self.ws, job['id'])
        return job

    def test_raw_goal_and_selection_work_in_parallel_with_other_discoverers(self):
        engine=Engine(self.ws,FixtureBackend(self.ws))
        release=engine.advance()
        self.assertEqual(release['assurance'],'simulation_only')
        jobs=[j for j in self.ws.state['jobs'].values() if j['role'] in ('frame','system_map','goal_scout','selection_scout','relation_scout','discovery','reframe','contrast_probe','environment_scout','blind_challenge')]
        roles={j['role'] for j in jobs}
        self.assertEqual(len(jobs),10)
        self.assertEqual(len(roles),10)
        self.assertIn('goal_scout',roles)
        self.assertIn('selection_scout',roles)
        self.assertIsNotNone(self.ws.state['goal_review'])
        self.assertEqual(self.ws.state['goal_review']['alternative'+'s'], [])
        ids=[self.ws.job_request(j['id'])['inputs'] for j in jobs]
        self.assertEqual(len({digest(x) for x in ids}),1)
        self.assertEqual(len([j for j in self.ws.state['work_results']
            if self.ws.job_request(j['job_id'])['role']=='selection_scout']),1)

    def test_explicit_goal_cannot_be_invented_without_source(self):
        job,out=self.goal_sample()
        out['source_evidence']=[]
        with self.assertRaisesRegex(StateDyneError,'Explicit goal must quote'):
            self.register(job,out)

    def test_value_dimensions_are_not_forced_into_one_scale(self):
        job,out=self.goal_sample()
        self.assertEqual(len(out['valued_dimensions']),2)
        self.assertNotEqual(out['valued_dimensions'][0]['content'],out['valued_dimensions'][1]['content'])
        self.register(job,out)
        self.assertEqual(len(self.ws.state['goal_review']['valued_dimensions']),2)

    def test_a_dimension_cannot_claim_distinction_without_reason(self):
        job,out=self.goal_sample()
        out['valued_dimensions'][0]['loss_if_collapsed']=''
        with self.assertRaisesRegex(StateDyneError,'require a reason'):
            self.register(job,out)

    def test_reject_duplicate_value_dimensions(self):
        job,out=self.goal_sample()
        out['valued_dimensions'][1]['label']=out['valued_dimensions'][0]['label'].upper()
        with self.assertRaisesRegex(StateDyneError,'unique labels'):
            self.register(job,out)

    def test_a_goal_alternative_cannot_silently_replace_user_goal(self):
        job,out=self.goal_sample()
        out['alternatives']=[{'target':'Prioritize response throughput over explaining cause',
                             'potential_gain':'Might fix symptoms faster',
                             'tradeoff':'Could conceal true failure mechanism',
                             'evidence_or_test':'First ask whether speed or diagnosis is the actual target',
                             'needs_user_choice':False}]
        with self.assertRaisesRegex(StateDyneError,'cannot be silently selected'):
            self.register(job,out)

    def test_missing_goal_requires_real_information_or_explicit_gap(self):
        job,out=self.goal_sample()
        out['basis']='missing';out['source_evidence']=[]
        out['gap_or_conflict']='';out['unresolved']=[]
        with self.assertRaisesRegex(StateDyneError,'Absent goal'):
            self.register(job,out)

    def test_independent_goal_question_enters_existing_inquiry_frontier(self):
        job,out=self.goal_sample()
        out['unresolved']=[{'question':'Is the priority latency or traceable correctness?',
                            'why_it_matters':'These targets favor different intervention points.',
                            'route':'user','priority':'important'}]
        j=self.register(job,out)
        self.assertIn(f"{j['id']}:goal-1",self.ws.state['unknowns'])
        from sd_runtime.inquiry_frontier import discovery_inquiries
        self.assertTrue(any(row['unknown_id']==f"{j['id']}:goal-1"
                            for row in discovery_inquiries(self.ws)))

    def test_clear_goal_does_not_force_new_goal_questions(self):
        job,out=self.goal_sample()
        self.register(job,out)
        self.assertFalse(any(u['origin']=='goal' for u in self.ws.state['unknowns'].values()))

    def test_compose_audit_retain_goal_selection_and_change_instructions_together(self):
        for role in ('compose','audit'):
            content = instructions(role)
            self.assertIn('目标—价值—现实差异', content)
            self.assertIn('从实际结果反推评价与选择机制', content)
            self.assertIn('干预', content)

    def test_selection_worker_is_real_distinct_role_not_environment_alias(self):
        self.assertNotEqual(instructions('selection_scout'), instructions('environment_scout'))
        self.assertIn('公开', instructions('selection_scout'))
        self.assertIn('反例', instructions('selection_scout'))


class ExpandAfterPointsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws=Workspace.create(Path(self.tmp.name)/'work', TASK, backend='fixture',scope='points')
        self.backend=FixtureBackend(self.ws)
        self.assertEqual(Engine(self.ws,self.backend).advance()['assurance'],'simulation_only')
        self.prior_ids={x['claim_id'] for x in self.ws.state['draft']['output']['delivery_units']
                        if x['kind']=='point'}
        self.assertTrue(self.prior_ids)

    def test_expand_after_points_preserves_point_stage(self):
        self.ws.expand_search('Find another intervention point with distinct net value')
        self.assertEqual(self.ws.state['scope'],'points')
        self.assertEqual(self.ws.state['delivery_scope'],'points')
        self.assertEqual(self.ws.state['expansion_target_scope'],'points')
        self.assertEqual(set(self.ws.state['expansion_base_point_ids']),self.prior_ids)
        self.assertEqual(self.ws.state['phase'],'expand_frontier')

    def test_reject_reprinting_old_points_as_new_discovery(self):
        prior=deepcopy(self.ws.state['draft']['output'])
        self.ws.expand_search('Find a second distinct leverage location')
        with self.assertRaisesRegex(StateDyneError,'actual new point value'):
            self.ws.check_delivery_contract(prior)

    def test_resume_starts_actual_new_independent_work_not_immediate_draft(self):
        self.ws.expand_search('Search independent leverage around external queues')
        # An open-search job is required after a reviewed stage; this is not
        # an immediate reprint of the cached answer.
        self.assertEqual(self.ws.state['phase'],'expand_frontier')
        self.assertFalse(self.ws.state.get('intervention_frontier_done'))
        self.assertFalse(self.ws.state['load_bearing_complete'])
        self.assertTrue(self.ws.state['open_search_requested'])
        self.assertGreaterEqual(len(self.prior_ids),1)

    def test_stage_continuation_after_point_expansion_can_still_be_actions(self):
        self.ws.continue_stage('actions')
        self.assertEqual(self.ws.state['scope'],'actions')
        self.assertFalse(self.ws.state['open_search_requested'])
        self.assertEqual(self.ws.state['expansion_base_point_ids'],[])
        self.assertTrue(self.ws.state['preflight_reused_from_prior_stage'])

    def test_open_goal_research_is_not_a_fixed_three_question_ceiling(self):
        # Independent goal questions use the same unbounded inquiry storage.
        job=self.ws.get_job('goal-cap-test','goal_scout','goal_review',self.ws.raw_view(),instructions('goal_scout'))
        from sd_runtime.schemas import SCHEMAS,validate
        sample={'current_target':'Change response times','basis':'missing','source_evidence':[],
                'observable_success':'Observe less contention','valued_dimensions':[],
                'alternatives':[],'gap_or_conflict':'Objective ambiguous',
                'adequate_existing_goal_reason':'',
                'unresolved':[{'question':f'Which independent business target {i} matters?',
                   'why_it_matters':f'Answer changes target criterion {i}',
                   'route':'user','priority':'important'} for i in range(13)]}
        validate(sample,SCHEMAS['goal_review'])
        write_result(self.ws.root,job,sample,kind='fixture',worker_ref='goal-cap-13',actual_model='fixture')
        register_goal_review(self.ws,job['id'])
        self.assertEqual(len([u for u in self.ws.state['unknowns'].values() if u['origin']=='goal']),13)


if __name__=='__main__':unittest.main()
