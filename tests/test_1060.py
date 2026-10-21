"""10.6.0 entry and independent-raw-search negative controls.

These are deterministic protocol checks, NEVER a GPT-5.6 capability claim.
"""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sd_runtime.common import StateDyneError
from sd_runtime.diversity import check_raw_discovery_diversity
from sd_runtime.backends import write_result
from sd_runtime.store import Workspace
from sd_runtime.engine import instructions, Engine
from test_runtime import TASK, work, unknown, FixtureBackend

RAW_ROLES = ('discovery', 'reframe', 'contrast_probe', 'environment_scout', 'selection_scout', 'relation_scout', 'blind_challenge')

class AllOpenTasksTests(unittest.TestCase):
    def test_portable_discovery_is_mandatory_and_not_domain_gated(self):
        entry = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        runtime = (ROOT / 'references/runtime.md').read_text(encoding='utf-8')
        guide = (ROOT / 'references/portable-discovery.md').read_text(encoding='utf-8')
        self.assertIn('references/portable-discovery.md', entry)
        self.assertIn('不按日常/复杂分流', entry)
        self.assertIn('开放问题均默认使用完整认知能力', runtime)
        self.assertIn('便携模式下', entry)
        self.assertIn('不是已启动多 Agent', guide)
        self.assertNotIn('简单任务保持简洁', entry)
        self.assertIn('未报告', guide)
        self.assertIn('不设问题', guide)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Workspace.create(Path(self.temp.name) / 'workspace', TASK)

    def batch(self, *, alter_role=None, delta=None, no_increment=None):
        jobs=[]
        for role in RAW_ROLES:
            job = self.ws.get_job('raw-'+role, role, 'work', self.ws.raw_view(), instructions(role))
            output = work()
            if role == alter_role and delta:
                delta(output)
            if role in (no_increment or {}):
                output['no_increment_reason'] = no_increment[role]
            write_result(self.ws.root, job, output, kind='fixture',
                         worker_ref='negative-control-'+role, actual_model='test-mock')
            jobs.append(job)
        return jobs

    def test_unexplained_repeated_sibling_explanations_do_not_count_as_breadth(self):
        jobs=self.batch()
        with self.assertRaisesRegex(StateDyneError, 'reframe.*repeated previous signals'):
            check_raw_discovery_diversity(self.ws, jobs)
        self.assertFalse(self.ws.state['claims'])
        self.assertFalse(self.ws.state['work_results'])

    def test_real_engine_blocks_raw_batch_repeating_sibling_outputs(self):
        from copy import deepcopy
        class DuplicateReframe(FixtureBackend):
            def execute(self, job):
                if job['role'] == 'reframe':
                    self.requests.append(deepcopy(job))
                    return write_result(self.ws.root, job, work(), kind='fixture',
                                        worker_ref='duplicate-reframe-mock', actual_model='mock')
                return super().execute(job)
        executor=Engine(self.ws, DuplicateReframe(self.ws))
        with self.assertRaisesRegex(StateDyneError, 'reframe.*repeated previous signals'):
            executor.advance()
        self.assertEqual(self.ws.state['phase'], 'discover')
        self.assertFalse(self.ws.state['work_results'])

    def test_distinct_prediction_counts_as_candidate_not_proof(self):
        def new_prediction(o):
            o['claims'][0]['distinct_consequences'] = ['Only when a third resource is saturated, latency grows.']
        nulls = {role:'An independent alternative was checked against the observed overlap, but it gives no independent outcome.'
                 for role in ('contrast_probe', 'environment_scout', 'selection_scout', 'relation_scout', 'blind_challenge')}
        jobs=self.batch(alter_role='reframe', delta=new_prediction, no_increment=nulls)
        check_raw_discovery_diversity(self.ws,jobs)

    def test_new_discriminating_unknown_counts_as_discovery_route(self):
        def new_question(o):
            u=unknown()
            u['question'] = 'Does a rate limit apply only on the external gateway?'
            u['why_it_matters']='If so the root cause moves outside the shared local lock.'
            o['unknowns'].append(u)
        nulls = {role:'The observed result has no evidence for a distinct independent environment or prediction at this step.'
                 for role in ('contrast_probe', 'environment_scout', 'selection_scout', 'relation_scout', 'blind_challenge')}
        jobs=self.batch(alter_role='reframe', delta=new_question, no_increment=nulls)
        check_raw_discovery_diversity(self.ws,jobs)

    def test_credible_null_is_not_forced_into_fabricated_mechanism(self):
        nulls={role:'The exact observed contrast and the strongest alternative were compared; no independent prediction follows.'
               for role in RAW_ROLES[1:]}
        check_raw_discovery_diversity(self.ws,self.batch(no_increment=nulls))

    def test_one_word_claim_of_no_increment_is_rejected(self):
        nulls={role:'none' for role in RAW_ROLES[1:]}
        with self.assertRaisesRegex(StateDyneError,'specific no-increment explanation'):
            check_raw_discovery_diversity(self.ws,self.batch(no_increment=nulls))

    def test_changed_phrase_without_changed_prediction_does_not_pass_by_role_title(self):
        def description_only(o):
            # Change only a description of the same effect, with no distinct evidence or prediction.
            o['summary']='A supposedly independent expert repeated the existing model.'
        nulls={role:'A separate search offered no additional independently discriminating outcome.'
               for role in RAW_ROLES[2:]}
        with self.assertRaisesRegex(StateDyneError,'reframe'):
            check_raw_discovery_diversity(self.ws,self.batch(alter_role='reframe',delta=description_only,no_increment=nulls))

if __name__=='__main__':
    unittest.main()
