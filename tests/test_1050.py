"""10.5.0 software-level tests. Mocked web is NOT a live web/model test."""
from __future__ import annotations
import json
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sd_runtime.store import Workspace
from sd_runtime.engine import Engine, instructions
from sd_runtime.backends import OpenAIBackend, write_result
from sd_runtime.common import StateDyneError
from test_runtime import FixtureBackend, work, TASK


class SearchArchitectureTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def workspace(self, **kwargs):
        return Workspace.create(self.root / 'case', TASK, **kwargs)

    def test_second_pass_scouts_are_genuinely_concurrent(self):
        ws = self.workspace(backend='fixture')
        barrier = threading.Barrier(2)
        class Both(FixtureBackend):
            def execute(self, job):
                if job['role'] in ('frontier_scout','evidence_scout'):
                    barrier.wait(timeout=4)
                return super().execute(job)
        self.assertEqual(Engine(ws, Both(ws)).advance()['assurance'], 'simulation_only')

    def test_new_user_evidence_reopens_both_research_frontiers(self):
        ws = self.workspace(backend='fixture')
        b = FixtureBackend(ws)
        Engine(ws, b).advance()
        ws.update('New observable change: slowdown also occurs without overlap.', supersedes='S1')
        self.assertFalse(ws.state['sweep_complete'])
        Engine(ws, b).advance()
        self.assertEqual(len([r for r in b.requests if r['role']=='frontier_scout']), 2)
        self.assertEqual(len([r for r in b.requests if r['role']=='evidence_scout']), 2)

    def test_two_gap_and_evidence_scouts_observe_identical_pre_sweep_ledger(self):
        ws = self.workspace(backend='fixture')
        engine_backend = FixtureBackend(ws)
        result = Engine(ws, engine_backend).advance()
        self.assertEqual(result['assurance'], 'simulation_only')
        roles = [x['role'] for x in engine_backend.requests]
        self.assertLess(roles.index('frontier_scout'), roles.index('entry_review'))
        self.assertLess(roles.index('evidence_scout'), roles.index('schedule'))
        a = next(x for x in engine_backend.requests if x['role'] == 'frontier_scout')
        b = next(x for x in engine_backend.requests if x['role'] == 'evidence_scout')
        self.assertEqual(a['inputs'], b['inputs'])
        self.assertNotIn('frontier-scout', json.dumps(b['inputs']))
        self.assertTrue(ws.state['sweep_complete'])
        after = next(x for x in engine_backend.requests if x['role'] == 'entry_review')
        self.assertTrue(any(x['origin_job'] == a['id'] for x in after['inputs']['claims']))
        self.assertTrue(any(x['origin_job'] == b['id'] for x in after['inputs']['claims']))

    def test_duplicate_opportunity_is_shared_not_repeated(self):
        ws = self.workspace()
        a = ws.get_job('scout-a', 'frontier_scout', 'work', ws.raw_view(), instructions('frontier_scout'))
        b = ws.get_job('scout-b', 'evidence_scout', 'work', ws.raw_view(), instructions('evidence_scout'))
        proposal = 'Find counterexamples in another market to reverse the conclusion.'
        out1 = work(); out1['opportunities'] = [proposal]
        out2 = work(); out2['opportunities'] = ['Find counterexamples in another market to reverse the conclusion!']
        for job, data in ((a, out1), (b, out2)):
            write_result(ws.root, job, data, kind='fixture', worker_ref='fixture-'+job['id'], actual_model='fixture')
            ws.merge_work(job['id'])
        self.assertEqual(len(ws.state['exploration_opportunities']), 1)
        record = next(iter(ws.state['exploration_opportunities'].values()))
        self.assertEqual(record['proposed_by'], [a['id'], b['id']])
        self.assertTrue(all(x['opportunity_ids'] for x in ws.state['work_results']))

    def test_web_search_is_opt_in_and_research_citations_are_only_leads(self):
        collected = []
        output = work()
        def fake(payload, key, timeout):
            collected.append(payload)
            return {'id': 'resp-fixture-1', 'model': 'fixture-model', 'status': 'completed',
                    'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30},
                    'output': [
                        {'type': 'web_search_call', 'id': 'ws-1', 'status': 'completed',
                         'action': {'type': 'search', 'query': 'company revenue filing'},
                         'results': [{'url': 'https://example.org/filing', 'title': 'Official filing'}]},
                        {'type': 'message', 'role': 'assistant', 'content': [
                            {'type': 'output_text', 'text': json.dumps(output),
                             'annotations': [{'type': 'url_citation', 'url': 'https://example.org/filing',
                                              'title': 'Official filing'}]}
                        ]}
                    ]}
        ws = self.workspace(backend='openai', model='fixture-model',
                            config={'allow_remote': True, 'web_search_enabled': True})
        backend = OpenAIBackend(ws.root, ws.state['sources'], ws.state['config'], transport=fake)
        job = ws.get_job('discover-1', 'discovery', 'work', ws.raw_view(), instructions('discovery'))
        result = backend.execute(job)
        self.assertEqual(result['backend_kind'], 'fixture')
        self.assertTrue(any(t.get('type') == 'web_search' for t in collected[0]['tools']))
        self.assertIn('web_search_call.results', collected[0]['include'])
        self.assertEqual(len(result['web_research']), 1)
        ws.merge_work(job['id'])
        leads = ws.current_view()['web_research_leads']
        self.assertEqual(leads[0]['url'], 'https://example.org/filing')
        self.assertFalse(leads[0]['verified_source'])
        with self.assertRaisesRegex(StateDyneError, 'Source/quote mismatch'):
            ws.check_evidence([{'source_id': 'https://example.org/filing', 'quote':'Official filing'}])

    def test_api_web_search_disabled_without_opt_in(self):
        payloads = []
        def fake(payload, key, timeout):
            payloads.append(payload)
            return {'id': 'r', 'model': 'fixture-model', 'status': 'completed',
                    'output': [{'type': 'message', 'role': 'assistant',
                                'content': [{'type': 'output_text', 'text': json.dumps(work())}]}]}
        ws = self.workspace(backend='openai', model='fixture-model', config={'allow_remote':True})
        backend = OpenAIBackend(ws.root, ws.state['sources'], ws.state['config'], transport=fake)
        job = ws.get_job('discover-1', 'discovery', 'work', ws.raw_view(), instructions('discovery'))
        backend.execute(job)
        self.assertFalse(any(t.get('type')=='web_search' for t in payloads[0]['tools']))
        self.assertNotIn('web_search_call.results', payloads[0]['include'])

    def test_stage_continuation_does_not_repeat_scouts(self):
        ws = self.workspace(backend='fixture')
        b = FixtureBackend(ws)
        Engine(ws, b).advance()
        before = len([x for x in b.requests if x['role'] in ('frontier_scout','evidence_scout')])
        ws.continue_stage('points')
        Engine(ws, b).advance()
        self.assertEqual(before, 2)
        self.assertEqual(len([x for x in b.requests if x['role'] in ('frontier_scout','evidence_scout')]), 2)


if __name__ == '__main__':
    unittest.main()
