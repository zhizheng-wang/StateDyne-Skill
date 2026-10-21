"""10.21: effect-first and always-on execution contracts; NOT real LLM quality proof."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))

from sd_runtime import __version__
from sd_runtime.cli import parser
from sd_runtime.engine import Engine, instructions
from sd_runtime.backends import NativeBackend
from sd_runtime.store import DEFAULTS, Workspace
from sd_runtime.priority_dispatch import priority_batch
from test_runtime import TASK, draft_for

ROOT = Path(__file__).resolve().parents[1]


class InvocationAndNoCapTests(unittest.TestCase):
    def test_new_version_and_skill_entry_invoked_for_all_calls(self):
        self.assertEqual(__version__, '11.3.0')
        text = (ROOT/'SKILL.md').read_text(encoding='utf8')
        self.assertTrue(text.index('references/always-on-orchestration.md') < text.index('## 可移植执行与历史高质量约束'))
        self.assertIn('没有真实独立工具时，当前模型不降级目标', text)
        self.assertIn('绝无固定问数', text)

    def test_openai_ui_prompt_prefers_actual_independent_workers(self):
        yaml = (ROOT/'agents/openai.yaml').read_text(encoding='utf8')
        self.assertIn('只要能调用就实际派发', yaml)
        self.assertIn('不把模拟多角色当实际多智能体', yaml)
        self.assertIn('无固定问题数量', yaml)

    def test_unlimited_exploration_is_default_not_20_ops(self):
        self.assertIsNone(DEFAULTS['max_operations'])
        args = parser().parse_args(['start','--task-file','x.txt','--workdir','run'])
        self.assertIsNone(args.max_operations)
        self.assertEqual(args.parallel_workers, 12)
        self.assertEqual(args.max_parallel_operations, 12)
        self.assertIsNone(args.max_question_characters)

    def test_unbounded_workspace_and_optional_explicit_transport_budget(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Workspace.create(Path(d)/'unlimited',TASK,backend='native')
            ws.state['operations_done']=1999
            self.assertEqual(Engine(ws, NativeBackend(ws.root, ws.state['sources'], ws.state['config'])).remaining_operations(), float('inf'))
            capped=Workspace.create(Path(d)/'capped',TASK,backend='native',config={'max_operations':4})
            capped.state['operations_done']=4
            self.assertEqual(Engine(capped, NativeBackend(capped.root, capped.state['sources'], capped.state['config'])).remaining_operations(),0)

    def test_no_three_question_fixture_truncation(self):
        qs=[{'id':f'Q{i}', 'question':f'What differs in independent evidence stream {i}?',
             'priority':'important'} for i in range(11)]
        generated=draft_for({'inputs':{'unknowns':qs, 'claims':[], 'foci':[]}})
        self.assertEqual(len([d for d in generated['information_dispositions'] if d['treatment']=='ask']),11)
        self.assertTrue(all(q['question'] in generated['answer'] for q in qs))

    def test_real_workers_do_not_appear_just_because_jobs_were_created(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Workspace.create(Path(d)/'native',TASK,backend='native')
            result=Engine(ws,NativeBackend(ws.root,ws.state['sources'],ws.state['config'])).advance()
            self.assertEqual(result['status'],'waiting_for_real_workers')
            self.assertEqual(len(result['jobs']),10)
            self.assertEqual({j['role'] for j in ws.state['jobs'].values()},
               {'frame','system_map','goal_scout','selection_scout','relation_scout','discovery','reframe','contrast_probe','environment_scout','blind_challenge'})
            self.assertFalse(any(x['status']=='completed' for x in ws.state['jobs'].values()))

    def test_every_actual_worker_sees_the_new_quality_contract(self):
        for role in ('reframe','contrast_probe','load_bearing','compose','schedule','audit'):
            spec=instructions(role)
            self.assertIn('实际模型工作者的质量内核',spec)
            self.assertIn('无固定数量或轮数上限',spec)
            self.assertIn('原始材料没有提到',spec)
            self.assertIn('不把未见结果写成观察事实',spec)


class ConcurrentHighValueWorkTests(unittest.TestCase):
    def test_many_independent_gaps_in_same_batch_not_only_one(self):
        work=priority_batch(model_opportunities=[f'O{i}' for i in range(8)],
                            research_unknowns=[f'U{i}' for i in range(8)],
                            evidence_reframes=[], capacity=12)
        self.assertEqual(len(work),12)
        self.assertEqual(sum(x['operator']=='reframe' for x in work),6)
        self.assertEqual(sum(x['operator']=='acquire' for x in work),6)
        self.assertEqual(len({tuple(x['opportunity_ids']) for x in work if x['operator']=='reframe'}),6)
        self.assertEqual(len({tuple(x['target_ids']) for x in work if x['operator']=='acquire'}),6)

    def test_all_independent_work_is_admitted_if_concurrency_allows(self):
        work=priority_batch(model_opportunities=[f'O{i}' for i in range(7)],
                            research_unknowns=[f'U{i}' for i in range(9)],
                            evidence_reframes=[], capacity=30)
        self.assertEqual(len(work),16)
        self.assertEqual(sum(x['operator']=='reframe' for x in work),7)
        self.assertEqual(sum(x['operator']=='acquire' for x in work),9)

    def test_new_evidence_reopens_and_coexists_with_other_work(self):
        work=priority_batch(model_opportunities=['O1','O2'],research_unknowns=['U1','U2'],
            evidence_reframes=[{'acquire_job':'J1','claim_ids':['M1']},
                               {'acquire_job':'J2','claim_ids':['M2']}],capacity=12)
        self.assertEqual(len(work),5)
        self.assertEqual(work[0]['operator'],'reframe')
        self.assertEqual(work[0]['evidence_trigger_ids'],['J1','J2'])
        self.assertEqual(work[0]['target_ids'],['M1','M2'])
        self.assertEqual(sum(x['operator']=='acquire' for x in work),2)

    def test_small_parallel_capacity_never_drops_an_item_from_input(self):
        models=[f'O{i}' for i in range(7)]
        unknowns=[f'U{i}' for i in range(7)]
        work=priority_batch(model_opportunities=models,research_unknowns=unknowns,
                            evidence_reframes=[],capacity=3)
        self.assertEqual(len(work),3)
        self.assertEqual(len(models),7)
        self.assertEqual(len(unknowns),7)
        self.assertEqual(work[0]['operator'],'reframe')
        self.assertEqual(work[1]['operator'],'acquire')

    def test_engine_itself_dispatches_nine_gaps_without_a_three_item_cutoff(self):
        with tempfile.TemporaryDirectory() as d:
            ws=Workspace.create(Path(d)/'native',TASK,backend='native')
            ws.state.update(phase='schedule', sweep_complete=True,
                            portfolio_complete=True, blind_complete=True,
                            entry_review={'output':{'verdict':'pass'}},
                            operations_done=37)
            ws.state['exploration_opportunities']={
                f'O{i}': {'id':f'O{i}', 'state':'open', 'attempts':0,
                          'system_dimension':f'd{i}', 'system_priority':'important'}
                for i in range(9)
            }
            result=Engine(ws,NativeBackend(ws.root,ws.state['sources'],ws.state['config'])).advance()
            self.assertEqual(result['status'],'waiting_for_real_workers')
            self.assertEqual(len(result['jobs']),9)
            self.assertEqual({ws.job_request(j['id'])['inputs']['opportunity_ids'][0]
                              for j in ws.state['jobs'].values()},
                             {f'O{i}' for i in range(9)})
            self.assertEqual(ws.state['operations_done'],37)  # Requests aren't results.

    def test_empty_frontier_does_not_fabricate_work(self):
        self.assertEqual(priority_batch(model_opportunities=[],research_unknowns=[],
                         evidence_reframes=[],capacity=12),[])

    def test_duplicate_opportunity_is_not_called_twice_in_same_batch(self):
        work=priority_batch(model_opportunities=['O1','O1','O2','O2'],
                            research_unknowns=['U1','U1'],evidence_reframes=[],capacity=12)
        self.assertEqual(len(work),3)

    def test_concurrency_capacity_is_not_question_count(self):
        work=priority_batch(model_opportunities=[f'O{i}' for i in range(10)],
                            research_unknowns=[],evidence_reframes=[],capacity=20)
        self.assertEqual(len(work),10)
        # There is intentionally no shared restriction on #questions, #hypotheses
        # and the number of physical threads.
        self.assertIsNone(DEFAULTS['max_question_characters'])


if __name__ == '__main__':
    unittest.main()
