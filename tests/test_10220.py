"""10.22: Generic intervention leverage/phase boundaries; synthetic tests only.

No personal story, company, market, hidden diagnosis or precomputed domain answer
is given to a solver by these tests. No real model invocation occurs here.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sd_runtime.common import StateDyneError
from sd_runtime.engine import instructions, Engine
from sd_runtime.frontstage import validate_frontstage
from sd_runtime.delivery_quality import validate_delivery_quality
from sd_runtime.store import Workspace
from test_runtime import Base, claim, work, draft_for, audit_for, FixtureBackend


class InterventionPhaseTests(Base):
    def setup_claims(self, scope='points'):
        ws=self.workspace(scope=scope,backend='fixture')
        output=work(claims=[
            claim('P1','point'),
            claim('P2','point'),
            claim('A1','action',deps=['P1','P2']),
            claim('A2','action',deps=['P2']),
            claim('L1','plan',deps=['A1','A2'])])
        j=self.make_job(ws,'change_forward');self.receive(ws,j,output);ws.merge_work(j['id'])
        ws.state['system_map']={'goal_basis':'explicit','goal_text':'Reduce the actual concurrent latency.'}
        ws.state['delivery_scope']=scope
        ids={key:f"{j['id']}:{key}" for key in ('P1','P2','A1','A2','L1')}
        return ws,ids

    def drafted(self,ws,scope):
        ws.state['delivery_scope']=scope
        return draft_for({'inputs':{**ws.current_view(),'delivery_scope':scope}})

    def acknowledged(self,ws,draft):
        ws.state['turn_history'].append({'release':{'answer_file':'answer.md'},
                                         'audit':{'output':{'verdict':'pass'}},
                                         'draft':{'output':deepcopy(draft)}})

    def review(self,ws,draft):
        job={'inputs':{'draft':draft,'claims':list(ws.active_claims().values()),
                       'adoption_relevant':ws.state.get('adoption_relevant',False),
                       'delivery_scope':ws.state['delivery_scope'],'foci':[]}}
        return audit_for(job)

    def test_points_action_plan_across_distinct_turns_no_repeat(self):
        ws,ids=self.setup_claims()
        d1=self.drafted(ws,'points')
        self.assertEqual({u['kind'] for u in d1['delivery_units']},{'point'})
        ws.check_delivery_contract(d1)
        self.acknowledged(ws,d1)
        d2=self.drafted(ws,'actions')
        self.assertEqual({u['kind'] for u in d2['delivery_units']},{'action'})
        self.assertEqual({u['claim_id'] for u in d2['delivery_units']},{ids['A1'],ids['A2']})
        ws.check_delivery_contract(d2)
        self.acknowledged(ws,d2)
        d3=self.drafted(ws,'plan')
        self.assertEqual({u['kind'] for u in d3['delivery_units']},{'plan'})
        ws.check_delivery_contract(d3)
        self.assertNotIn('干预点:',d3['answer'])
        self.assertNotIn('独立动作:',d3['answer'])

    def test_actions_not_visible_during_points_even_if_bound(self):
        ws,ids=self.setup_claims();d=self.drafted(ws,'points')
        extra={'kind':'action','claim_id':ids['A1'],'visible_text':'立即启用一个新动作。','comparison':'此时新动作能改变等待。'}
        d['answer']+='\n'+extra['visible_text']+'\n'+extra['comparison']
        d['delivery_units'].append(extra)
        d['used_claim_ids'].append(ids['A1'])
        with self.assertRaisesRegex(StateDyneError,'Stage boundary'):ws.check_delivery_contract(d)

    def test_analysis_cannot_delivery_points(self):
        ws,ids=self.setup_claims('analysis');d=self.drafted(ws,'points')
        ws.state['delivery_scope']='analysis'
        with self.assertRaisesRegex(StateDyneError,'Stage boundary'):ws.check_delivery_contract(d)

    def test_direct_explicit_actions_request_can_build_points_then_actions(self):
        ws,ids=self.setup_claims('actions');d=self.drafted(ws,'actions')
        self.assertEqual({u['kind'] for u in d['delivery_units']},{'point','action'})
        ws.check_delivery_contract(d)

    def test_direct_explicit_plan_request_can_order_all_stages(self):
        ws,ids=self.setup_claims('plan');d=self.drafted(ws,'plan')
        self.assertEqual({u['kind'] for u in d['delivery_units']},{'point','action','plan'})
        ws.check_delivery_contract(d)
        self.assertEqual([u['kind'] for u in d['delivery_units']],sorted([u['kind'] for u in d['delivery_units']],key={'point':0,'action':1,'plan':2}.get))

    def test_action_only_without_prior_audited_points_fails(self):
        ws,ids=self.setup_claims('actions');d=self.drafted(ws,'actions')
        d['delivery_units']=[u for u in d['delivery_units'] if u['kind']=='action']
        d['used_claim_ids']=[cid for cid in d['used_claim_ids'] if cid not in (ids['P1'],ids['P2'])]
        with self.assertRaises(StateDyneError):ws.check_delivery_contract(d)

    def test_unreleased_old_points_cannot_be_reused(self):
        ws,ids=self.setup_claims();d=self.drafted(ws,'points')
        ws.state['turn_history'].append({'release':None,'audit':{'output':{'verdict':'pass'}},'draft':{'output':d}})
        self.assertEqual(ws.previously_delivered_interventions()['point'],set())

    def test_combinations_use_real_points_and_text_anchors(self):
        ws,ids=self.setup_claims('points');d=self.drafted(ws,'points')
        a=self.review(ws,d)
        r=a['point_value_reviews'][0]
        r['combination_mode']='necessary_joint';r['companion_point_ids']=[ids['P2']]
        r['joint_value']='Two independently present bottlenecks must both be cleared for throughput to change.'
        with self.assertRaisesRegex(StateDyneError, 'exact visible answer'):
            validate_delivery_quality(ws,a,d)
        visible_joint='只有共享资源与外部限流同时约束时，两个干预点联合改变才有额外收益；否则单点更划算。'
        d['answer'] += '\n' + visible_joint
        r['user_visible_combination']=visible_joint
        validate_delivery_quality(ws,a,d)
        del r['companion_point_ids'][:]
        with self.assertRaisesRegex(StateDyneError,'paired point'):validate_delivery_quality(ws,a,d)

    def test_point_rank_reason_must_appear_in_actual_answer(self):
        ws,_=self.setup_claims('points');d=self.drafted(ws,'points');a=self.review(ws,d)
        a['point_value_reviews'][0]['user_visible_priority']='A backstage sentence missing from visible output.'
        with self.assertRaisesRegex(StateDyneError,'visible in this exact turn'):validate_delivery_quality(ws,a,d)

    def test_all_newly_visible_points_checked_no_arbitrary_ceiling(self):
        ws,_=self.setup_claims('points');d=self.drafted(ws,'points');a=self.review(ws,d)
        self.assertEqual(len(a['point_value_reviews']),2)
        a['point_value_reviews']=a['point_value_reviews'][:1]
        with self.assertRaisesRegex(StateDyneError,'Every newly visible intervention point'):validate_delivery_quality(ws,a,d)

    def test_unjustified_adoption_skip_fails_only_when_material(self):
        ws,_=self.setup_claims('points');d=self.drafted(ws,'points');a=self.review(ws,d)
        validate_delivery_quality(ws,a,d)
        ws.state['adoption_relevant']=True
        with self.assertRaisesRegex(StateDyneError,'cannot be skipped'):validate_delivery_quality(ws,a,d)
        d['answer']+='\n需要同时保留现有使用者真实得到的好处，检验新条件是否可行，而不是要求马上100%相信。'
        a['change_adoption_review'].update({'status':'analysed','user_visible_anchor':'需要同时保留现有使用者真实得到的好处，检验新条件是否可行，而不是要求马上100%相信。'})
        validate_delivery_quality(ws,a,d)

    def test_audit_cannot_pass_if_future_phase_content_declared(self):
        ws,_=self.setup_claims('points');d=self.drafted(ws,'points');a=self.review(ws,d)
        a['stage_boundary_review']['premature_future_content']=True
        with self.assertRaisesRegex(StateDyneError,'jumped into a future stage'):validate_delivery_quality(ws,a,d)

    def test_frontstage_prevents_obvious_unregistered_next_stage(self):
        ws,_=self.setup_claims('points');d=self.drafted(ws,'points')
        for section in ('\n## 具体动作\n每天增加记录。','\n## 完整实施方案\n未来一个月。'):
            with self.subTest(section=section),self.assertRaisesRegex(StateDyneError,'stage jumped'):
                validate_frontstage(ws,{**d,'answer':d['answer']+section})

    def test_frontstage_rejects_unexplained_internal_meta_phrase(self):
        ws,_=self.setup_claims('points');d=self.drafted(ws,'points')
        with self.assertRaisesRegex(StateDyneError,'internal analysis language'):
            validate_frontstage(ws,{**d,'answer':d['answer']+'\n更节约且更贴合原话的解释是'})

    def test_eleventh_independent_point_not_arbitrarily_truncated(self):
        ws,ids=self.setup_claims('points')
        template=deepcopy(ws.state['claims'][ids['P1']])
        for i in range(3,12):
            c=deepcopy(template)
            c['id']=f'INDEPENDENT-P{i}'
            c['statement']=f'Distinct changeable relation {i} changes a separate causal link.'
            ws.state['claims'][c['id']]=c
        d=self.drafted(ws,'points')
        point_units=[u for u in d['delivery_units'] if u['kind']=='point']
        self.assertEqual(len(point_units),11)
        self.assertEqual(len({u['claim_id'] for u in point_units}),11)
        ws.check_delivery_contract(d)
        a=self.review(ws,d)
        self.assertEqual(len(a['point_value_reviews']),11)
        validate_delivery_quality(ws,a,d)

    def test_real_worker_gets_intervention_and_change_rule_not_case_answer(self):
        for role in ('change_forward','change_backward','change_portfolio','compose','audit'):
            with self.subTest(role=role):
                p=instructions(role)
                self.assertIn('组合寻找',p)
                self.assertIn('旧自动反应仍在时怎样生成新行为',p)
                for phrase in ('fixture-key-a','fixture-key-b','fixture-subject-a','fixture-domain-a','fixture-company-a'):
                    self.assertNotIn(phrase,p)
        # keep the initial seven independent workers, the following specialized
        # portfolio runs only after forward/backward contributions are merged.
        ws,_=self.setup_claims('points');eng=Engine(ws,FixtureBackend(ws))
        self.assertIn('change_portfolio',eng.ws.state.get('phase','')+' '+instructions('change_portfolio'))


if __name__=='__main__':unittest.main()
