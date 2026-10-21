"""10.8 operational-default and discovery-to-question regression checks.

No fixture or structural test measures actual GPT reasoning quality.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from sd_runtime.common import StateDyneError
from sd_runtime.probe_bridge import unbridged_model_outside
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.backends import write_result
from test_runtime import TASK, work, unknown, FixtureBackend


class CandidateProbeContract(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.ws = Workspace.create(Path(t.name)/'run', TASK)

    def _record(self, role, name, output):
        j = self.ws.get_job(f'g1-{name}', role, 'work', self.ws.raw_view(), instructions(role))
        write_result(self.ws.root, j, output, kind='fixture', worker_ref=f'synthetic-{role}', actual_model='fixture')
        self.ws.merge_work(j['id'])
        return j

    def test_novel_out_of_frame_prediction_must_route_to_information(self):
        self._record('discovery','discovery',work())
        o = work()
        o['claims'][0]['local_id']='M2'
        o['claims'][0]['statement']='An independent queue can be a different bottleneck.'
        o['claims'][0]['distinct_consequences']=['If only two calls overlap in the gateway, upstream queue delay rises.']
        r = self._record('reframe','reframe',o)
        gaps = unbridged_model_outside(self.ws)
        self.assertEqual(len(gaps),1)
        self.assertEqual(gaps[0]['claim_id'], f"{r['id']}:M2")
        self.assertEqual(self.ws.current_view()['bridge_gaps'], gaps)
        # The prediction must not become an extra user question if its
        # evidence can instead be calculated or retrieved by a tool.
        repair = work(claims=[])
        q = unknown('QNEW')
        q.update(question='Do upstream gateway logs show enqueueing only during overlapping calls?',
                 why_it_matters='A gateway queue predicts a delay absent from a local lock.',
                 origin='prediction', route='materials', related_claims=[f"{r['id']}:M2"])
        repair['unknowns']=[q]
        self._record('entry_repair','entry-repair-0',repair)
        self.assertEqual(unbridged_model_outside(self.ws), [])

    def test_one_prediction_without_link_is_not_equivalent_to_actual_discriminator(self):
        self._record('discovery','discovery',work())
        o = work()
        o['claims'][0]['local_id']='M3'
        o['claims'][0]['statement']='Shared gateway pressure amplifies concurrent latency.'
        o['claims'][0]['distinct_consequences']=['There will be lag in gateway metrics while local CPU remains flat.']
        q = unknown('Q1')
        q.update(question='Is CPU high?', why_it_matters='CPU relates to a different explanation.',
                 origin='model_discrimination', route='user', related_claims=[])
        o['unknowns']=[q]
        self._record('contrast_probe','contrast-probe',o)
        self.assertEqual(len(unbridged_model_outside(self.ws)), 1)

    def test_reused_baseline_claim_is_not_forced_to_invent_extra_question(self):
        self._record('discovery','discovery',work())
        self._record('reframe','reframe',work())
        self.assertEqual(unbridged_model_outside(self.ws), [])

    def test_process_opens_targeted_repair_even_if_model_review_passes(self):
        class NovelWithoutProbe(FixtureBackend):
            def execute(self, job):
                if job['role'] == 'reframe':
                    o=work()
                    o['claims'][0]['statement']='A separate external gateway queue could cause concurrency-only slowdown.'
                    o['claims'][0]['distinct_consequences']=['Only external retry backlog will grow, not local lock wait time.']
                    return write_result(self.ws.root, job, o, kind='fixture',
                                        worker_ref='novel-independent-fixture', actual_model='fixture')
                if job['role'] == 'entry_repair':
                    self.requests.append(deepcopy(job))
                    raise StateDyneError('targeted-probe-repair-invoked')
                return super().execute(job)
        backend = NovelWithoutProbe(self.ws)
        with self.assertRaisesRegex(StateDyneError, 'targeted-probe-repair-invoked'):
            Engine(self.ws, backend).advance()
        self.assertEqual(self.ws.state['phase'], 'entry_repair')
        calls=[j for j in backend.requests if j['role']=='entry_repair']
        self.assertEqual(len(calls),1)
        self.assertTrue(calls[0]['inputs']['bridge_gaps'])
        self.assertEqual(calls[0]['inputs']['operation'],'predict')
        self.assertEqual(self.ws.state['entry_review']['output']['verdict'],'pass')


class SkillAgentRoutingTests(unittest.TestCase):
    def test_real_delegation_first_with_capability_and_no_made_up_agents(self):
        entry=(ROOT/'SKILL.md').read_text(encoding='utf-8')
        runtime=(ROOT/'references/runtime.md').read_text(encoding='utf-8')
        bridge=(ROOT/'references/host-bridge.md').read_text(encoding='utf-8')
        self.assertIn('先检视当前宿主实际提供的独立工作者/委派工具',entry)
        self.assertIn('默认立即派发至少两条原料盲任务',entry)
        self.assertIn('不能仅创建 `request.json` 就说已运行智能体',entry)
        self.assertIn('不能强行把单模型扮演角色称为“多智能体”',entry)
        self.assertIn('优先实际派发',runtime)
        self.assertIn('真实',bridge)

    def test_discovery_is_promoted_to_prediction_and_evidence(self):
        entry=(ROOT/'SKILL.md').read_text(encoding='utf-8')
        compose=(ROOT/'references/operators/compose.md').read_text(encoding='utf-8')
        operator=(ROOT/'references/operators/contrast_probe.md').read_text(encoding='utf-8')
        self.assertIn('首轮交付的硬连接',entry)
        self.assertIn('新候选推导',entry)
        self.assertIn('origin=`prediction`',operator)
        self.assertIn('related_claims',compose)

    def test_no_fixed_user_question_or_cognitive_count(self):
        entry=(ROOT/'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('绝无固定问数',entry)
        self.assertNotIn('最多三个问题',entry)


if __name__=='__main__':
    unittest.main()
