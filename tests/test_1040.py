"""10.4.0 observable-contract regression tests (not semantic/model benchmarks)."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from sd_runtime.engine import Engine
from sd_runtime.backends import write_result
from sd_runtime.common import StateDyneError
from sd_runtime.store import Workspace
from test_runtime import FixtureBackend, work, TASK


class NewArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)

    def workspace(self, **kwargs):
        return Workspace.create(self.root / 'case', TASK, **kwargs)

    def test_ten_raw_only_workers_are_dispatched_together(self):
        ws = self.workspace(backend='fixture')
        backend = FixtureBackend(ws)
        result = Engine(ws, backend).advance()
        self.assertEqual(result['assurance'], 'simulation_only')
        roles = ('frame','system_map','goal_scout','selection_scout','relation_scout','discovery','reframe','contrast_probe','environment_scout','blind_challenge')
        self.assertEqual(set(j['role'] for j in backend.requests[:10]), set(roles))
        baseline = backend.requests[0]['inputs']['task_sources']
        for job in backend.requests[:10]:
            self.assertEqual(set(job['inputs']), {'task_sources','material_index','output_scope'})
            self.assertEqual(job['inputs']['task_sources'], baseline)
            self.assertNotIn('claims', job['inputs'])
        self.assertEqual(len(next(x for x in backend.requests if x['role']=='entry_review')['inputs']['first_pass_job_ids']),8)
        self.assertEqual(ws.state['config']['parallel_workers'], 12)

    def test_initial_workers_actually_run_concurrently(self):
        ws = self.workspace(backend='fixture')
        gate = threading.Barrier(10)
        class Concurrent(FixtureBackend):
            def execute(self, job):
                if job['role'] in ('frame','system_map','goal_scout','selection_scout','relation_scout','discovery','reframe','contrast_probe','environment_scout','blind_challenge'):
                    gate.wait(timeout=4)
                return super().execute(job)
        self.assertEqual(Engine(ws, Concurrent(ws)).advance()['assurance'], 'simulation_only')

    def test_parallel_search_uses_same_snapshot_and_records_opportunity(self):
        ws = self.workspace(backend='fixture', config={'max_operations':4, 'max_parallel_operations':3})
        class Parallel(FixtureBackend):
            def execute(self, job):
                if job['role']=='discovery':
                    found=self.ws.result(job['id'])
                    if found: return found
                    self.requests.append(deepcopy(job))
                    output=work();output['opportunities']=['Independently predict the queue behaviour after changing request ordering.']
                    return write_result(self.ws.root,job,output,kind='fixture',worker_ref='fixture-'+job['id'],actual_model='fixture')
                if job['role']=='schedule':
                    found=self.ws.result(job['id'])
                    if found: return found
                    self.requests.append(deepcopy(job))
                    oid=next(iter(self.ws.state['exploration_opportunities']))
                    ops=('deepen','predict','transfer')
                    decisions=[{'operator':op,'target_ids':[],'opportunity_ids':[oid] if i==1 else [],
                                'rationale':f'Test distinct {op} relationship.',
                                'expected_difference':f'New {op} conditional prediction.',
                                'strongest_alternative':'Ask the user for more data.',
                                'why_parallel_safe':'Uses only the same prior snapshot, not other search outputs.'}
                               for i,op in enumerate(ops)]
                    output={'decisions':decisions,'finish':False,'finish_reason':'',
                            'delivery_scope':'analysis','adoption_relevant':False,'scope_reason':'Initial analysis requested.'}
                    return write_result(self.ws.root,job,output,kind='fixture',worker_ref='fixture-'+job['id'],actual_model='fixture')
                return super().execute(job)
        backend=Parallel(ws)
        result=Engine(ws,backend).advance()
        self.assertEqual(result['assurance'],'simulation_only')
        operations=[j for j in backend.requests if j['role'] in ('deepen','predict','transfer')]
        self.assertEqual(set(j['role'] for j in operations), {'deepen','predict','transfer'})
        self.assertEqual([j['inputs']['claims'] for j in operations], [operations[0]['inputs']['claims']]*3)
        oid=next(iter(ws.state['exploration_opportunities']))
        self.assertEqual(ws.state['exploration_opportunities'][oid]['attempts'], 2)  # autonomous discovery before scripted follow-up
        self.assertEqual(ws.state['operations_done'],4)
        self.assertTrue(ws.state['budget_limited'])

    def test_duplicate_parallel_operators_are_rejected(self):
        ws=self.workspace(backend='fixture')
        class Duplicate(FixtureBackend):
            def execute(self,job):
                if job['role']=='schedule':
                    self.requests.append(deepcopy(job))
                    task={'operator':'deepen','target_ids':[],'opportunity_ids':[],
                          'rationale':'Explore a relationship','expected_difference':'Find one new prediction',
                          'strongest_alternative':'Acquire evidence', 'why_parallel_safe':'Independent work'}
                    result={'decisions':[task,dict(task)], 'finish':False,'finish_reason':'',
                            'delivery_scope':'analysis','adoption_relevant':False,'scope_reason':'analysis'}
                    return write_result(self.ws.root,job,result,kind='fixture',worker_ref='fixture-'+job['id'],actual_model='fixture')
                return super().execute(job)
        with self.assertRaisesRegex(StateDyneError,'Duplicate parallel work'):
            Engine(ws, Duplicate(ws)).advance()

    def test_stage_continuation_reuses_blind_evidence_but_reaudits(self):
        ws=self.workspace(backend='fixture',scope='analysis')
        backend=FixtureBackend(ws)
        first=Engine(ws,backend).advance()
        first_count=len([r for r in backend.requests if r['role'] in ('frame','system_map','goal_scout','selection_scout','relation_scout','discovery','reframe','contrast_probe','environment_scout','blind_challenge')])
        self.assertEqual(first_count,10)
        audit_first=first['audit_job']
        ws.continue_stage('points')
        second=Engine(ws,backend).advance()
        self.assertEqual(second['assurance'],'simulation_only')
        self.assertNotEqual(audit_first, second['audit_job'])
        self.assertEqual(len([r for r in backend.requests if r['role'] in ('frame','system_map','goal_scout','selection_scout','relation_scout','discovery','reframe','contrast_probe','environment_scout','blind_challenge')]),10)
        self.assertIn('干预点:', ws.state['draft']['output']['answer'])
        self.assertEqual(ws.state['delivery_cycle'],1)
        self.assertEqual(len(ws.state['turn_history']),1)
        self.assertTrue(ws.state['turn_history'][0]['answer'])
        Engine(ws,backend).verify_release()
        ws.continue_stage('actions')
        third=Engine(ws,backend).advance()
        self.assertEqual(third['assurance'],'simulation_only')
        self.assertNotEqual(third['audit_job'],second['audit_job'])
        self.assertIn('独立动作:',ws.state['draft']['output']['answer'])
        self.assertEqual(len([r for r in backend.requests if r['role'] in ('frame','system_map','goal_scout','selection_scout','relation_scout','discovery','reframe','contrast_probe','environment_scout','blind_challenge')]),10)

    def test_continuation_before_release_is_blocked(self):
        ws=self.workspace(backend='native')
        with self.assertRaisesRegex(StateDyneError,'fully released stage'):
            ws.continue_stage('points')

    def test_public_evidence_provenance_is_not_user_testimony(self):
        ws=self.workspace()
        sid=ws.update('Public quarterly sales growth: 8%.',source_kind='retrieved_public',
                      source_label='Official filed document',source_url='https://example.org/filing')
        self.assertEqual(ws.state['sources'][sid]['kind'],'retrieved_public')
        self.assertFalse(ws.state['sources'][sid]['is_task'])
        self.assertEqual(ws.state['sources'][sid]['source_url'],'https://example.org/filing')
        self.assertIn(sid,[x['id'] for x in ws.raw_view()['material_index']])
        self.assertNotIn(sid,[x['id'] for x in ws.raw_view()['task_sources']])

    def test_public_evidence_without_url_rejected(self):
        ws=self.workspace()
        with self.assertRaisesRegex(StateDyneError,'source URL'):
            ws.update('Sales grew.',source_kind='retrieved_public')

    def test_superseded_evidence_marks_prior_exploration_stale(self):
        ws=self.workspace(backend='fixture')
        backend=FixtureBackend(ws)
        Engine(ws,backend).advance()
        # Explicit job work with a new opportunity references the original premise.
        j=ws.get_job('extra-original-observation','deepen','work',ws.current_view(),'test')
        out=work();out['opportunities']=['Try a reverse model of the original fact.']
        write_result(ws.root,j,out,kind='fixture',worker_ref='fixture-extra',actual_model='fixture')
        ws.merge_work(j['id'])
        ws.update('Original statement is false.',supersedes='S1')
        self.assertTrue(all(o['state']=='stale' for o in ws.state['exploration_opportunities'].values()))

if __name__=='__main__':unittest.main()
