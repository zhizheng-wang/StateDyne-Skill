"""10.28 portability, multi-predicate same-entity outcomes, and action causal bridges.

All cases are synthetic and unrelated to previously evaluated user stories.
Software assertions are not a proxy for true independent model cognition.
"""
from __future__ import annotations
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from sd_runtime.common import StateDyneError
from sd_runtime.objective_intersection import validate_objective_joins, validate_objective_join_review
from sd_runtime.delivery_quality import validate_delivery_quality
from sd_runtime.engine import instructions
from sd_runtime.schemas import SCHEMAS, validate


def q(local='O1',kind='eligible_net_increment'):
    return {'local_id':local,'measure_kind':kind}


def join(local='J1',kind='conditional_intersection'):
    return {'local_id':local,'quantity_ids':['O1'],'claim_ids':[],
            'target_entity_or_cohort':'One physical order, same week',
            'necessary_conditions':[
                {'name':'delivered on time','status':'estimated','evidence_or_assumption':'Assumed eligible order delivery fraction'},
                {'name':'passed independent safety inspection','status':'unverified','evidence_or_assumption':'Safety inspections are not linked to order delivery IDs'}],
            'joint_status':kind,'same_entity_basis':'Same order ID required but not observed',
            'missing_join_or_displacement':'No cross-table order-ID linkage; cancelations and reshipments are unknown',
            'visible_joint_anchor':'The same order must be on time and pass safety inspection.',
            'visible_uncertainty_anchor':'The combined eligible result has not been observed.'}


def drafted(joins=None):
    joins = [join()] if joins is None else joins
    return {'answer':'The same order must be on time and pass safety inspection. The combined eligible result has not been observed.',
            'status':'provisional','pivotal_quantities':[q()], 'used_claim_ids':[], 'objective_joins':joins}


def audited(joins=None, verdict='pass'):
    joins=[join()] if joins is None else joins
    return {'verdict':verdict,
            'objective_join_coverage_reason':'Checked the goal to identify same-order intersections and strongest missing record links.',
            'objective_join_reviews':[
                {'local_id':j['local_id'], 'verdict':'conditional_only',
                 'entity_and_time_match':'Only matching order ID and time may support the claim.',
                 'strongest_non_joint_alternative':'Inspected orders could be a different cohort from timely orders.',
                 'evidence_or_missing_join':'Matched identity record is not available.',
                 'consequence_for_conclusion':'Only a forecast range, not a verified completed result.'}
                for j in joins]}


class ObjectiveIntersectionContractTests(unittest.TestCase):
    def test_conditional_cross_entity_prediction_is_allowed(self):
        d=drafted()
        validate_objective_joins(None,d)
        validate_objective_join_review(audited(), d)

    def test_no_join_cannot_claim_eligible_net_increment(self):
        with self.assertRaisesRegex(StateDyneError,'same-entity'):
            validate_objective_joins(None,drafted([]))

    def test_two_separately_estimated_marginals_not_observed_joint_success(self):
        j=join(kind='observed_intersection')
        with self.assertRaisesRegex(StateDyneError,'Cannot claim observed'):
            validate_objective_joins(None,drafted([j]))

    def test_true_same_id_observation_requires_individual_evidence(self):
        j=join(kind='observed_intersection')
        j['same_entity_basis']='Independent order ledger joined by order-ID; actual 2027 batch records'
        for c in j['necessary_conditions']:
            c['status']='observed_same_entities'
            c['evidence_or_assumption']='Matched row verified against joint ledger'
        validate_objective_joins(None,drafted([j]))

    def test_not_linked_is_not_an_observation(self):
        j=join(kind='observed_intersection')
        j['same_entity_basis']='not linked'
        for c in j['necessary_conditions']:
            c['status']='observed_same_entities'
        with self.assertRaisesRegex(StateDyneError,'positive same-entity'):
            validate_objective_joins(None,drafted([j]))

    def test_missing_uncertainty_in_visible_answer_rejected(self):
        d=drafted();d['answer']=d['answer'].split(' The combined')[0]
        with self.assertRaisesRegex(StateDyneError,'visibly conditional'):
            validate_objective_joins(None,d)

    def test_unresolved_intersection_cannot_be_marked_complete(self):
        j=join(kind='unresolved');d=drafted([j]);d['status']='complete'
        with self.assertRaisesRegex(StateDyneError,'Cannot claim complete'):
            validate_objective_joins(None,d)

    def test_unverified_joint_cannot_receive_verified_audit(self):
        a=audited();a['objective_join_reviews'][0]['verdict']='joint_verified'
        with self.assertRaisesRegex(StateDyneError,'cannot be certified'):
            validate_objective_join_review(a,drafted())

    def test_rejected_joint_cannot_pass_independent_audit(self):
        a=audited();a['objective_join_reviews'][0]['verdict']='needs_revision'
        with self.assertRaisesRegex(StateDyneError,'Cannot pass'):
            validate_objective_join_review(a,drafted())

    def test_missing_joint_review_cannot_pass(self):
        a=audited();a['objective_join_reviews']=[]
        with self.assertRaisesRegex(StateDyneError,'review each'):
            validate_objective_join_review(a,drafted())

    def test_wrong_quantity_id_not_accepted(self):
        j=join();j['quantity_ids']=['O2']
        with self.assertRaisesRegex(StateDyneError,'invalid or repeated'):
            validate_objective_joins(None,drafted([j]))

    def test_no_fixed_max_for_independent_joint_consequences(self):
        js=[]
        for k in range(18):
            item=join(local=f'J{k}');item['quantity_ids']=[f'O{k}'];js.append(item)
        d=drafted(js)
        d['pivotal_quantities']=[q(local=f'O{k}') for k in range(18)]
        validate_objective_joins(None,d)
        validate_objective_join_review(audited(js),d)

    def test_generic_non_numeric_work_doesnt_fabricate_joints(self):
        d={'answer':'Qualitative comparison only.', 'status':'complete',
           'pivotal_quantities':[], 'used_claim_ids':[], 'objective_joins':[]}
        validate_objective_joins(None,d)
        validate_objective_join_review(audited([]),d)


class ActionPointCrossModelTests(unittest.TestCase):
    @staticmethod
    def _data():
        aid='A1';pid='P1'
        text='Change queue ownership rather than just count waiting tickets.'
        answer=f'Goal: reduce queue latency. {text}\n' + 'Expected advantage: fewer races than simply monitoring the queue.'
        draft={'used_claim_ids':[aid],
               'answer':answer,
               'delivery_units':[{'kind':'action','claim_id':aid,'visible_text':text,'comparison':'Expected advantage: fewer races than simply monitoring the queue.'}],
               'claim_dispositions':[{'claim_id':aid,'treatment':'conditional'}]}
        prior={'point':{pid},'action':set()}
        claims={aid:{'kind':'action','depends_on':[pid],'epistemic_status':'hypothesis'},
                pid:{'kind':'point','depends_on':[],'epistemic_status':'hypothesis'}}
        workspace=SimpleNamespace(active_claims=lambda:claims,
            previously_delivered_interventions=lambda:prior,
            state={'delivery_scope':'actions','scope':'actions','adoption_relevant':False})
        audit={'verdict':'pass','causal_boundary_reviews':[], 'point_value_reviews':[], 'plan_combination_reviews':[],
               'change_adoption_review':{'status':'not_relevant','relevance_reason':'No material habit barriers.'},
               'stage_boundary_review':{'delivered_scope':'actions','reason':'Actions now.','premature_future_content':False},
               'action_point_reviews':[{'action_claim_id':aid,'point_claim_ids':[pid],
                   'changed_relation_and_path':'Changing queue ownership removes repeated waiting contention.',
                   'distinct_gain_vs_no_action':'May lower delays if contention is observed.',
                   'strongest_competing_action':'Leave queue untouched and measure external rate limits.',
                   'burden_and_failure_boundary':'Requires compatible queue implementation and measurements.',
                   'user_visible_path':text, 'verdict':'conditional'}],
               'strategy_challenge':{'selected_action_claim_ids':[aid],
                   'no_extra_action_alternative':'No new action.','distinct_gain':'Lower lock contention.',
                   'added_burden':'Engineering migration.', 'overlap_or_monitoring_risk':'Extra monitoring cost.',
                   'when_alternative_wins':'No actual queue lock.',
                   'visible_comparison':'Expected advantage: fewer races than simply monitoring the queue.',
                   'verdict':'conditional'}}
        return workspace,audit,draft

    def test_independent_action_review_maps_to_prior_audited_point(self):
        ws,audit,draft=self._data()
        validate_delivery_quality(ws,audit,draft)

    def test_unmapped_new_action_cannot_pass(self):
        ws,a,d=self._data();a['action_point_reviews']=[]
        with self.assertRaisesRegex(StateDyneError,'newly delivered action'):
            validate_delivery_quality(ws,a,d)

    def test_false_action_point_mapping_rejected(self):
        ws,a,d=self._data();a['action_point_reviews'][0]['point_claim_ids']=['P-new']
        with self.assertRaisesRegex(StateDyneError,'previously reviewed'):
            validate_delivery_quality(ws,a,d)

    def test_action_claim_must_depend_on_claimed_point(self):
        ws,a,d=self._data();ws.active_claims()['A1']['depends_on']=[]
        with self.assertRaisesRegex(StateDyneError,'causal dependencies'):
            validate_delivery_quality(ws,a,d)

    def test_action_cannot_claim_success_without_visible_causal_path(self):
        ws,a,d=self._data();a['action_point_reviews'][0]['user_visible_path']='Unwritten mechanism.'
        with self.assertRaisesRegex(StateDyneError,'explained visibly'):
            validate_delivery_quality(ws,a,d)

    def test_action_failed_own_bridge_blocks_release(self):
        ws,a,d=self._data();a['action_point_reviews'][0]['verdict']='needs_revision'
        with self.assertRaisesRegex(StateDyneError,'cannot pass'):
            validate_delivery_quality(ws,a,d)

    def test_all_required_roles_have_unified_knowledge_gate(self):
        for role in ('frame','system_map','goal_scout','environment_scout',
                     'selection_scout','relation_scout','blind_challenge',
                     'change_forward','change_backward','change_action_probe',
                     'change_portfolio','compose','audit','schedule'):
            prompt=instructions(role)
            self.assertIn('跨模型统一认知与交付契约',prompt)
        for role in ('compose','audit','load_bearing','change_forward','change_backward'):
            self.assertIn('同一结果的必要条件交集',instructions(role))
        for role in ('compose','audit'):
            self.assertIn('action_point_reviews',instructions(role))

    def test_entry_concise_and_full_prior_protocol_preserved(self):
        curr=(ROOT/'SKILL.md').read_text()
        old=(ROOT/'engineering/history/10.27.0/archived-entry-10.27.md').read_text()
        self.assertLess(len(curr),len(old)*0.65)
        for marker in ('十项', '不设数量上限','交集','认知', '独立','下一步'):
            self.assertIn(marker,curr)
        self.assertIn('StateDyne 10.27.0',old)
        self.assertTrue((ROOT/'references/method.zh-CN.md').is_file())

    def test_action_contract_visible_on_engine_role(self):
        self.assertIn('actions',str(SCHEMAS['audit']))
        self.assertIn('action_point_reviews',SCHEMAS['audit']['properties'])
        self.assertIn('objective_join_reviews',SCHEMAS['audit']['properties'])

if __name__ == '__main__':
    unittest.main()
