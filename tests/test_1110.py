"""11.1 outcome, consent-to-stop-this-turn and genuine continuation regressions.

Structural/prompt tests only: they do not demonstrate true model creativity.
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
from sd_runtime.engine import Engine,instructions
from sd_runtime.backends import write_result
from sd_runtime.schemas import validate,SCHEMAS
from sd_runtime.common import StateDyneError
from test_runtime import FixtureBackend,TASK

class RealizationAndQuietReplyTests(unittest.TestCase):
    def make_ws(self, scope='points'):
        td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup)
        ws=Workspace.create(Path(td.name)/'run',TASK,scope=scope,backend='fixture')
        self.assertEqual(Engine(ws,FixtureBackend(ws)).advance()['status'],'complete')
        return ws

    def test_realization_rule_actually_reaches_workers_not_only_readme(self):
        for role in ('compose','audit','schedule','value_frontier','goal_scout',
                     'change_forward','change_backward','change_portfolio'):
            inst=instructions(role)
            self.assertIn('成果生成与路径实现',inst)
            self.assertIn('用户已经有的能力',inst)
            self.assertIn('删除泛泛的日程',inst)
        self.assertIn('成果生成与路径实现',(ROOT/'SKILL.md').read_text(encoding='utf8'))
        self.assertIn('quiet_reply_quote',instructions('compose'))
        self.assertIn('quiet_reply_quote',instructions('audit'))

    def test_quiet_reply_requires_real_latest_user_quote_and_does_not_kill_frontier(self):
        ws=self.make_ws()
        original_scope=ws.state['task_navigation']['last_primary_scope']
        user='我现在只想要一个可以直接用的办法，不想再继续分析了。'
        sid=ws.add_source('New side request',user,kind='user_reported',is_task=False,
                          precision='as_reported')
        ws.state['current_turn_source_id']=sid
        ws.state['interaction_mode']='side'
        ws.state['exploration_opportunities']['valuable']={
            'id':'valuable','description':'调查不同的结果生成条件能否改变最优动作',
            'state':'open','attempts':0,'origin_job':'independent','system_priority':'important'}
        draft=deepcopy(ws.state['draft']['output'])
        draft['navigation'].update(mode='side',primary_stage=original_scope,
            next_stage='plan' if original_scope=='actions' else 'actions',
            next_offer='',expansion_offer='',visible_anchor='',
            quiet_reply_quote='不想再继续分析了')
        validate(draft,SCHEMAS['draft'])
        ws.check_navigation_contract(draft)
        self.assertTrue(ws.research_frontier())
        self.assertEqual(ws.state['task_navigation']['last_primary_scope'],original_scope)
        # Without explicit user preference, material unfinished work MUST
        # remain visible: quiet is not a general loophole for superficial work.
        draft['navigation'].pop('quiet_reply_quote')
        with self.assertRaisesRegex(StateDyneError,'next-step bridge|continuation|continued'):
            ws.check_navigation_contract(draft)
        draft['navigation']['quiet_reply_quote']='我已经完全决定不做任何研究了' # invented
        with self.assertRaisesRegex(StateDyneError,'verbatim'):
            ws.check_navigation_contract(draft)

    def test_quiet_reply_does_not_change_frozen_next_stage(self):
        ws=self.make_ws('points')
        before=deepcopy(ws.state['task_navigation'])
        ws.state['exploration_opportunities']['X']={
            'id':'X','description':'探索尚未识别的新机制','state':'open','attempts':0,
            'origin_job':'blind','system_priority':'important'}
        user='我暂时不想继续研究了，只要一个简单的结果。'
        sid=ws.add_source('User message',user,kind='user_reported',is_task=False,
                          precision='as_reported')
        ws.state['current_turn_source_id']=sid
        draft=deepcopy(ws.state['draft']['output'])
        draft['navigation'].update(next_offer='',expansion_offer='',visible_anchor='',
                                   quiet_reply_quote='我暂时不想继续研究了')
        ws.check_navigation_contract(draft)
        self.assertEqual(ws.state['task_navigation'],before)
        ws.continue_stage('next')
        self.assertEqual(ws.state['scope'],'actions')

if __name__=='__main__': unittest.main()
