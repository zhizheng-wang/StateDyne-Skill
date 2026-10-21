"""10.16 selectable model expansion. Synthetic runtime tests, not model evaluation."""
from __future__ import annotations
from pathlib import Path
from copy import deepcopy
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))

from sd_runtime.common import StateDyneError, save_json
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.backends import NativeBackend, write_result
from sd_runtime.cli import parser
from test_runtime import TASK, claim, unknown


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace.create(Path(self.tmp.name)/'run', TASK, scope='auto', backend='native')

    def make_done(self):
        """Synthetic delivered state for transition testing; no model is pretended to have run."""
        self.ws.state['phase']='done'
        name='answer.md'
        (self.ws.root/name).write_text('A shared lock is only a tentative explanation.\n',encoding='utf8')
        save_json(self.ws.root/'release.json', {'answer_file':name,'status':'provisional', 'assurance':'synthetic-fixture'})
        self.ws.save('synthetic_completed_stage_for_transition_test')

    def pending_expand(self, focus=''):
        self.make_done()
        self.ws.expand_search(focus)
        return Engine(self.ws,NativeBackend(self.ws.root,self.ws.state['sources'],self.ws.state['config'])).advance()

    def test_expansion_rejects_unfinished_work_without_side_effect(self):
        before=deepcopy(self.ws.state)
        with self.assertRaisesRegex(StateDyneError,'completed'):
            self.ws.expand_search()
        self.assertEqual(before,self.ws.state)

    def test_user_must_explicitly_request_expansion(self):
        self.ws.state['phase']='expand_frontier'
        self.ws.state['delivery_cycle']=1
        with self.assertRaisesRegex(StateDyneError,'explicit'):
            Engine(self.ws,NativeBackend(self.ws.root,self.ws.state['sources'],self.ws.state['config'])).advance()

    def test_expansion_requires_a_real_previous_release(self):
        self.ws.state['phase']='done'
        with self.assertRaises(FileNotFoundError):
            self.ws.expand_search()

    def test_focus_length_checked_before_mutation(self):
        self.make_done()
        previous=deepcopy(self.ws.state)
        with self.assertRaisesRegex(StateDyneError,'<=2000'):
            self.ws.expand_search('X'*2001)
        self.assertEqual(previous,self.ws.state)

    def test_ambient_default_discovery_unchanged(self):
        engine=Engine(self.ws,NativeBackend(self.ws.root,self.ws.state['sources'],self.ws.state['config']))
        pending=engine.advance()
        self.assertEqual(len(pending['jobs']),10)
        roles={self.ws.job_request(jid)['role'] for jid in pending['jobs']}
        self.assertNotIn('open_search',roles)

    def test_expansion_spawns_parallel_incumbent_and_blind_jobs_on_existing_material(self):
        result=self.pending_expand('Check whether different successful teams use the same mechanism')
        self.assertEqual(result['status'],'waiting_for_real_workers')
        self.assertEqual(len(result['jobs']),2)
        reqs={self.ws.job_request(j)['role']:self.ws.job_request(j) for j in result['jobs']}
        self.assertEqual(set(reqs),{'open_search','breakthrough_scout'})
        req=reqs['open_search']
        self.assertEqual(req['schema_name'],'work')
        self.assertEqual(req['inputs']['expansion_focus'], 'Check whether different successful teams use the same mechanism')
        self.assertEqual(req['inputs']['recent_turns'][0]['answer'], 'A shared lock is only a tentative explanation.\n')
        self.assertNotIn('claims',reqs['breakthrough_scout']['inputs'])
        self.assertEqual(self.ws.state['scope'],'analysis')
        self.assertEqual(len(self.ws.state['sources']),1)
        self.assertTrue(self.ws.state['turn_history'])

    def test_previous_model_tournament_not_erased(self):
        self.make_done()
        old={'job_id':'older-portfolio','probes':[{'id':'deferred-synthetic-probe','state':'deferred'}],
             'covered_representation':'Local vs external queues','null_search_reason':''}
        self.ws.state['probe_portfolio']=deepcopy(old)
        self.ws.expand_search('Find a genuinely different causal family')
        self.assertEqual(self.ws.state['portfolio_history'][-1],old)
        self.assertEqual(self.ws.current_view()['prior_probe_portfolios'][-1],old)
        self.assertIsNone(self.ws.state['probe_portfolio'])
        self.assertEqual(len(self.ws.state['sources']),1)

    def test_expansion_user_request_does_not_jump_to_intervention(self):
        self.pending_expand('Investigate unknown drivers behind apparent success')
        self.assertEqual(self.ws.state['scope'],'analysis')
        self.assertEqual(self.ws.state['delivery_scope'],'analysis')
        self.assertEqual(self.ws.state['phase'],'expand_frontier')

    def test_real_worker_required_before_any_expansion_claim(self):
        self.pending_expand()
        self.assertEqual(self.ws.state['expansion_runs'],[])
        self.assertEqual(self.ws.state['claims'],{})
        self.assertEqual(self.ws.state['phase'],'expand_frontier')

    def send(self, product):
        pending=self.pending_expand('Look for an overlooked environmental selection effect')
        jid=pending['jobs'][0]
        job=self.ws.job_request(jid)
        write_result(self.ws.root,job,product,kind='fixture',worker_ref='synthetic-open-model-worker',actual_model='fixture')
        blind=self.ws.job_request(pending['jobs'][1])
        null={'summary':'Test fixture: independent raw-only expansion found no additional grounded relation.',
              'claims':[], 'unknowns':[], 'opportunities':[],
              'no_increment_reason':('Synthetic independent negative control compared upstream queue, nested routing, '
                  'and reverse temporal explanations; none provided a non-redundant prediction or evidence route.') }
        write_result(self.ws.root,blind,null,kind='fixture',worker_ref='synthetic-raw-blind-worker',actual_model='fixture')
        return Engine(self.ws,NativeBackend(self.ws.root,self.ws.state['sources'],self.ws.state['config']))

    def test_null_expansion_needs_meaningful_search_account(self):
        eng=self.send({'summary':'No new facts were discovered.','claims':[], 'unknowns':[],
                       'opportunities':[], 'no_increment_reason':'No new idea.'})
        with self.assertRaisesRegex(StateDyneError,'genuine null search'):
            eng.advance()
        self.assertEqual(self.ws.state.get('expansion_runs',[]),[])

    def test_new_mechanism_requires_a_route_or_research_opportunity(self):
        eng=self.send({'summary':'External admissions could select requests.','claims':[claim()],
                       'unknowns':[], 'opportunities':[], 'no_increment_reason':''})
        with self.assertRaisesRegex(StateDyneError,'information or a concrete'):
            eng.advance()

    def test_valid_null_result_reaches_independent_tournament(self):
        eng=self.send({'summary':'A targeted comparison of independent and shared workloads found no additional testable difference.',
                       'claims':[],'unknowns':[],'opportunities':[],
                       'no_increment_reason':'Compared worker identity, load distribution, independent request order, and outside admission. No new falsifiable outcome.'})
        pending=eng.advance()
        self.assertEqual(pending['status'],'waiting_for_real_workers')
        self.assertEqual(self.ws.state['phase'],'probe_portfolio')
        self.assertEqual(self.ws.state['expansion_runs'][0]['candidate_count'],0)
        self.assertEqual(self.ws.job_request(pending['jobs'][0])['role'],'probe_portfolio')

    def test_new_candidate_becomes_registered_unknown_then_portfolio(self):
        question=unknown()
        question['related_claims']=['M1']
        eng=self.send({'summary':'Candidate waits for a lock independently of peak utilization.',
                       'claims':[claim()], 'unknowns':[question], 'opportunities':[], 'no_increment_reason':''})
        pending=eng.advance()
        self.assertEqual(self.ws.state['phase'],'probe_portfolio')
        self.assertEqual(len(self.ws.active_claims()),1)
        q=list(self.ws.state['unknowns'].values())[0]
        self.assertEqual(q['related_claims'], list(self.ws.active_claims()))
        self.assertEqual(self.ws.state['expansion_runs'][0]['candidate_count'],1)
        self.assertEqual(self.ws.job_request(pending['jobs'][0])['role'],'probe_portfolio')

    def test_cli_exposes_requested_optional_expand(self):
        args=parser().parse_args(['expand','--workdir',str(self.ws.root),'--focus','Look for different cohorts'])
        self.assertEqual(args.command,'expand')
        self.assertEqual(args.focus,'Look for different cohorts')

    def test_portable_contract_mentions_both_routes_and_noninduction(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'SKILL.md').read_text(encoding='utf8')
        method=(root/'references/open-search.md').read_text(encoding='utf8')
        operator=(root/'references/operators/open_search.md').read_text(encoding='utf8')
        self.assertIn('继续扩大搜索',text)
        self.assertIn('不强迫用户',text)
        self.assertIn('组内细分',method)
        self.assertIn('不得因此自动跳到干预点',text)
        self.assertIn('不能在用户只要求继续分析时擅自给干预点',operator)
        self.assertIn('如果没有真正增量',method)

class ExpansionFullCycle(unittest.TestCase):
    """Fixture-only complete protocol round trip, never a claim of LLM discovery."""
    def test_previously_delivered_fixture_can_expand_and_release_new_audit(self):
        from test_runtime import FixtureBackend, work
        class ExpansionFixture(FixtureBackend):
            def execute(self, job):
                if job['role']=='open_search':
                    self.requests.append(deepcopy(job))
                    product=work(claims=[claim('New')], unknowns=[unknown('NewQ')])
                    product['summary']='Synthetic rival model differs in outside queue dependency.'
                    return write_result(self.ws.root, job, product,
                                        kind='fixture',worker_ref=f'fixture-{job["id"]}',
                                        actual_model='scripted-fixture-not-a-model')
                return super().execute(job)
        with tempfile.TemporaryDirectory() as temp:
            ws=Workspace.create(Path(temp)/'run', TASK, backend='fixture',scope='analysis')
            backend=ExpansionFixture(ws)
            initial=Engine(ws,backend).advance()
            self.assertEqual(initial['assurance'],'simulation_only')
            old_claims=set(ws.active_claims())
            old_source_hashes={sid:s['sha256'] for sid,s in ws.state['sources'].items()}
            old_jobs=len(backend.requests)
            ws.expand_search('Challenge the common mechanism across successful cases')
            expanded=Engine(ws,backend).advance()
            self.assertEqual(expanded['assurance'],'simulation_only')
            self.assertEqual(ws.state['phase'],'done')
            self.assertEqual(len(ws.state['expansion_runs']),1)
            self.assertEqual(ws.state['expansion_runs'][0]['candidate_count'],1)
            self.assertTrue(old_claims.issubset(ws.active_claims()))
            self.assertEqual(old_source_hashes,{sid:s['sha256'] for sid,s in ws.state['sources'].items()})
            newroles=[x['role'] for x in backend.requests[old_jobs:]]
            self.assertEqual(newroles.count('open_search'),1)
            self.assertEqual(newroles.count('probe_portfolio'),1)
            self.assertEqual(newroles.count('compose'),1)
            self.assertEqual(newroles.count('audit'),1)
            self.assertFalse(any(x in newroles for x in ('frame','blind_challenge','system_map')))
            self.assertEqual(ws.state['scope'],'analysis')
            Engine(ws,backend).verify_release()


if __name__=='__main__':
    unittest.main()
