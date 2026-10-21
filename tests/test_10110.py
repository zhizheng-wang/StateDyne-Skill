"""10.11 deterministic gates. Not a real-language-model capability demonstration."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sd_runtime.common import StateDyneError
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.probe_portfolio import register_portfolio, pending_model_expansion
from sd_runtime.inquiry_frontier import discovery_inquiries
from sd_runtime.backends import write_result
from test_runtime import TASK, claim, work, draft_for
from fixture_helpers_10190 import search_for

class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=Workspace.create(Path(self.tmp.name) / 'run', TASK, backend='fixture')
    def tearDown(self): self.tmp.cleanup()

    def have_candidate(self):
        job=self.ws.get_job('source','reframe','work',self.ws.raw_view(),instructions('reframe'))
        write_result(self.ws.root,job,work(),kind='fixture',worker_ref='probe-source',actual_model='fixture')
        self.ws.merge_work(job['id'])
        return f'{job["id"]}:M1'

    def probe(self, refs=None, *, advance=True, route='user', novel='One process runs late even if local contention is absent.'):
        return dict(local_id='P1',claim_ids=refs or [],model_gap='' if refs else 'A distant queue or external gate not present in the local lock model.',
                    question='Does the upstream service exhibit independent waiting spikes?',
                    unreported_outcome=novel,
                    rival_outcome='The upstream service does not show independent waits.',
                    why_distinguishes='A nonlocal wait differs from the original shared lock account.',
                    recognition_prompt='Apart from the original example, do you recall a delay when local resource use was low? No or unsure is fine.',
                    counter_cue='If the slowdown always tracks lock occupancy, the external queue account is less likely.',
                    route=route,importance='important',advance=advance,
                    reason='An independently observable event can discriminate rival mechanisms.')

    def register(self,probes,reason=''):
        job=self.ws.get_job('probe','probe_portfolio','probe_portfolio',self.ws.current_view(),instructions('probe_portfolio'))
        out=dict(covered_representation='Compared a local shared lock with an external serialization queue.',exploration_attempts=search_for(probes),probes=probes,null_search_reason=reason)
        write_result(self.ws.root,job,out,kind='fixture',worker_ref='portfolio-worker',actual_model='fixture')
        register_portfolio(self.ws,job['id'])
        return job

    def test_candidate_linked_probe_enters_actual_unknowns(self):
        cid=self.have_candidate()
        job=self.register([self.probe([cid])])
        uq=self.ws.state['unknowns'][f'{job["id"]}:Q1']
        self.assertEqual(uq['related_claims'],[cid])
        self.assertEqual(uq['route'],'user')
        self.assertEqual(uq['priority'],'important')
        self.assertEqual(len(discovery_inquiries(self.ws)),1)

    def test_unmodelled_relationship_enters_actual_new_search(self):
        job=self.register([self.probe()])
        ids=pending_model_expansion(self.ws)
        self.assertEqual(ids,[f'{job["id"]}:P1'])
        self.assertEqual(self.ws.state['exploration_opportunities'][ids[0]]['state'],'open')
        self.assertEqual(self.ws.state['unknowns'],{})

    def test_rejected_candidate_does_not_create_user_question(self):
        self.register([self.probe(advance=False)])
        self.assertFalse(self.ws.state['unknowns'])
        self.assertFalse(pending_model_expansion(self.ws))

    def test_zero_novelty_valid_only_with_specific_negative_search(self):
        self.register([],reason='Examined an external-queue alternative and a clock-skew account; neither gives a distinct prediction under supplied facts.')
        self.assertEqual(self.ws.state['probe_portfolio']['probes'],[])

    def test_empty_claim_without_model_gap_rejected(self):
        bad=self.probe();bad['model_gap']=''
        with self.assertRaisesRegex(StateDyneError,'new relation'):
            self.register([bad])
        self.assertIsNone(self.ws.state['probe_portfolio'])

    def test_existing_model_with_unneeded_gap_rejected(self):
        cid=self.have_candidate()
        bad=self.probe([cid]);bad['model_gap']='wrong field'
        with self.assertRaisesRegex(StateDyneError,'empty model_gap'):
            self.register([bad])

    def test_duplicate_rival_prediction_rejected(self):
        bad=self.probe();bad['rival_outcome']=bad['unreported_outcome']
        with self.assertRaisesRegex(StateDyneError,'identical'):
            self.register([bad])

    def test_repeated_known_outcome_does_not_count_new(self):
        bad=self.probe(novel=TASK)
        with self.assertRaisesRegex(StateDyneError,'verbatim reported'):
            self.register([bad])

    def test_unavailable_information_not_forced_to_user(self):
        cid=self.have_candidate()
        self.register([self.probe([cid],route='unavailable')])
        self.assertEqual(next(iter(self.ws.state['unknowns'].values()))['route'],'unavailable')

    def test_public_evidence_is_not_reframed_as_user_question(self):
        cid=self.have_candidate()
        self.register([self.probe([cid],route='public_source')])
        self.assertEqual(next(iter(self.ws.state['unknowns'].values()))['route'],'public_source')

    def test_high_value_unmodelled_relation_blocks_early_finish(self):
        job=self.register([self.probe()])
        self.ws.state.update(phase='schedule',sweep_complete=True,portfolio_complete=True,
                             blind_complete=True,entry_review={'output':{'verdict':'pass'}})
        class Intercept:
            def execute(self,job):
                if job['role']=='reframe_informed':
                    self.reframe=job
                    raise StateDyneError('UNMODELLED_RELATION_WAS_ACTUALLY_SCHEDULED')
                from test_runtime import FixtureBackend
                return FixtureBackend(self_outer.ws).execute(job)
        self_outer=self
        provider=Intercept()
        with self.assertRaisesRegex(StateDyneError,'UNMODELLED_RELATION_WAS_ACTUALLY_SCHEDULED'):
            Engine(self.ws,provider).advance()
        self.assertIn(f'{job["id"]}:P1',provider.reframe['inputs']['opportunity_ids'])

    def test_model_expansion_is_not_infinite(self):
        job=self.register([self.probe()]); oid=f'{job["id"]}:P1'
        self.ws.mark_opportunities_attempted({'opportunity_ids':[oid],'operator':'reframe'})
        self.assertFalse(pending_model_expansion(self.ws))

    def test_repeated_question_is_not_registered_twice(self):
        cid=self.have_candidate()
        base_job=self.ws.get_job('unknown-source','reframe','work',self.ws.raw_view(),instructions('reframe'))
        from test_runtime import unknown
        uq=unknown('Q1');uq['question']=self.probe([cid])['question'];uq['related_claims']=[cid]
        write_result(self.ws.root,base_job,work(claims=[],unknowns=[uq]),kind='fixture',worker_ref='base-unknown',actual_model='fixture')
        self.ws.merge_work(base_job['id'])
        self.register([self.probe([cid])])
        self.assertEqual(len(self.ws.state['unknowns']),1)

    def test_non_selected_model_cannot_silently_downgrade_priority_probe(self):
        cid=self.have_candidate()
        self.register([self.probe([cid])])
        job=self.ws.get_job('compose','compose','draft',self.ws.current_view(),instructions('compose'))
        d=draft_for(job)
        inquiry=d['information_dispositions'][0]
        inquiry['treatment']='defer';inquiry['visible_question']='';inquiry['decision_effect']='refines_only'
        d['question_groups']=[]
        d['answer']=d['answer'].replace(self.probe([cid])['question'],'')
        write_result(self.ws.root,job,d,kind='fixture',worker_ref='writer',actual_model='fixture')
        with self.assertRaisesRegex(StateDyneError,'cannot be silently downgraded'):
            self.ws.set_draft(job['id'])

    def test_after_new_evidence_portfolio_is_not_recycled(self):
        self.register([self.probe()])
        self.ws.update('A genuinely new user observation arrived.')
        self.assertIsNone(self.ws.state['probe_portfolio'])
        self.assertFalse(self.ws.state['portfolio_complete'])

if __name__ == '__main__': unittest.main()
