"""10.17 information benefit retained; 10.18 frees the frontstage wording.

Synthetic protocol tests, NOT evidence of natural-language model performance.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sd_runtime.common import StateDyneError
from sd_runtime.inquiry_contract import (validate_question_groups, validate_question_resolution,
                                        validate_question_payoff, previous_question_groups)
from sd_runtime.schemas import SCHEMAS, validate
from test_runtime import Base

PURPOSE='后台区分共享资源等待与各进程独立负载，两个答案会改变优先调查的过程。'

def grp(ids=('Q1',), gid='G1'):
    return {'group_id':gid,'unknown_ids':list(ids),'analytic_purpose':PURPOSE,
            'if_first':'如果仅并发时变慢，则优先定位共享资源的等待机制。',
            'if_second':'如果各自单独运行同样慢，则优先定位独立计算或限流。',
            'if_unknown':'没有可靠比较时暂时保留两个候选，由系统日志寻找新证据。'}

def response(groups=None, asks=('Q1',)):
    groups=groups if groups is not None else [grp(asks)] if asks else []
    return {'answer':'同时执行时出现的变慢值得进一步核对；能提供并发与串行记录吗？\n'
                     + '\n'.join(f'Is {i} slow only when overlapped?' for i in asks),
            'information_dispositions':[{'unknown_id':i,'treatment':'ask',
                 'visible_question':f'Is {i} slow only when overlapped?'} for i in asks],
            'question_groups':groups,
            'question_payoff':{'covered_groups':[],'evidence_gained':'',
                'still_unknown':'','answer_anchor':''}}

class GroupValueTests(unittest.TestCase):
    def test_valid_group_without_frontend_purpose_script(self):
        draft=response()
        self.assertNotIn(PURPOSE,draft['answer'])
        validate_question_groups(draft)
    def test_questions_first_are_allowed(self):
        draft=response();draft['answer']=draft['information_dispositions'][0]['visible_question']+'\n'+PURPOSE
        validate_question_groups(draft)
    def test_question_number_has_no_fixed_cap(self):
        items=[f'Q{i}' for i in range(17)]
        validate_question_groups(response([grp(items)],items))
    def test_no_questions_need_no_rationale(self):
        validate_question_groups(response([],()))
    def test_no_questions_cannot_invent_group(self):
        with self.assertRaisesRegex(StateDyneError,'exactly once'):
            validate_question_groups(response([grp()],()))
    def test_question_must_be_assigned(self):
        with self.assertRaisesRegex(StateDyneError,'exactly once'):
            validate_question_groups(response([grp(('Q1',))],('Q1','Q2')))
    def test_question_cannot_be_double_assigned(self):
        two=[grp(('Q1',),'G1'),grp(('Q1',),'G2')]
        with self.assertRaisesRegex(StateDyneError,'exactly once'):
            validate_question_groups(response(two,('Q1',)))
    def test_group_requires_distinct_id(self):
        with self.assertRaisesRegex(StateDyneError,'distinct stable'):
            validate_question_groups(response([grp(('Q1',),'G1'),grp(('Q2',),'G1')],('Q1','Q2')))
    def test_group_cannot_be_empty(self):
        with self.assertRaisesRegex(StateDyneError,'distinct actually asked'):
            validate_question_groups(response([grp(())],('Q1',)))
    def test_internal_purpose_must_be_substantive(self):
        draft=response();draft['question_groups'][0]['analytic_purpose']='为什么问'
        with self.assertRaisesRegex(StateDyneError,'INTERNAL'):
            validate_question_groups(draft)
    def test_two_identical_answer_paths_rejected(self):
        draft=response();draft['question_groups'][0]['if_second']=draft['question_groups'][0]['if_first']
        with self.assertRaisesRegex(StateDyneError,'same model update'):
            validate_question_groups(draft)
    def test_unknown_is_not_mechanism_confirmation(self):
        draft=response();draft['question_groups'][0]['if_unknown']=draft['question_groups'][0]['if_first']
        with self.assertRaisesRegex(StateDyneError,'unobserved answer'):
            validate_question_groups(draft)
    def test_no_unknown_path_rejected(self):
        draft=response();draft['question_groups'][0]['if_unknown']=''
        with self.assertRaisesRegex(StateDyneError,'unknown path'):
            validate_question_groups(draft)
    def test_structure_still_needs_semantic_verification(self):
        validate_question_groups(response())
        self.assertTrue(True)  # Structural fork alone does not certify economic truth.

class FollowupValueTests(unittest.TestCase):
    def receipt(self, outcome='unknown',gid='G1'):
        return {'group_id':gid,'outcome':outcome,
            'evidence_change':'The new observation does not establish resource ownership.',
            'revised_judgment':'Both internal lock and external rate limiting remain possible.'}
    def payoff(self,receipts):
        anchor='The new timing does not establish which limit caused the slowdown.'
        return {'answer':'Additional observations were considered. '+anchor,
         'question_payoff':{'covered_groups':[x['group_id'] for x in receipts],
           'evidence_gained':'The latest timings narrow some hypotheses but do not identify a unique cause.',
           'still_unknown':'Resource ownership remains unresolved without independent system observations.',
           'answer_anchor':anchor}}
    def test_single_fluent_update_suffices(self):
        receipts=[self.receipt()];validate_question_payoff(self.payoff(receipts),receipts)
    def test_missing_group_receipt_rejected(self):
        receipts=[self.receipt()];draft=self.payoff(receipts);draft['question_payoff']['covered_groups']=[]
        with self.assertRaisesRegex(StateDyneError,'all evaluated'):
            validate_question_payoff(draft,receipts)
    def test_duplicated_group_receipts_rejected(self):
        receipts=[self.receipt()];draft=self.payoff(receipts);draft['question_payoff']['covered_groups']=['G1','G1']
        with self.assertRaisesRegex(StateDyneError,'all evaluated'):
            validate_question_payoff(draft,receipts)
    def test_no_receipts_no_invented_payoff(self):
        draft=self.payoff([])
        with self.assertRaisesRegex(StateDyneError,'invent a payoff'):
            validate_question_payoff(draft,[])
    def test_absent_visible_anchor_rejected(self):
        receipts=[self.receipt()];draft=self.payoff(receipts);draft['answer']='Only an unrelated story.'
        with self.assertRaisesRegex(StateDyneError,'visibly communicate'):
            validate_question_payoff(draft,receipts)
    def test_same_gain_and_limit_rejected(self):
        receipts=[self.receipt()];draft=self.payoff(receipts)
        draft['question_payoff']['still_unknown']=draft['question_payoff']['evidence_gained']
        with self.assertRaisesRegex(StateDyneError,'distinguish gained evidence'):
            validate_question_payoff(draft,receipts)
    def test_no_expected_groups_allow_empty(self):
        validate_question_payoff({'answer':'No questions were previously asked.',
            'question_payoff':{'covered_groups':[], 'evidence_gained':'',
              'still_unknown':'','answer_anchor':''}},[])

class DeltaAccountabilityTests(Base):
    def setUp(self):
        super().setUp()
        self.ws=self.workspace(backend='fixture',scope='analysis')
        self.ws.state['turn_history']=[{'draft':{'output':{'question_groups':[grp(('Q1',))]}}}]
    def expected(self,outcome='unknown'):
        return {'impact':'local','reason':'New information changes which concurrent hypothesis remains viable.',
         'affected_claim_ids':[],'affected_unknown_ids':[],
         'goal_or_boundary_changed':False,
         'newly_relevant_difference':'Observed timing does not establish a shared locking mechanism.',
         'new_foci':[],'question_results':[{'group_id':'G1','outcome':outcome,
            'evidence_change':'New timings are reported but their serialisation route is not directly measured.',
            'revised_judgment':'A shared lock remains only one conditional mechanism rather than a settled cause.'}]}
    def test_previous_question_groups_visible_to_delta(self):
        self.assertEqual(previous_question_groups(self.ws)[0]['group_id'],'G1')
    def test_missing_result_cannot_pass(self):
        a=self.expected();a['question_results']=[]
        with self.assertRaisesRegex(StateDyneError,'every prior asked'):
            validate_question_resolution(self.ws,a)
    def test_unknown_user_reply_valid_and_not_denial(self):
        validate_question_resolution(self.ws,self.expected('unknown'))
    def test_partial_or_mixed_valid(self):
        validate_question_resolution(self.ws,self.expected('mixed'))
    def test_new_relation_without_any_model_change_fails(self):
        with self.assertRaisesRegex(StateDyneError,'actually affect'):
            validate_question_resolution(self.ws,self.expected('new_relation'))
    def test_new_relation_with_actual_rebuild_possible(self):
        a=self.expected('new_relation');a['impact']='rebuild'
        validate_question_resolution(self.ws,a)
    def test_duplicate_results_dont_pass(self):
        a=self.expected();a['question_results'].append(deepcopy(a['question_results'][0]))
        with self.assertRaisesRegex(StateDyneError,'every prior asked'):
            validate_question_resolution(self.ws,a)
    def test_delta_schema_enforces_payoff_results(self):
        a=self.expected();validate(a,SCHEMAS['delta_assessment'])
        del a['question_results']
        with self.assertRaisesRegex(StateDyneError,'question_results'):
            validate(a,SCHEMAS['delta_assessment'])

class PortableContractTests(unittest.TestCase):
    def test_skill_has_information_value_not_compulsory_script(self):
        root=Path(__file__).resolve().parents[1]
        skill=(root/'SKILL.md').read_text('utf8')
        operator=(root/'references/operators/compose.md').read_text('utf8')
        self.assertIn('为什么值得问',skill)
        self.assertIn('analytic_purpose',operator)
        self.assertNotIn('每批重要问题先用一两句自然语言解释',skill)
    def test_latest_work_assignments_are_explicit_not_accidental(self):
        skill=(Path(__file__).resolve().parents[1]/'SKILL.md').read_text('utf8')
        self.assertIn('relation_scout',skill)
        self.assertIn('十项独立工作',skill)
        self.assertIn('可用的真实子智能体',skill)

if __name__=='__main__': unittest.main()
