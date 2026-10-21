"""11.0 structural regressions targeting observed failure modes.

These tests ensure the engine actually attempts the right work and maintains
public continuation state.  Scripted outputs cannot certify semantic novelty.
"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.research_agenda import agenda, meaningful_frontier, unattempted_open_relations
from sd_runtime.backends import write_result
from sd_runtime.common import StateDyneError
from sd_runtime.schemas import SCHEMAS, validate
from test_runtime import FixtureBackend, TASK, work


class GenerativeLoopStructuralTests(unittest.TestCase):
    def workspace(self, scope='analysis'):
        holder=tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        ws=Workspace.create(Path(holder.name)/'run',TASK,scope=scope,backend='fixture')
        return ws

    def test_early_goal_value_competition_is_before_first_finish_scheduler(self):
        ws=self.workspace()
        self.assertEqual(Engine(ws,FixtureBackend(ws)).advance()['status'],'complete')
        jobs=list(ws.state['jobs'].values())
        types=[j['role'] for j in jobs]
        self.assertIn('value_frontier',types)
        self.assertIn('schedule',types)
        self.assertLess(types.index('value_frontier'), types.index('schedule'))
        self.assertTrue(ws.state['value_frontier_done'])

    def test_novel_opportunity_is_not_silently_erased_by_scheduler_finish(self):
        ws=self.workspace()
        class FinishTooSoon(FixtureBackend):
            def execute(self, job):
                if self.ws.result(job['id']):
                    return self.ws.result(job['id'])
                if job['role']=='discovery':
                    out=work()
                    out['opportunities']=['Investigate the missing outside selection process under reversed conditions.']
                    self.requests.append(deepcopy(job))
                    return write_result(self.ws.root,job,out,kind='fixture',
                        worker_ref='fixture-'+job['id'],actual_model='scripted-fixture')
                if job['role']=='schedule':
                    self.requests.append(deepcopy(job))
                    out={'decisions':[],'finish':True,
                         'finish_reason':'Scripted scheduler wants to stop.',
                         'delivery_scope':'analysis','adoption_relevant':False,
                         'scope_reason':'The user requested an explanation.'}
                    return write_result(self.ws.root,job,out,kind='fixture',
                        worker_ref='fixture-'+job['id'],actual_model='scripted-fixture')
                return super().execute(job)
        backend=FinishTooSoon(ws)
        self.assertEqual(Engine(ws,backend).advance()['status'],'complete')
        self.assertTrue(any(j['role']=='reframe_informed' for j in backend.requests))
        self.assertTrue(any(x['attempts'] for x in ws.state['exploration_opportunities'].values()))

    def test_deferred_question_stays_on_durable_frontier(self):
        ws=self.workspace()
        Engine(ws,FixtureBackend(ws)).advance()
        ws.state['unknowns']['deferred']={
            'id':'deferred','question':'Check whether the rival predicts latency without simultaneous access',
            'route':'public_source','priority':'important','state':'defer','origin_job':'probe',
            'related_claims':[]}
        matches=[x for x in ws.research_frontier() if x['id']=='deferred']
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0]['disposition'],'defer')
        self.assertEqual(matches[0]['route'],'public_source')
        ws.state['interaction_mode']='side'
        self.assertIn('deferred',[x['id'] for x in ws.research_frontier()])

    def test_open_relation_requires_specific_visible_bridge(self):
        ws=self.workspace(scope='points')
        Engine(ws,FixtureBackend(ws)).advance()
        ws.state['exploration_opportunities']['new-selection']={
            'id':'new-selection','description':'调查采购决策条件是否会反向改变收益归属和最强干预点',
            'state':'open','attempts':0,'system_priority':'important','origin_job':'discovery'}
        self.assertTrue(meaningful_frontier(ws.state))
        draft=deepcopy(ws.state['draft']['output'])
        with self.assertRaisesRegex(StateDyneError,'source|research|具体|bind|引用|Concrete'):
            ws.check_navigation_contract(draft)
        draft['navigation']['research_focus_id']='new-selection'
        draft['navigation']['research_focus_excerpt']='采购决策条件'
        draft['navigation']['expansion_offer']='还可扩大搜索采购决策条件，检验收益归属是否改变点的优先次序。'
        draft['answer'] += '\n'+draft['navigation']['expansion_offer']
        ws.check_navigation_contract(draft)
        draft['navigation']['research_focus_id']='nonexistent'
        with self.assertRaisesRegex(StateDyneError,'bind'):
            ws.check_navigation_contract(draft)

    def test_plan_is_not_equivalent_to_research_exhaustion(self):
        ws=self.workspace(scope='plan')
        Engine(ws,FixtureBackend(ws)).advance()
        ws.state['exploration_opportunities']['X']={
            'id':'X','description':'继续比较临界位置和跨域新关系可能改变方案',
            'state':'open','attempts':0,'origin_job':'independent','system_priority':'important'}
        self.assertEqual(ws.state['task_navigation']['last_next_scope'],'none')
        draft=deepcopy(ws.state['draft']['output'])
        draft['navigation']['expansion_offer']='可继续扩大搜索临界位置，检验跨域机制是否改变原方案。'
        draft['navigation']['research_focus_id']='X'
        draft['navigation']['research_focus_excerpt']='临界位置'
        draft['navigation']['visible_anchor']=draft['navigation']['expansion_offer']
        draft['answer'] += '\n'+draft['navigation']['expansion_offer']
        ws.check_navigation_contract(draft)
        ws.continue_stage('next')
        self.assertEqual(ws.state['phase'],'expand_frontier')
        self.assertEqual(ws.state['scope'],'plan')

    def test_unconsented_goal_alternative_is_visible_but_never_selected_silently(self):
        ws=self.workspace()
        ws.state['goal_review']={'job_id':'g1','alternatives':[
            {'target':'把收入目标换成长期保留创造时间的现金流','potential_gain':'自由时间',
             'tradeoff':'当前收入可能更低','evidence_or_test':'compare','needs_user_choice':True}]}
        routes=agenda(ws.state)
        self.assertEqual(len(routes),1)
        self.assertEqual(routes[0]['kind'],'goal_tradeoff')
        self.assertEqual(routes[0]['route'],'compare_without_replacing_user_goal')
        self.assertEqual(ws.state['task_thread']['latest_unfinished_goal'],TASK)

    def test_optional_research_navigation_fields_remain_backwards_compatible(self):
        ws=self.workspace()
        Engine(ws,FixtureBackend(ws)).advance()
        draft=deepcopy(ws.state['draft']['output'])
        validate(draft,SCHEMAS['draft'])
        draft['navigation'].update(research_focus_id='X',research_focus_excerpt='真实目标')
        validate(draft,SCHEMAS['draft'])
        draft['navigation']['unadvertised_data']='bad'
        with self.assertRaisesRegex(StateDyneError,'unadvertised_data'):
            validate(draft,SCHEMAS['draft'])

    def test_operational_workers_get_the_same_evolving_reality_loop(self):
        for role in ('schedule','goal_scout','value_frontier','compose','audit',
                     'turn_router','change_portfolio','open_search'):
            prompt=instructions(role)
            self.assertIn('生成性研究循环',prompt)
            self.assertIn('粗略',prompt)
            self.assertIn('研究前沿',prompt)
        entry=(ROOT/'SKILL.md').read_text(encoding='utf8')
        self.assertIn('让用户本轮',entry) if '让用户本轮' in entry else self.assertIn('回答先满足本轮意图',entry)
        self.assertIn('继续扩大搜索',entry)
        self.assertIn('持续',entry)


if __name__=='__main__':unittest.main()
