"""10.12 objective-scoped system coverage, immediate search and incremental evidence.

Every test below uses synthetic fixtures, not actual GPT reasoning or private user data.
"""
import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from test_runtime import TASK, FixtureBackend, work, draft_for
from sd_runtime.engine import Engine, instructions
from sd_runtime.store import Workspace
from sd_runtime.system_map import register_system_map, pending_coverage_opportunities
from sd_runtime.inquiry_frontier import discovery_inquiries
from sd_runtime.backends import write_result
from sd_runtime.common import StateDyneError


class SystemCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws=Workspace.create(Path(self.tmp.name)/'case',TASK,backend='fixture')

    def sample(self):
        job=self.ws.get_job('base-map','system_map','system_map',self.ws.raw_view(),instructions('system_map'))
        product=deepcopy(FixtureBackend(self.ws).execute(job)['output'])
        return product

    def register(self,product):
        job=self.ws.get_job('candidate-map','system_map','system_map',self.ws.raw_view(),instructions('system_map'))
        write_result(self.ws.root,job,product,kind='fixture',worker_ref='independent-system-mapper',actual_model='fixture')
        register_system_map(self.ws,job['id'])
        return job

    def gap(self,p,dim='upstream_inputs',route='materials',priority='important'):
        slot=next(x for x in p['coverage'] if x['dimension']==dim)
        slot.update(state='open',basis='unavailable',observed_or_hypothesized='',
                    missing='Which upstream request broker batches the jobs?',
                    why_material='The broker can fully reverse the apparent local-lock diagnosis.',
                    evidence=[],route=route,priority=priority)
        p['no_material_gap_reason']=''
        return p

    def test_open_upstream_interface_is_real_evidence_and_search_work(self):
        job=self.register(self.gap(self.sample()))
        id_=f'{job["id"]}:sys-upstream_inputs'
        q=self.ws.state['unknowns'][id_]
        self.assertEqual(q['route'],'materials')
        self.assertEqual(q['origin'],'system_map')
        self.assertIn(id_,[x['unknown_id'] for x in discovery_inquiries(self.ws)])
        self.assertTrue(pending_coverage_opportunities(self.ws))
        self.assertEqual(self.ws.state['system_map']['goal_basis'],'inferred')
        self.assertEqual(self.ws.state['system_map']['coverage'][3]['state'],'open')

    def test_goal_must_be_supported_if_declared_explicit(self):
        p=self.sample();p['goal_basis']='explicit';p['goal_evidence']=[]
        with self.assertRaisesRegex(StateDyneError,'explicitly claimed user goal'):
            self.register(p)

    def test_absent_dimension_cannot_be_passed_as_complete_map(self):
        p=self.sample();p['coverage'].pop()
        with self.assertRaisesRegex(StateDyneError,'Every core system dimension'):
            self.register(p)

    def test_duplicate_dimension_fails_independently_of_wording(self):
        p=self.sample();p['coverage'].append(deepcopy(p['coverage'][0]))
        with self.assertRaisesRegex(StateDyneError,'Every core system dimension'):
            self.register(p)

    def test_novel_domain_specific_dimension_is_allowed_without_hidden_fixed_cap(self):
        p=self.sample()
        slot=deepcopy(p['coverage'][-1])
        slot['dimension']='cross_scale_latency_boundary'
        slot.update(state='represented',basis='hypothesized',
                    observed_or_hypothesized='An external timing-domain boundary may change observed latency.',
                    why_material='Timing behavior can differ across coupled services.',
                    missing='',evidence=[])
        p['coverage'].append(slot)
        p['links'].append({'from_dimension':'upstream_inputs','to_dimension':'cross_scale_latency_boundary',
            'link':'The external source may be conditioned by an independent timing domain.',
            'kind':'hypothesized_causation','evidence':[]})
        # A linked dimension is not allowed to be classified as irrelevant.
        p['coverage'][3].update(state='open',basis='hypothesized',missing='Which external clock domain is active?',
            why_material='The clock can switch the outcome.',route='unavailable',priority='important')
        p['no_material_gap_reason']=''
        self.register(p)
        self.assertIn('cross_scale_latency_boundary',
            [x['dimension'] for x in self.ws.state['system_map']['coverage']])

    def test_relation_must_not_link_a_dim_called_irrelevant(self):
        p=self.sample();p['links'][0]['to_dimension']='environment'
        with self.assertRaisesRegex(StateDyneError,'irrelevant dimensions'):
            self.register(p)

    def test_unsourced_reported_fact_does_not_pass(self):
        p=self.sample();p['coverage'][0]['evidence']=[]
        with self.assertRaisesRegex(StateDyneError,'User-reported system facts'):
            self.register(p)

    def test_important_unknown_can_be_user_owned_not_automatically_public(self):
        job=self.register(self.gap(self.sample(),dim='history',route='user'))
        q=self.ws.state['unknowns'][f'{job["id"]}:sys-history']
        self.assertEqual(q['route'],'user')
        self.assertFalse(any('coverage-history' in v for v in pending_coverage_opportunities(self.ws)))

    def test_model_gap_gets_search_priority_before_any_finish(self):
        self.register(self.gap(self.sample()))
        self.ws.state.update(phase='schedule',blind_complete=True,entry_review={'output':{'verdict':'pass'}},
                             sweep_complete=True,portfolio_complete=True)
        class Trap(FixtureBackend):
            def execute(self,job):
                if job['role']=='reframe_informed':
                    self.captured=job
                    raise StateDyneError('NEW_UPSTREAM_MODEL_WAS_PRIORITIZED')
                return super().execute(job)
        provider=Trap(self.ws)
        with self.assertRaisesRegex(StateDyneError,'NEW_UPSTREAM_MODEL_WAS_PRIORITIZED'):
            Engine(self.ws,provider).advance()
        self.assertEqual(self.ws.state['phase'],'operate')
        self.assertTrue(provider.captured['inputs']['opportunity_ids'])
        self.assertFalse(any(x['role']=='schedule' for x in provider.requests))


    def test_boundary_review_must_actually_triage_open_system_gap(self):
        from sd_runtime.frontier import check_boundary
        self.register(self.gap(self.sample()))
        # A filled system map must not become decorative: a reviewer who
        # ignores its important upstream unknown cannot announce completion.
        answer={'new_foci':[], 'coverage':[], 'verdict':'pass',
                'system_coverage_dispositions':[]}
        with self.assertRaisesRegex(StateDyneError,'triage every material open system interface'):
            check_boundary(self.ws,answer)
        answer['system_coverage_dispositions']=[{
            'dimension':'upstream_inputs','resolution':'search',
            'rationale':'A real upstream broker might explain concurrency-specific delay.',
            'evidence_or_next_action':'Read the upstream queue scheduler configuration.'}]
        self.assertEqual(check_boundary(self.ws,answer),[])

    def test_system_review_cannot_claim_research_without_a_registered_unknown(self):
        from sd_runtime.frontier import check_boundary
        self.register(self.gap(self.sample()))
        self.ws.state['unknowns'].clear()
        answer={'new_foci':[], 'coverage':[], 'verdict':'pass',
                'system_coverage_dispositions':[{
                    'dimension':'upstream_inputs','resolution':'search',
                    'rationale':'An upstream broker changes which change intervention matters.',
                    'evidence_or_next_action':'Read the upstream broker specification.'}]}
        with self.assertRaisesRegex(StateDyneError,'actually registered unknown'):
            check_boundary(self.ws,answer)


class IncrementalChangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ws=Workspace.create(Path(self.tmp.name)/'case',TASK,backend='fixture')
        self.provider=FixtureBackend(self.ws)

    def run_first(self):
        result=Engine(self.ws,self.provider).advance()
        self.assertEqual(result['assurance'],'simulation_only')
        self.assertEqual(self.ws.state['phase'],'done')
        return result

    def test_additive_evidence_revisits_only_affected_system_and_models(self):
        old=self.run_first()
        previous_jobs={role:sum(j['role']==role for j in self.provider.requests)
                       for role in ('discovery','system_map','frame','reframe','contrast_probe')}
        self.ws.update('The independent upstream worker is active during only the slow intervals.')
        self.assertEqual(self.ws.state['phase'],'delta_assess')
        self.assertEqual(self.ws.state['generation'],1)
        fresh=Engine(self.ws,self.provider).advance()
        self.assertNotEqual(fresh['audit_job'],old['audit_job'])
        for role,n in previous_jobs.items():
            self.assertEqual(sum(j['role']==role for j in self.provider.requests),n)
        for role in ('delta_assess','delta_integrate','delta_challenge','system_reconcile'):
            self.assertEqual(sum(j['role']==role for j in self.provider.requests),1)
        self.assertEqual(self.ws.state['processed_delta_sources'],['S2'])
        self.assertEqual(len(self.ws.state['system_map_history']),2)
        Engine(self.ws,self.provider).verify_release()

    def test_rebuild_if_new_goal_or_system_boundary_changed(self):
        self.run_first()
        self.ws.update('New objective: optimize cost rather than latency.')
        class GlobalFixture(FixtureBackend):
            def execute(self,job):
                if job['role']!='delta_assess':return super().execute(job)
                output={'impact':'rebuild','reason':'The target is now cost, rather than response latency.',
                    'affected_claim_ids':[],'affected_unknown_ids':[],
                    'goal_or_boundary_changed':True,'newly_relevant_difference':'Cost optimisation needs another system model.',
                    'new_foci':[], 'question_results':[{'group_id':g['group_id'],
                        'outcome':'unknown', 'evidence_change':'No direct evidence for this previous test group was supplied.',
                        'revised_judgment':'The previous two alternatives remain unresolved under the new objective.'}
                        for g in (job['inputs'].get('recent_turns') or [{}])[-1].get('draft',{}).get('output',{}).get('question_groups',[])]}
                return write_result(self.ws.root,job,output,kind='fixture',worker_ref='fresh-goal-review',actual_model='fixture')
        provider=GlobalFixture(self.ws)
        outcome=Engine(self.ws,provider).advance()
        self.assertEqual(outcome['assurance'],'simulation_only')
        self.assertEqual(self.ws.state['generation'],2)
        self.assertEqual(sum(j['role']=='discovery' for j in provider.requests),1)
        self.assertEqual(len(self.ws.state['system_map_history']),2)

    def test_an_existing_source_correction_requires_full_raw_restart(self):
        self.run_first()
        self.ws.update('Actually the system is slow even for a single process.',supersedes='S1')
        self.assertEqual(self.ws.state['phase'],'discover')
        self.assertEqual(self.ws.state['generation'],2)

    def test_proposed_delta_focus_must_really_quote_new_source(self):
        self.run_first()
        self.ws.update('An external dependency seems delayed.')
        input_=self.ws.current_view()
        input_['new_sources']=[self.ws.state['sources']['S2']]
        job=self.ws.get_job('delta-trap','delta_assess','delta_assessment',input_,instructions('delta_assess'))
        result={'impact':'local','reason':'The new symptom suggests another path.',
            'affected_claim_ids':[],'affected_unknown_ids':[],
            'goal_or_boundary_changed':False,'newly_relevant_difference':'A new upstream signal appears.',
            'new_foci':[{'local_id':'F2', 'observation':'External latency is observed.',
                'unexplained_difference':'A second symptom exists.','why_material':'Changes explanation.',
                'priority':'critical','evidence':[{'source_id':'S1','quote':TASK}]}],
            'question_results':[{'group_id':g['group_id'],'outcome':'unknown',
                 'evidence_change':'The new source does not resolve the earlier shared resource discriminator.',
                 'revised_judgment':'Both explanations remain conditional pending independent evidence.'}
                 for g in (input_.get('recent_turns') or [{}])[-1].get('draft',{}).get('output',{}).get('question_groups',[])]}
        write_result(self.ws.root,job,result,kind='fixture',worker_ref='delta-worker',actual_model='fixture')
        with self.assertRaisesRegex(StateDyneError,'newly supplied source'):
            self.ws.invalidate_delta_dependencies(result,job['id'])

    def test_requesting_action_must_show_goal_and_then_points_before_actions(self):
        self.ws.state['scope']='actions'
        provider=FixtureBackend(self.ws)
        Engine(self.ws,provider).advance()
        self.assertIn('本轮目标：',self.ws.state['draft']['output']['answer'])
        draft_job=self.ws.get_job('no-goal-compose','compose','draft',self.ws.current_view(),instructions('compose'))
        d=draft_for(draft_job);d['goal_line']=''
        write_result(self.ws.root,draft_job,d,kind='fixture',worker_ref='writer-without-goal',actual_model='fixture')
        with self.assertRaisesRegex(StateDyneError,'visibly state the goal'):
            self.ws.set_draft(draft_job['id'])


if __name__=='__main__':unittest.main()
