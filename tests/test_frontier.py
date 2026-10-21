"""Adversarial *program* tests for model-space coverage.

All products in this file are fixtures, never evidence of GPT capability.
"""
from __future__ import annotations
from copy import deepcopy
from test_runtime import (Base, FixtureBackend, TASK, work, draft_for, audit_for,
                          StateDyneError, Workspace, Engine, write_result)
from sd_runtime.engine import instructions
from sd_runtime.frontier import record_focus, check_boundary, ensure_repair_changed_relation


def sample_frame(text=TASK):
    return {"foci":[{"local_id":"F1","evidence":[{"source_id":"S1","quote":text}],
                     "observation":"Concurrency is associated with the slowdown.",
                     "unexplained_difference":"Single operation is not slow.",
                     "why_material":"Different interventions follow from shared queues versus independent processing.",
                     "priority":"critical"}], "no_focus_reason":""}


def sample_coverage(fid, claim_id):
    return {"focus_id":fid,"status":"explained", "candidate_claim_ids":[claim_id],
            "missing_or_explained_bridge":"When both tasks claim a shared lock, one waits while another runs.",
            "unreported_prediction":"Disabling the lock should remove the concurrency-specific delay.",
            "discriminator":"Compare with/without lock while matching the independent compute load.",
            "reason":"This distinguishes shared lock serialization from independent slowdown."}


def setup(ws):
    focus_job=ws.get_job("frame","frame","frame",ws.raw_view(),instructions("frame"))
    write_result(ws.root,focus_job,sample_frame(),kind="fixture",worker_ref="fixture-frame",actual_model="fixture")
    record_focus(ws,focus_job['id'])
    job=ws.get_job('discovery','discovery','work',ws.raw_view(),instructions('discovery'))
    write_result(ws.root,job,work(),kind='fixture',worker_ref='fixture-disc',actual_model='fixture')
    ws.merge_work(job['id'])
    focus=ws.state['foci'][0]['id']; claim_id=next(iter(ws.active_claims()))
    return focus,claim_id


class AnchorsAndGates(Base):
    def test_real_quoted_anchor_required(self):
        ws=self.workspace();job=ws.get_job('frame','frame','frame',ws.raw_view(),instructions('frame'))
        answer=sample_frame('Not a real observation')
        write_result(ws.root,job,answer,kind='fixture',worker_ref='x',actual_model='fixture')
        with self.assertRaisesRegex(StateDyneError,'Source/quote mismatch'):record_focus(ws,job['id'])
        self.assertEqual(ws.state['foci'],[])

    def test_empty_anchor_map_needs_a_reason(self):
        ws=self.workspace();job=ws.get_job('frame','frame','frame',ws.raw_view(),instructions('frame'))
        write_result(ws.root,job,{'foci':[],'no_focus_reason':''},kind='fixture',worker_ref='x',actual_model='fixture')
        with self.assertRaisesRegex(StateDyneError,'No focal phenomena'):record_focus(ws,job['id'])

    def test_missing_focal_coverage_blocks_pass(self):
        ws=self.workspace();fid,cid=setup(ws)
        with self.assertRaisesRegex(StateDyneError,'every source-anchored phenomenon'):
            check_boundary(ws, {'new_foci':[],'coverage':[], 'verdict':'pass'})

    def test_old_observation_cannot_be_new_prediction(self):
        ws=self.workspace();fid,cid=setup(ws)
        row=sample_coverage(fid,cid)
        row['unreported_prediction']=TASK
        with self.assertRaisesRegex(StateDyneError,'known observation'):
            check_boundary(ws,{'new_foci':[],'coverage':[row],'verdict':'pass'})

    def test_pass_does_not_accept_partial_gap(self):
        ws=self.workspace();fid,cid=setup(ws)
        row=sample_coverage(fid,cid);row['status']='partial'
        with self.assertRaisesRegex(StateDyneError,'cannot pass'):
            check_boundary(ws, {'new_foci':[],'coverage':[row], 'verdict':'pass'})

    def test_claim_with_unknown_id_cannot_approve(self):
        ws=self.workspace();fid,cid=setup(ws)
        row=sample_coverage(fid,'never-generated-claim')
        with self.assertRaisesRegex(StateDyneError,'missing or repeated candidate'):
            check_boundary(ws, {'new_foci':[],'coverage':[row], 'verdict':'pass'})

    def test_source_anchored_out_of_model_focal_can_expand_map(self):
        ws=self.workspace();fid,cid=setup(ws)
        review=ws.get_job('first-review','entry_review','entry_review',ws.current_view(),instructions('entry_review'))
        new={"local_id":"X1", "evidence":[{"source_id":"S1","quote":TASK}],
             "observation":"The slowdown happens in the two-process case.",
             "unexplained_difference":"Another unmodeled shared-resource path might produce the same effect.",
             "why_material":"The favored explanation might otherwise be an artifact of framing.",
             "priority":"critical"}
        row2=sample_coverage('X1',cid);row2['status']='open'
        answer={'new_foci':[new], 'coverage':[sample_coverage(fid,cid),row2], 'verdict':'reopen'}
        write_result(ws.root,review,{'system_coverage_dispositions':[], 'search_space_assessment': {
                 'judgment':'no_new_space_after_search','candidate_claim_ids':[],
                 'prior_representation_limit':'A local serialization model is not uniquely identified.',
                 'tested_alternative_representation':'An independent gateway can create overlapping delays.',
                 'unreported_outcome':'','discriminating_observation':'',
                 'comparison_reason':'New source-anchored observation still lacks a differential mechanism.'},
                 'new_foci':[new], 'coverage':[sample_coverage(fid,cid),row2],
               'verdict':'reopen', 'examined_contrasts':['concurrency'], 'missing_relation':'shared path',
               'why_material':'alternate explanations differ', 'next_operator':'reframe',
               'required_new_prediction_or_test':'test independent resource', 'no_gap_reason':''},
               kind='fixture',worker_ref='independent-review',actual_model='fixture')
        admitted=check_boundary(ws,answer,review['id'])
        self.assertEqual([x['id'] for x in admitted],['X1'])
        self.assertEqual(len(ws.state['foci']),1)  # Admission is atomic and caller-controlled.

    def test_recheck_cannot_reuse_old_candidates_for_new_resolution(self):
        ws=self.workspace();fid,cid=setup(ws)
        previous={'coverage':[{**sample_coverage(fid,cid),'status':'partial'}]}
        now={'coverage':[sample_coverage(fid,cid)]}
        with self.assertRaisesRegex(StateDyneError,'reused only old claims'):
            ensure_repair_changed_relation(ws,previous,now,'J0999')

    def test_frontend_must_publish_focal_resolution(self):
        ws=self.workspace();fid,cid=setup(ws)
        draft_job=ws.get_job('compose','compose','draft',ws.current_view(),instructions('compose'))
        draft=draft_for(draft_job)
        draft['focus_dispositions'][0]['visible_resolution']='This sentence is not present in the answer'
        write_result(ws.root,draft_job,draft,kind='fixture',worker_ref='writer',actual_model='fixture')
        with self.assertRaisesRegex(StateDyneError,'visible in the answer'):
            ws.set_draft(draft_job['id'])

    def test_final_auditor_must_account_for_all_foci(self):
        ws=self.workspace(backend='fixture');Engine(ws,FixtureBackend(ws)).advance()
        inputs=ws.current_view();inputs.update(draft=ws.state['draft']['output'], draft_sha256=ws.state['draft']['sha256'])
        job=ws.get_job('bad-audit','audit','audit',inputs,instructions('audit'))
        audit=audit_for(job);audit['examined_focus_ids']=[]
        write_result(ws.root,job,audit,kind='fixture',worker_ref='bad-reviewer',actual_model='fixture')
        with self.assertRaisesRegex(StateDyneError,'examined_focus_ids'):
            ws.set_audit(job['id'])


class UnresolvedStillDelivers(Base):
    def test_exhausted_first_pass_repair_only_allows_provisional_answer(self):
        class OpenGate(FixtureBackend):
            def execute(self,job):
                result=super().execute(job)
                if job['role']=='entry_review':
                    new=deepcopy(result['output'])
                    new['verdict']='reopen';new['coverage'][0]['status']='partial'
                    new['missing_relation']='Unobserved process between input and result'
                    new['why_material']='Different candidate paths would change the remedy'
                    new['required_new_prediction_or_test']='Find evidence that discriminates the two paths'
                    new['no_gap_reason']=''
                    return write_result(self.ws.root,job,new,kind='fixture',worker_ref='fixture-'+job['id'],actual_model='fixture')
                if job['role']=='compose':
                    new=deepcopy(result['output']);new['status']='provisional';new['focus_dispositions'][0]['status']='open'
                    return write_result(self.ws.root,job,new,kind='fixture',worker_ref='fixture-'+job['id'],actual_model='fixture')
                return result
        ws=self.workspace(backend='fixture',config={'max_entry_repairs':0})
        result=Engine(ws,OpenGate(ws)).advance()
        self.assertTrue(result['first_pass_gap_unresolved'])
        self.assertEqual(result['status'],'provisional')
        self.assertNotEqual(ws.state['entry_review']['output']['verdict'],'pass')
        self.assertFalse(result['capability_evaluation_passed'])
