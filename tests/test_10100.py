"""10.10: epistemic information value and model-outside candidate survival.

These tests exercise the actual engine/store contracts, not GPT discovery.
Every hypothesized semantic improvement still requires live-model blind trials.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_runtime import Base, TASK, claim, unknown, work, draft_for, FixtureBackend
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.inquiry_frontier import pending_self_research, discovery_inquiries
from sd_runtime.common import StateDyneError


class InferenceValueTests(Base):
    def new_probe(self, *, origin='prediction', route='user', priority='important', kind='mechanism', prediction=True):
        ws = self.workspace(backend='fixture', scope='analysis')
        c=claim('N1', kind=kind)
        c['statement']='An omitted environmental permission system determines the event.'
        c['distinct_consequences']=(['Independent system B would change although visible mechanism A remains unchanged'] if prediction else [])
        q=unknown('U1', priority=priority)
        q.update(origin=origin, route=route, related_claims=['N1'],
                 question='Does the independent mechanism change B while A remains constant?',
                 why_it_matters='It would distinguish a missing permission rule from the visible mechanism.')
        j=ws.get_job('g1-reframe','reframe','work',ws.raw_view(),instructions('reframe'))
        self.receive(ws, j, work(claims=[c],unknowns=[q]))
        ws.merge_work(j['id'])
        d=ws.get_job('compose','compose','draft',ws.current_view(),instructions('compose'))
        return ws,d,draft_for(d), f'{j["id"]}:N1', f'{j["id"]}:U1'

    def submit(self, ws, job, output):
        self.receive(ws, job, output)
        ws.set_draft(job['id'])

    def effect(self, output, effect):
        x=output['information_dispositions'][0];x['decision_effect']=effect
        output['status']='needs_information'
        return x

    def test_explanatory_question_allowed_without_immediate_action_flip(self):
        ws,j,d,_,_=self.new_probe(origin='reframe')
        self.effect(d, 'changes_explanation')
        self.submit(ws,j,d)
        self.assertEqual(ws.state['draft']['output']['information_dispositions'][0]['treatment'], 'ask')

    def test_novel_mechanism_probe_allowed_as_user_question(self):
        ws,j,d,cid,qid=self.new_probe()
        self.effect(d,'opens_testable_mechanism')
        self.submit(ws,j,d)
        self.assertEqual(discovery_inquiries(ws)[0]['claim_ids'],[cid])

    def test_change_prediction_probe_allowed(self):
        ws,j,d,_,_=self.new_probe()
        self.effect(d,'changes_prediction')
        self.submit(ws,j,d)

    def test_unknown_with_no_distinct_prediction_cannot_claim_novel_prediction(self):
        ws,j,d,_,_=self.new_probe(prediction=False)
        self.effect(d,'opens_testable_mechanism')
        with self.assertRaisesRegex(StateDyneError,'differentiated predicted outcome'):
            self.submit(ws,j,d)

    def test_novel_user_inquiry_cannot_claim_complete_while_still_asking(self):
        ws,j,d,_,_=self.new_probe()
        self.effect(d,'opens_testable_mechanism')
        d['status']='complete'
        with self.assertRaisesRegex(StateDyneError,'fully completed explanation'):
            self.submit(ws,j,d)

    def test_novel_public_fact_cannot_be_outsourced_to_user(self):
        ws,j,d,_,_=self.new_probe(route='public_source')
        self.effect(d,'changes_explanation')
        with self.assertRaisesRegex(StateDyneError,'non-user information'):
            self.submit(ws,j,d)

    def test_deferred_selected_novel_hypothesis_requires_visible_reason(self):
        ws,j,d,_,_=self.new_probe()
        x=self.effect(d,'opens_testable_mechanism')
        x.update(treatment='defer',visible_question='',fallback_if_unknown='')
        d['question_groups']=[]
        # Stop claiming the previously asked question was visible.
        d['answer']=d['answer'].replace('Does the independent mechanism change B while A remains constant?','')
        d['status']='provisional'
        with self.assertRaisesRegex(StateDyneError,'silent suppression'):
            self.submit(ws,j,d)

    def test_deferred_novel_hypothesis_can_be_visible_and_conditional(self):
        ws,j,d,_,_=self.new_probe()
        x=self.effect(d,'opens_testable_mechanism')
        x.update(treatment='defer',visible_question='',fallback_if_unknown='本轮不能确定该预测，先保留两个条件性模型。')
        d['question_groups']=[]
        d['answer']=d['answer'].replace('Does the independent mechanism change B while A remains constant?','')+'\n'+x['fallback_if_unknown']
        d['status']='provisional'
        d['navigation']['expansion_offer']='如需继续研究，可核对那个独立环境机制的日志与预测。'
        d['answer']+='\n'+d['navigation']['expansion_offer']
        self.submit(ws,j,d)

    def test_rejected_novel_hypothesis_need_not_be_asked_or_in_answer(self):
        ws,j,d,cid,_=self.new_probe()
        x=self.effect(d,'opens_testable_mechanism')
        x.update(treatment='defer',visible_question='',fallback_if_unknown='')
        d['question_groups']=[]
        d['answer']=d['answer'].replace('Does the independent mechanism change B while A remains constant?','')
        d['claim_dispositions'][0].update(treatment='not_selected',reason='No observed result currently separates this from a much simpler explanation.')
        d['used_claim_ids']=[]
        d['status']='provisional'
        self.submit(ws,j,d)

    def test_multiple_identical_novel_questions_are_not_independent_discoveries(self):
        ws=self.workspace(backend='fixture',scope='analysis')
        c=claim('M1'); c['distinct_consequences']=['C changes unexpectedly.']
        q1=unknown('Q1');q1.update(origin='prediction', related_claims=['M1'])
        q2=deepcopy(q1);q2['local_id']='Q2'
        j=ws.get_job('supply','reframe','work',ws.raw_view(), instructions('reframe'))
        self.receive(ws,j,work(claims=[c],unknowns=[q1,q2]))
        ws.merge_work(j['id'])
        djob=ws.get_job('compose','compose','draft',ws.current_view(),instructions('compose'))
        d=draft_for(djob)
        for x in d['information_dispositions']: x['decision_effect']='changes_prediction'
        with self.assertRaisesRegex(StateDyneError,'Duplicate novel-discovery'):
            self.submit(ws,djob,d)

    def test_no_fixed_question_count_after_value_generalization(self):
        ws=self.workspace(backend='fixture',scope='analysis')
        c=claim('M1')
        qs=[]
        for i in range(9):
            q=unknown(f'Q{i}');q.update(question=f'Can you distinguish condition {i} from another cause?', related_claims=['M1'])
            qs.append(q)
        j=ws.get_job('supply','discovery','work',ws.raw_view(), instructions('discovery'))
        self.receive(ws,j,work(claims=[c],unknowns=qs));ws.merge_work(j['id'])
        djob=ws.get_job('compose','compose','draft',ws.current_view(),instructions('compose'))
        d=draft_for(djob)
        d['answer']+='\n'+'\n'.join(q['question'] for q in qs[3:])
        for x,q in zip(d['information_dispositions'],qs):
            x.update(treatment='ask',visible_question=q['question'],decision_effect='changes_explanation')
        d['status']='needs_information'
        from test_runtime import regroup_questions
        regroup_questions(d)
        self.submit(ws,djob,d)
        self.assertEqual(sum(x['treatment']=='ask' for x in ws.state['draft']['output']['information_dispositions']),9)


class AutonomousEvidenceTests(Base):
    def setup_pending(self, route='materials'):
        ws=self.workspace(backend='fixture')
        c=claim('M1'); c['distinct_consequences']=['If relation H exists, a separate machine logs B.']
        q=unknown('Q1',priority='important')
        q.update(route=route,origin='reframe', related_claims=['M1'])
        j=ws.get_job('supply','reframe','work',ws.raw_view(),instructions('reframe'))
        self.receive(ws,j,work(claims=[c],unknowns=[q]));ws.merge_work(j['id'])
        return ws, f'{j["id"]}:Q1'

    def test_obtainable_model_outside_info_scheduled_when_not_yet_investigated(self):
        ws,qid=self.setup_pending('materials')
        self.assertEqual(pending_self_research(ws),[qid])
        ws.state['investigated_unknowns']=[qid]
        self.assertEqual(pending_self_research(ws),[])

    def test_user_and_unavailable_questions_never_trigger_automatic_acquire(self):
        ws,qid=self.setup_pending('user')
        self.assertEqual(pending_self_research(ws),[])

    def test_public_search_requires_actual_web_permission(self):
        ws,qid=self.setup_pending('public_source')
        self.assertEqual(pending_self_research(ws),[])
        ws.state['config']['web_search_enabled']=True
        self.assertEqual(pending_self_research(ws),[qid])

    def test_scheduler_finish_is_intercepted_for_unchecked_material_evidence(self):
        ws,qid=self.setup_pending('materials')
        ws.state.update(phase='schedule',sweep_complete=True,portfolio_complete=True,blind_complete=True,
                        entry_review={'output':{'verdict':'pass'}})
        class RecordingFixture(FixtureBackend):
            def execute(self, job):
                if job['role']=='acquire':
                    self.captured=job
                    raise StateDyneError('real-autonomous-information-work-was-requested')
                return super().execute(job)
        provider=RecordingFixture(ws)
        with self.assertRaisesRegex(StateDyneError,'real-autonomous-information-work-was-requested'):
            Engine(ws,provider).advance()
        self.assertEqual(provider.captured['inputs']['targets'],[qid])
        self.assertEqual(ws.state['phase'],'operate')
        self.assertTrue(any(x['event']=='high_value_new_discovery_received_immediate_search_priority'
                            for x in ws.state['events']))

    def test_new_evidence_reopens_investigation_frontier(self):
        ws,qid=self.setup_pending('materials')
        ws.state['investigated_unknowns']=[qid]
        ws.update('New authorized evidence changes the causal comparison.',source_kind='user_reported')
        self.assertEqual(ws.state['investigated_unknowns'],[])

    def test_autonomous_acquire_happens_once_and_returns_to_delivery(self):
        from sd_runtime.backends import write_result
        ws=self.workspace(backend='fixture',scope='analysis')
        class Finder(FixtureBackend):
            def execute(self, job):
                if job['role']=='reframe':
                    c=claim('NEW1')
                    c['statement']='An independent service could select the transactions.'
                    c['distinct_consequences']=['A distinct upstream log will change without local lock contention.']
                    q=unknown('FIND1',priority='important')
                    q.update(route='materials',origin='prediction',related_claims=['NEW1'],
                             question='Is there evidence of upstream filtering?',
                             why_it_matters='It distinguishes upstream filtering from local locking.')
                    return write_result(self.ws.root,job,work(claims=[c],unknowns=[q]),kind='fixture',
                                        worker_ref=f'fixture-{job["id"]}',actual_model='synthetic-fixture')
                if job['role']=='compose':
                    d=draft_for(job)
                    # Fixture without the desired log: retain an explicit
                    # unresolved information need rather than fabricate data.
                    for v in d['information_dispositions']:
                        if v['treatment']=='ask' and next(q for q in job['inputs']['unknowns'] if q['id']==v['unknown_id'])['route']!='user':
                            d['answer']=d['answer'].replace(v['visible_question'],'')
                            v.update(treatment='unavailable',visible_question='',
                                     decision_effect='changes_explanation',
                                     reason='The registered materials lack the necessary log.')
                            d['status']='provisional'
                            v['fallback_if_unknown']='缺少上游日志，当前不能确定筛选机制是否存在，因此结论仍须附条件。'
                            d['answer']+='\n'+v['fallback_if_unknown']
                    from test_runtime import regroup_questions
                    regroup_questions(d)
                    return write_result(self.ws.root,job,d,kind='fixture',
                                        worker_ref=f'fixture-{job["id"]}',actual_model='synthetic-fixture')
                return super().execute(job)
        backend=Finder(ws)
        outcome=Engine(ws,backend).advance()
        self.assertEqual(ws.state['phase'],'done')
        self.assertEqual(outcome['status'],'provisional')
        attempts=[x for x in ws.state['events'] if x['event']=='model_outside_information_research_attempted']
        self.assertEqual(len(attempts),1)
        self.assertEqual(len([x for x in backend.requests if x['role']=='schedule']),1)
        self.assertTrue(ws.state['investigated_unknowns'])


if __name__=='__main__':
    unittest.main()
