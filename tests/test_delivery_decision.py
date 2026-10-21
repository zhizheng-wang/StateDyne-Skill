"""Focused negative tests for intervention delivery and decision-impact gates.

These tests deliberately do not pretend to evaluate true semantic quality or
whether a model can find hidden facts. They verify observable contracts only.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_runtime import Base, TASK, claim, unknown, work, draft_for
from sd_runtime.common import StateDyneError
from sd_runtime.engine import instructions


class DeliveryContractTests(Base):
    def setup_delivery(self, scope, claims):
        ws = self.workspace(backend='fixture', scope=scope)
        d = ws.get_job('supply', 'change', 'work', ws.raw_view(), instructions('change'))
        self.receive(ws, d, work(claims=claims))
        ws.merge_work(d['id'])
        j = ws.get_job('compose', 'compose', 'draft', ws.current_view(), instructions('compose'))
        return ws, j, draft_for(j)

    def submit(self, ws, job, product):
        self.receive(ws, job, product)
        ws.set_draft(job['id'])

    def test_actions_need_visible_points_before_actions(self):
        ws, job, draft = self.setup_delivery('actions', [claim('P1', 'point'), claim('A1', 'action', ['P1'])])
        self.submit(ws, job, draft)
        self.assertEqual([x['kind'] for x in ws.state['draft']['output']['delivery_units']], ['point', 'action'])

    def test_action_without_visible_point_is_rejected(self):
        ws, job, draft = self.setup_delivery('actions', [claim('P1', 'point'), claim('A1', 'action', ['P1'])])
        draft['delivery_units'] = [x for x in draft['delivery_units'] if x['kind'] != 'point']
        with self.assertRaisesRegex(StateDyneError, 'missing from actual delivery'):
            self.submit(ws, job, draft)

    def test_unmentioned_action_cannot_be_silently_counted_as_delivered(self):
        ws, job, draft = self.setup_delivery('actions', [claim('P1', 'point'), claim('A1', 'action', ['P1'])])
        draft['delivery_units'] = [x for x in draft['delivery_units'] if x['kind'] != 'action']
        with self.assertRaisesRegex(StateDyneError, 'missing from actual delivery'):
            self.submit(ws, job, draft)

    def test_point_needs_visible_comparative_rationale(self):
        ws, job, draft = self.setup_delivery('points', [claim('P1', 'point')])
        draft['delivery_units'][0]['comparison'] = ''
        with self.assertRaisesRegex(StateDyneError, 'comparative selection'):
            self.submit(ws, job, draft)

    def test_visible_order_must_be_point_then_action(self):
        ws, job, draft = self.setup_delivery('actions', [claim('P1', 'point'), claim('A1', 'action', ['P1'])])
        draft['delivery_units'].reverse()
        with self.assertRaisesRegex(StateDyneError, 'ordered'):
            self.submit(ws, job, draft)

    def test_answer_itself_must_show_point_before_action(self):
        ws, job, draft = self.setup_delivery('actions', [claim('P1', 'point'), claim('A1', 'action', ['P1'])])
        point, action = draft['delivery_units']
        # Reverse complete visible stage sections, including the newly required
        # independent-value sentence; old two-sentence fixtures are insufficient.
        point_at = draft['answer'].index(point['visible_text'])
        action_at = draft['answer'].index(action['visible_text'])
        self.assertLess(point_at,action_at)
        draft['answer'] = (draft['answer'][:point_at] +
                           draft['answer'][action_at:] + '\n' +
                           draft['answer'][point_at:action_at])
        with self.assertRaisesRegex(StateDyneError, 'real answer'):
            self.submit(ws, job, draft)

    def test_plan_requires_prior_action_claim_in_graph(self):
        ws = self.workspace(backend='fixture', scope='plan')
        j = ws.get_job('bad-plan', 'change', 'work', ws.raw_view(), instructions('change'))
        self.receive(ws, j, work(claims=[claim('P1','point'), claim('A1','action',['P1']), claim('L1','plan',[])]))
        with self.assertRaisesRegex(StateDyneError, 'plan must map'):
            ws.merge_work(j['id'])

    def test_complete_plan_requires_all_three_visible_stages(self):
        ws, job, draft = self.setup_delivery('plan', [claim('P1', 'point'), claim('A1', 'action', ['P1'])])
        with self.assertRaisesRegex(StateDyneError, 'Requested intervention stages are missing'):
            self.submit(ws, job, draft)

    def test_plan_with_point_action_plan_passes(self):
        ws, job, draft = self.setup_delivery('plan', [claim('P1', 'point'), claim('A1', 'action', ['P1']), claim('L1', 'plan', ['A1'])])
        self.submit(ws, job, draft)
        self.assertEqual([x['kind'] for x in ws.state['draft']['output']['delivery_units']], ['point', 'action', 'plan'])

    def test_impossible_intervention_can_be_provisional_without_fabrication(self):
        ws, job, draft = self.setup_delivery('actions', [claim('M1', 'mechanism')])
        draft['status'] = 'provisional'
        draft['delivery_limit_reason'] = '目前没有获得足以安全选点和执行的条件信息。'
        draft['answer'] += '\n'+draft['delivery_limit_reason']
        self.submit(ws, job, draft)

    def test_missing_delivery_cannot_claim_complete(self):
        ws, job, draft = self.setup_delivery('actions', [claim('M1', 'mechanism')])
        draft['status'] = 'complete'
        with self.assertRaisesRegex(StateDyneError, 'Requested intervention stages are missing'):
            self.submit(ws, job, draft)

    def test_no_fixed_point_count(self):
        points = [claim('P'+str(i), 'point') for i in range(8)]
        ws, job, draft = self.setup_delivery('points', points)
        self.submit(ws, job, draft)
        self.assertEqual(len(ws.state['draft']['output']['delivery_units']), 8)


class InformationFrontierTests(Base):
    def setup_unknown(self, route='user', priority='blocking'):
        ws = self.workspace(backend='fixture', scope='analysis')
        q = unknown('Q1', priority=priority)
        q['route'] = route
        j = ws.get_job('supply','discovery','work',ws.raw_view(),instructions('discovery'))
        self.receive(ws,j,work(claims=[claim()],unknowns=[q]))
        ws.merge_work(j['id'])
        dj = ws.get_job('compose','compose','draft',ws.current_view(),instructions('compose'))
        return ws, dj, draft_for(dj)

    def submit(self, ws, job, draft):
        self.receive(ws,job,draft)
        ws.set_draft(job['id'])

    def test_ask_only_if_decision_can_change(self):
        ws, job, draft = self.setup_unknown()
        draft['information_dispositions'][0]['decision_effect'] = 'refines_only'
        with self.assertRaisesRegex(StateDyneError,'cannot change'):
            self.submit(ws,job,draft)

    def test_no_default_question_character_ceiling(self):
        ws, job, draft = self.setup_unknown()
        q = draft['information_dispositions'][0]
        old = q['visible_question']
        extended = '请在你确实知道的范围里说明：' + old + '，尤其指出会导致不同选择的已有事实；无法确定时不用猜。' * 16
        q['visible_question'] = extended
        draft['answer'] = draft['answer'].replace(old, extended)
        self.submit(ws,job,draft)
        self.assertGreater(len(extended),220)

    def test_public_facts_must_not_be_outsourced_to_user(self):
        ws, job, draft = self.setup_unknown(route='public_source')
        with self.assertRaisesRegex(StateDyneError,'non-user information'):
            self.submit(ws,job,draft)

    def test_downgraded_blocker_needs_visible_robust_result(self):
        ws, job, draft = self.setup_unknown()
        disp = draft['information_dispositions'][0]
        disp.update(treatment='defer', visible_question='', decision_effect='refines_only', fallback_if_unknown='')
        draft['question_groups']=[]
        draft['status'] = 'complete'
        with self.assertRaisesRegex(StateDyneError,'visible robust'):
            self.submit(ws,job,draft)

    def test_robust_result_can_stop_endless_questioning(self):
        ws, job, draft = self.setup_unknown()
        disp = draft['information_dispositions'][0]
        reason = '即使这一未知有不同答案，当前保留的低风险选择和退出条件仍然相同。'
        disp.update(treatment='defer', visible_question='', decision_effect='refines_only', fallback_if_unknown=reason)
        draft['question_groups']=[]
        draft['answer'] += '\n' + reason
        draft['status'] = 'complete'
        self.submit(ws,job,draft)
        self.assertEqual(ws.state['draft']['output']['status'],'complete')

    def test_decision_changing_unknown_still_prevents_complete(self):
        ws, job, draft = self.setup_unknown()
        draft['status'] = 'complete'
        with self.assertRaisesRegex(StateDyneError,'Cannot claim full completion'):
            self.submit(ws,job,draft)
