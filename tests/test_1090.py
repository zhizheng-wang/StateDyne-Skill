"""10.9 model-space changes: deterministic tests, never proof of GPT discovery."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys, tempfile, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sd_runtime.common import StateDyneError
from sd_runtime.engine import Engine, instructions
from sd_runtime.store import Workspace
from sd_runtime.backends import write_result
from sd_runtime.frontier import check_boundary, ensure_repair_changed_relation
from sd_runtime.probe_bridge import unbridged_model_outside
from test_runtime import FixtureBackend, TASK, work, unknown
from test_frontier import setup, sample_coverage


def assessment(mode='no_new_space_after_search', **kwargs):
    a = {'judgment':mode, 'candidate_claim_ids': [],
         'prior_representation_limit':'A local lock explanation covers only visible concurrency behavior.',
         'tested_alternative_representation':'A gateway queue or external admission policy could delay a distinct subsystem.',
         'unreported_outcome':'', 'discriminating_observation':'',
         'comparison_reason':'Source-bound alternatives were compared; a test is needed to identify the actual mechanism.'}
    a.update(kwargs)
    return a


class SearchSpaceReviewTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.ws=Workspace.create(Path(t.name)/'case', TASK, backend='fixture')
        self.focus, self.base_claim=setup(self.ws)

    def review(self,a,verdict='pass'):
        return {'system_coverage_dispositions':[], 'search_space_assessment':a,'verdict':verdict,
                'new_foci':[], 'coverage':[sample_coverage(self.focus,self.base_claim)],
                'examined_contrasts':['Concurrent requests versus sequential requests.'],
                'missing_relation':'An independent model-space search has not been performed.' if verdict=='reopen' else '',
                'why_material':'A different mechanism may reverse the appropriate fix.' if verdict=='reopen' else '',
                'next_operator':'reframe',
                'required_new_prediction_or_test':'Predict an out-of-model observable result.' if verdict=='reopen' else '',
                'no_gap_reason':'The actual cited tests discriminate the available mechanisms.' if verdict=='pass' else ''}

    def test_incomplete_model_outside_search_cannot_pass(self):
        with self.assertRaisesRegex(StateDyneError,'cannot pass'):
            check_boundary(self.ws,self.review(assessment('missing_search')))

    def test_missing_model_search_may_reopen_without_faking_unexplained_observation(self):
        self.assertEqual(check_boundary(self.ws,self.review(assessment('missing_search'),'reopen')),[])

    def test_new_claim_needs_independent_source_and_outcome(self):
        a=assessment('new_testable_space', candidate_claim_ids=[self.base_claim],
                     unreported_outcome='External retry counts rise even when the local lock is free.',
                     discriminating_observation='Read retry logs under overlapping calls.')
        with self.assertRaisesRegex(StateDyneError,'independently sourced'):
            check_boundary(self.ws,self.review(a))

    def test_new_claim_without_discriminator_is_not_credited(self):
        a=assessment('new_testable_space', candidate_claim_ids=[self.base_claim],
                     unreported_outcome='Different subsystem metric changes.')
        with self.assertRaisesRegex(StateDyneError,'unseen prediction and discriminator'):
            check_boundary(self.ws,self.review(a))

    def test_model_outside_source_is_admissible_and_bridge_can_be_separate(self):
        d=self.ws.get_job('g1-discovery','discovery','work',self.ws.raw_view(),instructions('discovery'))
        write_result(self.ws.root,d,work(),kind='fixture',worker_ref='new-baseline-worker',actual_model='fixture')
        self.ws.merge_work(d['id'])
        j=self.ws.get_job('g1-frontier-scout','frontier_scout','work',self.ws.current_view(),instructions('frontier_scout'))
        x=work(); x['claims'][0]['local_id']='NX1'
        x['claims'][0]['statement']='The gateway rate limit, not local CPU, is the shared bottleneck.'
        x['claims'][0]['distinct_consequences']=['Gateway retry count should rise without a local lock wait.']
        write_result(self.ws.root,j,x,kind='fixture',worker_ref='fresh-frontier',actual_model='fixture')
        self.ws.merge_work(j['id'])
        new_id=f"{j['id']}:NX1"
        a=assessment('new_testable_space', candidate_claim_ids=[new_id],
                     unreported_outcome='Gateway retry count rises without local CPU saturation.',
                     discriminating_observation='Read gateway metrics when request overlap changes.')
        self.assertEqual(check_boundary(self.ws,self.review(a)),[])
        gaps=unbridged_model_outside(self.ws)
        self.assertTrue(any(item['claim_id']==new_id for item in gaps))
        # A source-routed, claim-linked unknown closes the bridge without
        # forcing the user to answer a question available in server logs.
        j2=self.ws.get_job('manual-information-path','acquire','work',self.ws.current_view(),instructions('acquire'))
        x2=work(claims=[]); q=unknown('QNX');q.update(question='Do gateway retry metrics rise without local lock waiting?',
                     why_it_matters='A remote gateway queue predicts a difference from the local lock model.',
                     origin='prediction',route='materials',related_claims=[new_id]); x2['unknowns']=[q]
        write_result(self.ws.root,j2,x2,kind='fixture',worker_ref='data-worker',actual_model='fixture')
        self.ws.merge_work(j2['id'])
        self.assertFalse(any(item['claim_id']==new_id for item in unbridged_model_outside(self.ws)))

    def test_null_search_is_permitted_without_forcing_invention(self):
        self.assertEqual(check_boundary(self.ws,self.review(assessment())),[])

    def test_empty_or_fake_comparison_cannot_pass(self):
        a=assessment(comparison_reason=' ')
        with self.assertRaisesRegex(StateDyneError,'comparison'):
            check_boundary(self.ws,self.review(a))

    def test_prev_missing_search_requires_real_repair_output(self):
        previous=self.review(assessment('missing_search'),'reopen')
        current=self.review(assessment(),'pass')
        with self.assertRaisesRegex(StateDyneError,'needs a real new prediction'):
            ensure_repair_changed_relation(self.ws,previous,current,'J4040')


class EngineOrderingAndContractsTests(unittest.TestCase):
    def test_gate_sees_frontier_and_acquisition_before_first_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Workspace.create(Path(tmp)/'run', TASK, backend='fixture')
            b=FixtureBackend(ws)
            release=Engine(ws,b).advance()
            self.assertEqual(release['assurance'],'simulation_only')
            names=[x['role'] for x in b.requests]
            self.assertLess(names.index('frontier_scout'),names.index('entry_review'))
            self.assertLess(names.index('evidence_scout'),names.index('entry_review'))
            rev=next(x for x in b.requests if x['role']=='entry_review')
            source_roles={ws.job_request(r['job_id'])['role'] for r in rev['inputs']['work_results']}
            self.assertIn('frontier_scout',source_roles)
            self.assertIn('evidence_scout',source_roles)
            self.assertEqual(len(rev['inputs']['first_pass_job_ids']),8)

    def test_roles_have_distinct_cognitive_responsibilities(self):
        root=Path(__file__).resolve().parents[1]
        disc=(root/'references/operators/discovery.md').read_text()
        reform=(root/'references/operators/reframe.md').read_text()
        probe=(root/'references/operators/contrast_probe.md').read_text()
        gate=(root/'references/operators/entry_review.md').read_text()
        entry=(root/'SKILL.md').read_text()
        self.assertIn('解释现有事实是你的责任',disc)
        self.assertIn('改变问题表示',reform)
        self.assertIn('另一类现象',probe)
        self.assertIn('search_space_assessment',gate)
        self.assertIn('三份措辞不同',entry)
        self.assertNotIn('最多三个问题',entry)

if __name__=='__main__':unittest.main()
