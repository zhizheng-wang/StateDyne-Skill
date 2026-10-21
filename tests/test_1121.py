"""11.2.1: verified bridge regressions for discovery, environment and continuation.

These checks execute real controller methods on synthetic states. They cannot
certify that a model's environmental inference or innovation is actually true.
"""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.backends import NativeBackend, write_result
from sd_runtime.priority_dispatch import priority_batch
from sd_runtime.research_agenda import (agenda, meaningful_frontier,
    unattempted_open_relations, environment_relation_ids)
from test_runtime import TASK, work


class FrontierContinuityTests(unittest.TestCase):
    def ws(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Workspace.create(Path(td.name) / 'work', TASK, scope='analysis', backend='native')

    def schedule_now(self, ws, capacity=12):
        ws.state.update(phase='schedule', sweep_complete=True, portfolio_complete=True,
            blind_complete=True, entry_review={'output':{'verdict':'pass'}})
        ws.state['config']['max_parallel_operations'] = capacity
        backend=NativeBackend(ws.root,ws.state['sources'],ws.state['config'])
        result=Engine(ws,backend).advance()
        self.assertEqual(result['status'],'waiting_for_real_workers')
        return [ws.job_request(jid) for jid in result['jobs']]

    def open(self,ws,oid='independent', **extra):
        ws.state['exploration_opportunities'][oid]={
            'id':oid, 'description':'Compare an independently overlooked route to the observed outcome.',
            'origin_job':'unclassified', 'state':'open', 'attempts':0,
            'system_priority':'important', **extra}
        return oid

    def test_general_discovery_gets_immediate_worker_not_only_finish_gate(self):
        ws=self.ws();self.open(ws)
        jobs=self.schedule_now(ws)
        self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['role'],'reframe_informed')
        self.assertEqual(jobs[0]['inputs']['opportunity_ids'],['independent'])
        self.assertFalse(any(j['role']=='schedule' for j in ws.state['jobs'].values()))

    def test_real_environment_scout_opportunity_uses_deep_environment_operator(self):
        ws=self.ws()
        origin=ws.get_job('original-environment','environment_scout','work',ws.raw_view(),instructions('environment_scout'))
        oid=self.open(ws,'env-opportunity')
        ws.state['exploration_opportunities'][oid]['origin_job']=origin['id']
        self.assertEqual(environment_relation_ids(ws.state,[oid]),[oid])
        jobs=self.schedule_now(ws)
        self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['role'],'environment')
        self.assertIn('环境',jobs[0]['instructions'])
        self.assertEqual(jobs[0]['inputs']['opportunity_ids'],[oid])

    def test_material_environment_dimension_does_not_get_generic_reframe(self):
        ws=self.ws()
        oid=self.open(ws,'context-gap',system_dimension='rules_incentives')
        jobs=self.schedule_now(ws)
        self.assertEqual([j['role'] for j in jobs],['environment'])
        self.assertEqual(jobs[0]['inputs']['opportunity_ids'],[oid])

    def test_material_environment_unknown_triggers_deepening_even_without_opportunity(self):
        ws=self.ws()
        ws.state['unknowns']['env-q']={
            'id':'env-q', 'question':'Who really controls the external approval decision?',
            'priority':'important', 'state':'open', 'origin':'environment',
            'route':'unavailable', 'related_claims':[]}
        jobs=self.schedule_now(ws)
        self.assertEqual([j['role'] for j in jobs],['environment'])
        self.assertEqual(jobs[0]['inputs']['targets'],['env-q'])
        ws.state['environment_questions_attempted']=['env-q']
        from sd_runtime.research_agenda import unattempted_environment_questions
        self.assertEqual(unattempted_environment_questions(ws.state),[])

    def test_unrelated_ordinary_problem_does_not_force_environment(self):
        ws=self.ws();self.open(ws, 'model-relation')
        self.assertEqual(environment_relation_ids(ws.state,['model-relation']),[])
        self.assertEqual([j['role'] for j in self.schedule_now(ws)], ['reframe_informed'])

    def test_mixed_frontiers_are_not_starved_by_small_worker_capacity(self):
        models=['M1','M2','M3']
        environment=['E1','E2','E3']
        facts=['U1','U2','U3']
        selected=[]
        for turn in range(3):
            tasks=priority_batch(model_opportunities=models,environment_opportunities=environment,
                research_unknowns=facts,evidence_reframes=[],capacity=1,rotation=turn)
            self.assertEqual(len(tasks),1)
            selected.append(tasks[0]['operator'])
            identifier=(tasks[0]['opportunity_ids'] or tasks[0]['target_ids'])[0]
            for group in (models,environment,facts):
                if identifier in group: group.remove(identifier)
        self.assertEqual(selected,['reframe','environment','acquire'])

    def test_null_attempt_is_recorded_but_not_reoffered_as_new_discovery(self):
        ws=self.ws();oid=self.open(ws,'already-inspected')
        job=ws.get_job('real-null-study','reframe_informed','work',ws.current_view(),instructions('reframe'))
        output=work(claims=[],unknowns=[])
        output['no_increment_reason']='Independent search found no distinct prediction or feasible alternative under available evidence.'
        write_result(ws.root,job,output,kind='fixture',worker_ref='synthetic-worker',actual_model='scripted-fixture')
        ws.mark_opportunities_attempted({'opportunity_ids':[oid],'operator':'reframe'},job_id=job['id'])
        item=ws.state['exploration_opportunities'][oid]
        self.assertEqual(item['state'],'examined')
        self.assertEqual(item['attempt_outcome'],'no_increment')
        # Simulate an older or inconsistent storage process leaving state=open.
        item['state']='open'
        self.assertEqual(unattempted_open_relations(ws.state),[])
        self.assertEqual([x for x in agenda(ws.state) if x['id']==oid],[])
        self.assertFalse(meaningful_frontier(ws.state))

    def test_attempted_unknown_remains_conditional_not_another_call_to_action(self):
        ws=self.ws();ws.state['unknowns']['q1']={
            'id':'q1','question':'What does the independent public record say?',
            'route':'public_source','priority':'important','state':'defer','origin_job':'environment-scout'}
        ws.state['investigated_unknowns']=['q1']
        entries=[x for x in agenda(ws.state) if x['id']=='q1']
        self.assertEqual(len(entries),1)
        self.assertFalse(entries[0]['ready'])
        self.assertEqual(entries[0]['route'],'awaiting_changed_evidence')
        self.assertFalse(meaningful_frontier(ws.state))
        self.assertFalse(ws.research_frontier()[0]['ready'])

    def test_side_branch_does_not_resurrect_stale_research_offer(self):
        ws=self.ws()
        ws.state['interaction_mode']='side'
        ws.state['task_thread']['research_frontier']=[{
            'id':'already-done','kind':'new_relation','focus':'Previous recommendation',
            'route':'self_research','priority':'important'}]
        self.assertEqual(ws.research_frontier(),[])
        ws.state['exploration_opportunities']['already-done']={
            'id':'already-done','description':'Previous recommendation','origin_job':'old',
            'state':'examined','attempts':1}
        self.assertEqual(ws.research_frontier(),[])

    def test_navigation_does_not_force_illusory_search_for_attempted_item(self):
        ws=self.ws();oid=self.open(ws,'attempted-open')
        ws.state['exploration_opportunities'][oid]['attempts']=1
        ws.state['delivery_scope']='plan'
        nav={'mode':'primary','primary_stage':'plan','next_stage':'none',
             'next_offer':'','expansion_offer':'','visible_anchor':'',
             'reason':'The authorized plan was delivered; no new untested opening exists.'}
        ws.check_navigation_contract({'navigation':nav,'answer':'Current plan has been delivered.'})

    def test_uncertainty_is_reenabled_when_new_primary_evidence_arrives(self):
        ws=self.ws()
        ws.state['unknowns']['q1']={
            'id':'q1','question':'Check a changed public record',
            'route':'public_source','priority':'important','state':'defer'}
        ws.state['investigated_unknowns']=['q1']
        self.assertFalse(meaningful_frontier(ws.state))
        ws.state['phase']='done'
        ws.update('A new verifiable policy document has appeared.')
        self.assertEqual(ws.state['investigated_unknowns'],[])
        self.assertTrue(meaningful_frontier(ws.state))


if __name__=='__main__': unittest.main()
