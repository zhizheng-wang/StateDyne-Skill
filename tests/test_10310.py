"""10.31 tests: explicit independent-task scope, publication/closure protocol.

No LLM semantic quality claim follows from these structural safeguards.
"""
from __future__ import annotations
from pathlib import Path
import json
import tempfile
import unittest
from copy import deepcopy
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine,instructions
from test_runtime import FixtureBackend,TASK
from test_10290 import BranchBackend


class LiveFailureBoundaryTests(unittest.TestCase):
    def test_explicit_independent_goal_does_not_leak_old_material_or_cognition(self):
        with tempfile.TemporaryDirectory() as td:
            ws=Workspace.create(Path(td)/'run',TASK,scope='points',backend='fixture',
                materials=[('Prior material', 'OLD PRIVATE MATERIAL ONLY FOR ORIGINAL TASK')])
            eng=Engine(ws,FixtureBackend(ws))
            self.assertEqual(eng.advance()['status'],'complete')
            old_claims=set(ws.active_claims())
            new='研究另一件独立的事情，绝对不要参考前面对话、记忆或资料。'
            ws.receive_user_turn(new)
            backend=BranchBackend(ws,route='replace_goal')
            request={**ws.current_view(),'new_user_turn':deepcopy(ws.state['pending_turn'])}
            job=eng.job('scope-separation-test','turn_router','turn_route',request)
            backend.execute(job)
            ws.apply_turn_route(ws.result(job['id'])['output'],job['id'])
            now=ws.current_view()
            emitted=json.dumps(now,ensure_ascii=False)
            self.assertEqual(ws.state['phase'],'discover')
            self.assertEqual([s['text'] for s in now['task_sources']],[new])
            self.assertEqual(now['material_index'],[])
            self.assertNotIn(TASK,emitted)
            self.assertNotIn('OLD PRIVATE MATERIAL ONLY',emitted)
            self.assertFalse(ws.active_claims())
            self.assertTrue(old_claims)
            self.assertFalse(now['work_results'])
            self.assertEqual(now['recent_turns'],[])
            self.assertIsNone(now['last_verified_primary_turn'])
            self.assertEqual(ws.state['archived_goal_boundaries'][-1]['new_goal_source'], 'S3')

    def test_continuing_side_question_does_not_clear_primary_state(self):
        with tempfile.TemporaryDirectory() as td:
            ws=Workspace.create(Path(td)/'run',TASK,scope='points',backend='fixture')
            eng=Engine(ws,FixtureBackend(ws))
            self.assertEqual(eng.advance()['status'],'complete')
            old_stage=ws.state['task_navigation']['last_primary_scope']
            ws.receive_user_turn('side: explain a term from this analysis')
            eng.backend=BranchBackend(ws,route='side')
            self.assertEqual(eng.advance()['status'],'complete')
            self.assertEqual(ws.state['task_navigation']['last_primary_scope'],old_stage)
            self.assertTrue(ws.state['sources']['S1']['active'])

    def test_actual_workers_receive_novelty_closure_check(self):
        for role in ('compose','audit','schedule','value_frontier'):
            inst=instructions(role)
            self.assertIn('有效发现、竞争淘汰与收束审核', inst)
            self.assertIn('有用重组',inst)
        entry=(ROOT/'SKILL.md').read_text(encoding='utf8')
        self.assertIn('用户已知现象与真正新增发现',entry)
        self.assertIn('用户尚未报告',entry)
        self.assertIn('不参考此前对话',entry)
        router=instructions('turn_router')
        self.assertIn('replace_goal',router)
        self.assertIn('不参考以前的对话',router)

if __name__=='__main__':unittest.main()
