"""Additional deterministic regression tests; no real model is called."""
from copy import deepcopy
import json
from test_runtime import (Base, FixtureBackend, TASK, claim, work, unknown,
                         StateDyneError, Workspace, Engine, NativeBackend,
                         OpenAIBackend, write_result, read_json, save_json)


class RecoveryAndIsolationTests(Base):
    def test_cached_job_integrity_checked_before_execution(self):
        ws = self.workspace()
        engine = Engine(ws, NativeBackend(ws.root, ws.state['sources'], ws.state['config']))
        engine.advance()
        path = ws.root/'jobs'/'J0001'/'request.json'
        raw = read_json(path); raw['inputs']['leaked_answer'] = 'tampered'; save_json(path, raw)
        with self.assertRaises(StateDyneError): engine.advance()
        self.assertIn('integrity mismatch', ws.state['last_error'])

    def test_rejected_first_attempt_is_retained_and_fresh_job_used(self):
        ws = self.workspace(backend='fixture')
        engine = Engine(ws, NativeBackend(ws.root, ws.state['sources'], ws.state['config']))
        engine.advance()
        old = next(ws.job_request(jid) for jid in ws.state['jobs'] if ws.job_request(jid)['role']=='discovery')
        broken = work(); broken['claims'][0]['mechanism']['transformation'] = ''
        write_result(ws.root, old, broken, kind='fixture', worker_ref='fixture-first', actual_model='fixture')
        provider = FixtureBackend(ws)
        with self.assertRaises(StateDyneError): Engine(ws, provider).advance()
        original = (ws.root/'jobs'/old['id']/'result.json').read_bytes()
        replacement = ws.retry_job(old['id'], 'The transformation field was empty; produce a nonempty observable relation.')
        self.assertNotEqual(replacement['id'], old['id'])
        self.assertEqual(replacement['inputs'], old['inputs'])
        result = Engine(ws, provider).advance()
        self.assertEqual(result['assurance'], 'simulation_only')
        self.assertEqual(ws.state['jobs'][old['id']]['status'], 'rejected')
        self.assertEqual((ws.root/'jobs'/old['id']/'result.json').read_bytes(), original)
        self.assertTrue(all(c['origin_job'] != 'J0001' for c in ws.active_claims().values()))
        Engine(ws, provider).verify_release()

    def test_retry_cannot_overwrite_accepted_work(self):
        ws = self.workspace(); job = self.make_job(ws)
        self.receive(ws, job, work()); ws.merge_work(job['id'])
        with self.assertRaises(StateDyneError): ws.retry_job(job['id'], 'Rewrite an accepted result')

    def test_retry_cannot_run_obsolete_generation(self):
        ws = self.workspace(); job = self.make_job(ws)
        ws.update('New evidence changes the task.')
        with self.assertRaises(StateDyneError): ws.retry_job(job['id'], 'Retry older raw inputs')

    def test_blind_challenge_informs_first_scheduler_even_when_budget_exhausted(self):
        ws = self.workspace(backend='fixture'); provider = FixtureBackend(ws)
        Engine(ws, provider).advance()
        schedules = [r for r in provider.requests if r['role']=='schedule']
        self.assertEqual(len(schedules), 1)
        blind = next(r for r in provider.requests if r['role']=='blind_challenge')
        self.assertTrue(any(c['origin_job']==blind['id'] for c in schedules[0]['inputs']['claims']))
        roles = [r['role'] for r in provider.requests]
        self.assertLess(roles.index('blind_challenge'), roles.index('schedule'))
        # Even a zero-operation run sees and disposes of blind findings in the draft.
        zero_ws = Workspace.create(self.root / 'zero', TASK, backend='fixture', config={'max_operations':0})
        zero_provider=FixtureBackend(zero_ws)
        Engine(zero_ws, zero_provider).advance()
        blind_id=next(r['id'] for r in zero_provider.requests if r['role']=='blind_challenge')
        self.assertTrue(any(c['origin_job']==blind_id for c in zero_ws.active_claims().values()))
        draft=zero_ws.state['draft']['output']
        self.assertTrue(any(d['claim_id'].startswith(blind_id+':') for d in draft['claim_dispositions']))

    def test_corrected_feedback_completes_new_generation_not_old_audit(self):
        ws = self.workspace(backend='fixture'); provider = FixtureBackend(ws)
        first = Engine(ws, provider).advance()
        first_audit = first['audit_job']
        old_ids = set(ws.active_claims())
        ws.update('Corrected task: the delay occurs even with one process; investigate the other causes.', supersedes='S1')
        self.assertFalse((ws.root/'simulation-answer.md').exists())
        second = Engine(ws, provider).advance()
        self.assertNotEqual(second['audit_job'], first_audit)
        self.assertTrue(ws.job_request(second['audit_job'])['tag'].startswith('g2-'))
        self.assertTrue(all(ws.state['claims'][cid]['state']=='stale' for cid in old_ids))
        self.assertEqual(len(ws.state['turn_history']), 1)
        Engine(ws, provider).verify_release()

    def test_informed_reframe_is_not_counted_as_blind_worker(self):
        ws = self.workspace(backend='fixture', config={'max_operations': 1})
        provider = FixtureBackend(ws, schedule_op='reframe')
        result = Engine(ws, provider).advance()
        operation = next(r for r in provider.requests if r['role']=='reframe_informed')
        self.assertIn('claims', operation['inputs'])
        self.assertEqual(result['assurance'], 'simulation_only')
        self.assertEqual(len([r for r in provider.requests if r['role']=='reframe']), 1)

    def test_failed_transport_not_silently_repeated(self):
        count = []
        def transport(*args):
            count.append(1)
            return {'id':'resp-fixture', 'status':'incomplete', 'model':'fixture', 'output':[]}
        ws = self.workspace(backend='openai', model='explicit-fixture', config={'allow_remote':True})
        provider = OpenAIBackend(ws.root, ws.state['sources'], ws.state['config'], transport=transport)
        job = self.make_job(ws)
        with self.assertRaises(StateDyneError): provider.execute(job)
        with self.assertRaises(StateDyneError): provider.execute(job)
        self.assertEqual(len(count), 1)
        newer = ws.retry_job(job['id'], 'Previous output was incomplete; make a new explicit attempt.')
        with self.assertRaises(StateDyneError): provider.execute(newer)
        self.assertEqual(len(count), 2)
        self.assertTrue((ws.root/'jobs'/job['id']/'failure.json').exists())

    def test_adoption_relevance_creates_actual_work_not_only_field(self):
        class AdoptionFixture(FixtureBackend):
            def execute(self, job):
                if job['role'] != 'schedule':
                    return super().execute(job)
                cached = self.ws.result(job['id'])
                if cached: return cached
                self.requests.append(deepcopy(job))
                result = {'decisions': [], 'finish': True, 'finish_reason': 'Current tasks complete.',
                          'delivery_scope':'actions','adoption_relevant':True,'scope_reason':'User asked for actions requiring adoption.'}
                return write_result(self.ws.root,job,result,kind='fixture',worker_ref='fixture-'+job['id'],actual_model='fixture')
        ws = self.workspace(backend='fixture', scope='actions'); provider=AdoptionFixture(ws)
        Engine(ws, provider).advance()
        roles=[r['role'] for r in provider.requests]
        self.assertTrue({'change_forward','change_backward'}.issubset(set(roles)))
        self.assertIn('adoption',roles)
        self.assertLess(roles.index('adoption'),roles.index('compose'))


class FirstPassBoundaryAndQuestionTests(Base):
    def test_three_raw_only_workers_run_before_first_interpretation_gate(self):
        ws=self.workspace(backend='fixture')
        provider=FixtureBackend(ws)
        release=Engine(ws,provider).advance()
        roles=[x['role'] for x in provider.requests]
        self.assertLess(max(roles.index(x) for x in ('discovery','reframe','contrast_probe')), roles.index('entry_review'))
        first=next(x for x in provider.requests if x['role']=='entry_review')
        self.assertEqual(len(first['inputs']['first_pass_job_ids']),8)
        self.assertEqual(len(first['inputs']['foci']),1)
        for role in ('frame','discovery','reframe','contrast_probe','environment_scout','blind_challenge'):
            req=next(x for x in provider.requests if x['role']==role)
            self.assertNotIn('claims',req['inputs'])
            self.assertNotIn('unknowns',req['inputs'])
        self.assertEqual(release['assurance'],'simulation_only')

    def test_first_gate_reopens_and_merges_concrete_repair(self):
        ws=self.workspace(backend='fixture')
        provider=FixtureBackend(ws,reopen_first_pass=True)
        release=Engine(ws,provider).advance()
        roles=[x['role'] for x in provider.requests]
        self.assertLess(roles.index('entry_review'),roles.index('entry_repair'))
        self.assertLess(roles.index('entry_repair'),roles.index('schedule'))
        self.assertEqual(roles.count('entry_review'),2)
        self.assertEqual(ws.state['entry_reviews'][-1]['output']['verdict'],'pass')
        self.assertIn('gate_findings',next(x for x in provider.requests if x['role']=='entry_repair')['inputs'])
        self.assertEqual(release['assurance'],'simulation_only')
        self.assertTrue(any(ws.job_request(x['job_id'])['role']=='entry_repair' for x in ws.state['work_results']))

    def test_passing_first_gate_requires_concrete_comparison(self):
        class EmptyGate(FixtureBackend):
            def execute(self,job):
                if job['role']!='entry_review':return super().execute(job)
                product={'system_coverage_dispositions':[], 'search_space_assessment': {
                  'judgment':'no_new_space_after_search','candidate_claim_ids':[],
                  'prior_representation_limit':'Local lock explains overlap only.',
                  'tested_alternative_representation':'External queue could explain the same symptom.',
                  'unreported_outcome':'','discriminating_observation':'',
                  'comparison_reason':'Scripted no-increment negative control.'},
                 'verdict':'pass','new_foci':[], 'coverage':[{"focus_id":f["id"], "status":"explained", "candidate_claim_ids":[c["id"] for c in job["inputs"]["claims"][:1]], "missing_or_explained_bridge":"Shared resource queues requests.", "unreported_prediction":"Removing the lock reduces waiting.","discriminator":"Compare without lock.","reason":"Under overlap."} for f in job["inputs"]["foci"]], 'examined_contrasts':['Shared resource and overlap.'],
                        'missing_relation':'','why_material':'','next_operator':'reframe',
                        'required_new_prediction_or_test':'','no_gap_reason':''}
                return write_result(self.ws.root,job,product,kind='fixture',worker_ref='fixture-'+job['id'],actual_model='fixture')
        ws=self.workspace(backend='fixture')
        with self.assertRaises(StateDyneError): Engine(ws,EmptyGate(ws)).advance()

    def test_four_distinct_visible_questions_are_allowed(self):
        from test_runtime import draft_for
        ws=self.workspace(backend='fixture'); provider=FixtureBackend(ws,with_unknown=True)
        Engine(ws,provider).advance()
        current=ws.current_view(); current['delivery_scope']='analysis'
        job=ws.get_job('test-question-overload','compose','draft',current,'test')
        proposed=draft_for(job)
        # No fixture-level three-question truncation: all four distinct,
        # actionable synthetic unknowns are already available to ask.
        self.assertGreaterEqual(len([q for q in proposed['information_dispositions']
                              if q['treatment']=='ask']), 4)
        write_result(ws.root,job,proposed,kind='fixture',worker_ref='extra-question',actual_model='fixture')
        ws.set_draft(job['id'])
        self.assertGreaterEqual(len([q for q in ws.state['draft']['output']['information_dispositions'] if q['treatment']=='ask']), 4)

    def test_visible_single_question_cannot_be_an_unbounded_form(self):
        from test_runtime import draft_for
        ws=self.workspace(backend='fixture',config={'max_question_characters':220}); provider=FixtureBackend(ws,with_unknown=True)
        Engine(ws,provider).advance()
        inputs=ws.current_view(); job=ws.get_job('question-long','compose','draft',inputs,'test')
        proposed=draft_for(job); long_question='这个反差的直接原因是什么、是否有其他不同的场景？'*15
        proposed['information_dispositions'][0]['visible_question']=long_question
        proposed['answer']+='\n'+long_question
        write_result(ws.root,job,proposed,kind='fixture',worker_ref='long-question',actual_model='fixture')
        with self.assertRaisesRegex(StateDyneError,'too long'):ws.set_draft(job['id'])


class MigrationAndEntryIndependenceTests(Base):
    def test_old_workspace_version_is_rejected_without_mutation(self):
        ws=self.workspace()
        prior=read_json(ws.path)
        prior['skill_version']='10.0.0'
        save_json(ws.path,prior)
        before=ws.path.read_bytes()
        with self.assertRaisesRegex(StateDyneError,'Incompatible previous'):Workspace(ws.root)
        self.assertEqual(ws.path.read_bytes(),before)

    def test_entry_review_cannot_reuse_initial_worker_identity(self):
        class SharedGateRef(FixtureBackend):
            def execute(self,job):
                result=super().execute(job)
                if job['role']=='entry_review':
                    from test_runtime import read_json,save_json
                    path=self.ws.root/'jobs'/job['id']/'result.json'
                    data=read_json(path);data['worker_ref']='fixture-J0001';save_json(path,data)
                return result
        ws=self.workspace(backend='fixture')
        provider=SharedGateRef(ws)
        with self.assertRaisesRegex(StateDyneError,'fresh independent worker'):
            Engine(ws,provider).advance()
