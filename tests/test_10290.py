"""10.29 long-horizon autonomy and independent option-value regressions.

All tests use unrelated synthetic workflow/resource examples. They do not
measure actual model intelligence or make factual claims about private users.
"""
from __future__ import annotations
from pathlib import Path
from copy import deepcopy
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.common import StateDyneError
from sd_runtime.backends import write_result
from sd_runtime.schemas import SCHEMAS,validate
from test_runtime import FixtureBackend, TASK, claim, work, draft_for

class BranchBackend(FixtureBackend):
    def __init__(self, ws, route=None, **kwargs):
        super().__init__(ws,**kwargs)
        self.route=route
    def execute(self, job):
        if job['role'] == 'open_search':
            cached=self.ws.result(job['id'])
            if cached:return cached
            self.requests.append(deepcopy(job))
            output=work(claims=[])
            output['no_increment_reason']=('Independent synthetic expansion compared multiple alternative relations, '
                 'found no new discriminating evidence, and preserved the active intervention stage.')
            return write_result(self.ws.root,job,output,kind='fixture',
                 worker_ref=f'fixture-{job["id"]}',actual_model='scripted-fixture',independent_context=True)
        if job['role'] == 'compose' and self.route == 'expand' and job['inputs'].get('expansion_base_point_ids'):
            cached=self.ws.result(job['id'])
            if cached:return cached
            self.requests.append(deepcopy(job))
            output=draft_for(job)
            # No valuable new point was found; don't reprint a previously published point.
            prior=set(job['inputs']['expansion_base_point_ids'])
            dropped=[u for u in output['delivery_units'] if u['claim_id'] in prior]
            for u in dropped:
                output['answer']=output['answer'].replace('\n'+u['visible_text']+'\n'+u['comparison'],'')
                output['used_claim_ids'].remove(u['claim_id'])
                next(d for d in output['claim_dispositions'] if d['claim_id']==u['claim_id'])['treatment']='not_selected'
            output['delivery_units']=[u for u in output['delivery_units'] if u['claim_id'] not in prior]
            reason='本轮扩大搜索已完成，独立比较后未发现具有新增价值的其他干预点，之前的优先位置依然可用。'
            output['answer']+='\n'+reason
            output['delivery_limit_reason']=reason
            output['status']='complete'
            return write_result(self.ws.root,job,output,kind='fixture',
                worker_ref=f'fixture-{job["id"]}',actual_model='scripted-fixture',independent_context=True)
        if job['role'] != 'turn_router' or self.route is None:
            return super().execute(job)
        cached=self.ws.result(job['id'])
        if cached:return cached
        self.requests.append(deepcopy(job))
        text=job['inputs']['new_user_turn']['text']
        payload={'route':self.route,'quoted_trigger':text.strip(),
                 'reason':'The latest actual request explicitly directs this task route.',
                 'preserves_primary_goal':self.route!='replace_goal',
                 'user_declines_more_questions':False,'user_invites_questions':False,
                 'expansion_focus':'Re-evaluate upstream conditions and rival explanations' if self.route=='expand' else '',
                 'no_new_information_route':'Work from already supplied evidence, public information and conditional evidence.'}
        return write_result(self.ws.root,job,payload,kind='fixture',worker_ref=f'fixture-{job["id"]}',
                            actual_model='scripted-fixture',independent_context=True)

class NovelAlternativeFixture(FixtureBackend):
    def execute(self, job):
        if job['role']!='value_frontier':return super().execute(job)
        cached=self.ws.result(job['id'])
        if cached:return cached
        self.requests.append(deepcopy(job))
        alt=claim(local='V1')
        alt['statement']='Independent hardware contention can also produce overlapping-task latency.'
        alt['mechanism']['transformation']='Two requests saturate a shared physical bus with no software lock.'
        alt['distinct_consequences']=['Latency remains high when software locks are eliminated.']
        return write_result(self.ws.root,job,work([alt]),kind='fixture',
                            worker_ref=f'fixture-{job["id"]}',actual_model='scripted-fixture',independent_context=True)

class LongHorizonTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.ws=Workspace.create(Path(temp.name)/'run',TASK,scope='points',backend='fixture')
        self.backend=FixtureBackend(self.ws)
        self.engine=Engine(self.ws,self.backend)
        release=self.engine.advance()
        self.assertEqual(release['status'],'complete')
        self.initial_goal=self.ws.state['task_thread']['latest_unfinished_goal']
        self.initial_stage=self.ws.state['task_navigation']['last_primary_scope']

    def test_no_user_turn_is_automatically_treated_as_new_primary_source(self):
        self.assertEqual(self.ws.receive_user_turn('side: explain a technical term')['status'],'routing_required')
        self.assertEqual(self.ws.state['phase'],'route_turn')
        self.engine.advance()
        self.assertEqual(self.ws.state['interaction_mode'],'side')
        self.assertEqual(self.ws.state['task_navigation']['last_primary_scope'],self.initial_stage)
        self.assertEqual(self.ws.state['task_thread']['latest_unfinished_goal'],self.initial_goal)
        self.assertFalse(self.ws.state['sources']['S2']['is_task'])
        self.assertEqual(self.ws.state['sources'][self.ws.state['current_turn_source_id']]['text'],'side: explain a technical term')
        self.assertEqual(self.ws.current_view()['latest_user_message']['text'],'side: explain a technical term')

    def test_refusal_is_not_main_goal_cancellation_or_repeat_question(self):
        self.ws.receive_user_turn('我不想再提供这些私人的细节')
        self.engine.advance()
        self.assertEqual(self.ws.state['task_thread']['user_input_policy'],'no_repeated_questions_without_invitation')
        self.assertEqual(self.ws.state['task_thread']['status'],'active')
        self.assertEqual(self.ws.state['task_navigation']['last_primary_scope'],'points')
        self.assertEqual(self.ws.state['scope'],'analysis')

    def test_multiple_side_branches_resume_last_audited_point_stage(self):
        for phrase in ('side: a quick unrelated question','side: a second unrelated question','下一步'):
            self.ws.receive_user_turn(phrase)
            self.engine.advance()
        self.assertEqual(self.ws.state['task_navigation']['last_primary_scope'],'actions')
        self.assertEqual(self.ws.state['interaction_mode'],'primary')
        self.assertTrue(self.ws.previously_delivered_interventions()['point'])
        self.assertTrue(self.ws.state['task_thread']['last_verified_primary_stage']=='actions')
        self.assertEqual(len(self.ws.state['task_thread']['turn_routes']),3)
        self.assertEqual(len([j for j in self.ws.state['jobs'].values() if j['role']=='frame']),1)

    def test_paused_task_does_not_offer_automatic_resume(self):
        self.engine.backend=BranchBackend(self.ws,route='pause')
        self.ws.receive_user_turn('请先暂停我们原来的研究')
        self.engine.advance()
        self.assertEqual(self.ws.state['task_thread']['status'],'paused')
        nav=self.ws.state['draft']['output']['navigation']
        self.assertEqual(nav['next_offer'],'')
        self.assertEqual(nav['expansion_offer'],'')

    def test_open_goal_request_must_be_actual_user_turn_quote(self):
        self.ws.receive_user_turn('side: unrelated follow up')
        request=self.ws.get_job('isolated-route-validation','turn_router','turn_route',
            {'new_user_turn':self.ws.state['pending_turn']},instructions('turn_router'))
        invalid={'route':'side','quoted_trigger':'fabricated words','reason':'side question',
            'preserves_primary_goal':True,'user_declines_more_questions':False,
            'user_invites_questions':False,'expansion_focus':'','no_new_information_route':'Use original evidence.'}
        write_result(self.ws.root,request,invalid,kind='fixture',worker_ref='fixture-x',actual_model='script',independent_context=True)
        with self.assertRaisesRegex(StateDyneError,'unchanged span'):
            self.ws.apply_turn_route(invalid,request['id'])
        self.assertEqual(self.ws.state['phase'],'route_turn')

    def test_primary_value_frontier_is_real_worker_and_does_not_repeat_forever(self):
        before=[j for j in self.ws.state['jobs'].values() if j['role']=='value_frontier']
        self.assertEqual(len(before),1)
        self.assertTrue(self.ws.state['value_frontier_done'])
        self.assertTrue(before[0]['status']=='completed')
        self.assertIn('higher-value',instructions('value_frontier').lower())

    def test_expansion_remains_in_same_intervention_stage(self):
        self.engine.backend=BranchBackend(self.ws,route='expand')
        self.ws.receive_user_turn('我想再寻找不同的可改变位置')
        self.engine.advance()
        self.assertEqual(self.ws.state['task_navigation']['last_primary_scope'],'points')
        self.assertTrue(self.ws.state['expansion_runs'])

    def _route_replacement_in_isolation(self, message):
        # Route worker is still permitted to see the old task in order to
        # classify this turn. No old content survives into the new research.
        self.engine.backend=BranchBackend(self.ws,route='replace_goal')
        self.ws.receive_user_turn(message)
        inputs=self.ws.current_view()
        inputs['new_user_turn']=deepcopy(self.ws.state['pending_turn'])
        job=self.engine.job('turn-route-test','turn_router','turn_route',inputs)
        self.engine.backend.execute(job)
        self.ws.apply_turn_route(self.ws.result(job['id'])['output'],job['id'])

    def test_explicit_goal_replacement_cannot_be_misclassified_as_local(self):
        new='改成新目标：研究另一个独立问题，不参考此前对话和记忆'
        self._route_replacement_in_isolation(new)
        self.assertEqual(self.ws.state['phase'],'discover')
        self.assertFalse(self.ws.state['sources']['S1']['active'])
        self.assertEqual(self.ws.raw_view()['task_sources'][0]['text'],new)
        self.assertFalse(self.ws.current_view()['claims'])
        self.assertFalse(self.ws.current_view()['work_results'])
        self.assertEqual(len(self.ws.current_view()['task_sources']),1)

    def test_value_frontier_new_rival_gets_fresh_portfolio_and_audit_not_old_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            ws=Workspace.create(Path(td)/'fresh',TASK,backend='fixture')
            eng=Engine(ws,NovelAlternativeFixture(ws));release=eng.advance()
            self.assertEqual(release['status'],'complete')
            self.assertTrue(ws.state['value_frontier_done'])
            self.assertEqual(len([j for j in ws.state['jobs'].values() if j['role']=='value_frontier']),1)
            self.assertTrue(any('value-c0-r1' in j['tag'] for j in ws.state['jobs'].values() if j['role']=='probe_portfolio'))
            self.assertGreaterEqual(len({j['tag'] for j in ws.state['jobs'].values() if j['role']=='load_bearing'}),2)
            self.assertTrue(any(c['statement'].startswith('Independent hardware contention') for c in ws.active_claims().values()))

    def test_refusal_route_preserves_independent_research_plan(self):
        self.ws.receive_user_turn('我不想回答更多私人问题')
        self.engine.advance()
        self.assertIn('conditional evidence',self.ws.state['task_thread']['independent_continuation_plan'])
        self.assertEqual(self.ws.current_view()['task_thread']['user_input_policy'],
                         'no_repeated_questions_without_invitation')

    def test_replaced_goal_moves_root_source_identifier(self):
        new='完全更换研究目标：新问题具有独立结果，不参考以前研究'
        self._route_replacement_in_isolation(new)
        self.assertEqual(self.ws.state['task_thread']['root_source_id'],'S2')
        self.assertEqual(self.ws.state['task_thread']['latest_unfinished_goal'],new)
        self.assertNotIn(self.initial_goal,repr(self.ws.current_view()))
        self.assertNotIn('past_goals',self.ws.current_view()['task_thread'])
        self.assertEqual(self.ws.state['scope'],'auto')
        self.assertEqual(self.ws.state['task_navigation']['last_primary_scope'],None)

    def test_public_instructions_require_active_long_horizon_return_and_nonforced_novelty(self):
        entry=(ROOT/'SKILL.md').read_text('utf8')
        self.assertIn('长程自主研究',entry)
        self.assertIn('拒答',entry)
        self.assertIn('高价值',instructions('value_frontier'))
        self.assertIn('not',instructions('turn_router').lower())

if __name__=='__main__':unittest.main()
