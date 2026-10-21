"""Double-sided change-search scheduling: executable checks, not efficacy proofs."""
import tempfile
import unittest
from pathlib import Path
from test_runtime import TASK, FixtureBackend
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine
from sd_runtime.common import digest

class InterventionSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=Workspace.create(Path(self.tmp.name)/'run', TASK, backend='fixture',scope='points')
    def tearDown(self):self.tmp.cleanup()
    def test_forward_backward_receipts_are_real_separate_jobs(self):
        provider=FixtureBackend(self.ws)
        release=Engine(self.ws,provider).advance()
        jobs={j['role']: j for j in provider.requests}
        self.assertIn('change_forward',jobs)
        self.assertIn('change_backward',jobs)
        self.assertEqual(digest(jobs['change_forward']['inputs']),digest(jobs['change_backward']['inputs']))
        self.assertNotEqual(jobs['change_forward']['id'], jobs['change_backward']['id'])
        self.assertTrue(self.ws.state['intervention_frontier_done'])
        self.assertEqual(release['assurance'],'simulation_only')
        kinds=[x['kind'] for x in self.ws.active_claims().values()]
        self.assertIn('point',kinds)

    def test_unchanged_next_stage_reuses_prior_discovery_not_duplicate_initial_scouts(self):
        provider=FixtureBackend(self.ws)
        Engine(self.ws,provider).advance()
        before=len([r for r in provider.requests if r['role']=='discovery'])
        self.ws.continue_stage('actions')
        Engine(self.ws,provider).advance()
        after=len([r for r in provider.requests if r['role']=='discovery'])
        self.assertEqual((before,after),(1,1))
        # A fully reviewed point frontier and its backstage feasibility work
        # must be reused, not completely rerun during actions.
        self.assertEqual(len([r for r in provider.requests if r['role']=='change_forward']),1)
        self.assertEqual(len([r for r in provider.requests if r['role']=='change_backward']),1)
        self.assertEqual(len([r for r in provider.requests if r['role']=='change_portfolio']),1)
        self.assertEqual(len([r for r in provider.requests if r['role']=='change_action_probe']),1)
        self.assertTrue(self.ws.state['preflight_reused_from_prior_stage'])

    def test_analysis_scope_does_not_run_unrequested_intervention_search(self):
        self.tmp.cleanup()
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=Workspace.create(Path(self.tmp.name)/'run', TASK, backend='fixture',scope='analysis')
        provider=FixtureBackend(self.ws)
        Engine(self.ws,provider).advance()
        self.assertFalse(any(r['role'] in ('change_forward','change_backward') for r in provider.requests))

    def test_intervention_does_not_require_fixed_number_of_points(self):
        provider=FixtureBackend(self.ws)
        Engine(self.ws,provider).advance()
        self.assertTrue(any(c['kind']=='point' for c in self.ws.active_claims().values()))
        self.assertEqual(self.ws.state['config']['max_question_characters'],None)

if __name__ == '__main__': unittest.main()
