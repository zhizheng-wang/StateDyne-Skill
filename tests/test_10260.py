"""10.26 independent-value unknown handoff and generic numerical coherence.

Synthetic tasks intentionally avoid previous personal/finance/housing cases.
Passing software checks is not evidence of model discovery or source truth.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sd_runtime.common import StateDyneError
from sd_runtime.material_unknowns import validate_material_unknowns
from sd_runtime.conclusion_integrity import check_pivotal_quantities,check_quantity_review


def workspace(route='user', origin='reframe', linked=True, investigated=False, web=False):
    q={'id':'Q1','priority':'important','route':route,'origin':origin,
       'question':'Would a separate distributor account for the unexplained outcome?',
       'related_claims':['C1'] if linked else []}
    return SimpleNamespace(state={'unknowns':{'Q1':q},'investigated_unknowns':['Q1'] if investigated else [],
       'config':{'web_search_enabled':web},'load_bearing_audit':{}},
       active_claims=lambda:{'C1':{'kind':'inference','statement':'A separate distributor can explain the outcome.'}})


def draft():
    return {'used_claim_ids':['C1'],'information_dispositions':[
        {'unknown_id':'Q1','treatment':'defer','decision_effect':'changes_explanation',
         'fallback_if_unknown':'','reason':'The route has not been verified.'}],
        'answer':'A separate distributor could be responsible, but the result remains conditional.',
        'navigation':{'expansion_offer':''},'pivotal_quantities':[]}


def quantity(kind='same_measure',head='2,000–3,000',body='2,000–3,000',closing='2,000–3,000'):
    return {'local_id':'V1','claim_ids':['C1'],'metric':'accepted inspected components',
      'measurement_basis':'reported units minus the observed baseline','population_and_scope':'all plants in a region',
      'period':'five-year cumulative','unit':'completed units','measure_kind':'net_increment',
      'scenario':'base scenario','headline_anchor':f'Headline: {head} units' if head else '',
      'headline_value':head,'body_anchor':f'Calculation: {body} units' if body else '',
      'body_value':body,'conclusion_anchor':f'Conclusion: {closing} units' if closing else '',
      'conclusion_value':closing,'relation':kind,'visible_reconciliation':'',
      'assumption_or_limit':'The baseline must be independently corroborated.'}


class MaterialUnknownTests(unittest.TestCase):
    def test_important_deferred_new_relation_cannot_disappear(self):
        d=draft()
        with self.assertRaisesRegex(StateDyneError,'visible conditional consequence'):
            validate_material_unknowns(workspace(),d)

    def test_real_conditional_consequence_requires_optional_expansion(self):
        d=draft();fallback='If the separate distributor is active, the leading causal explanation changes.'
        d['information_dispositions'][0]['fallback_if_unknown']=fallback
        d['answer']+='\n'+fallback
        with self.assertRaisesRegex(StateDyneError,'continued-search'):
            validate_material_unknowns(workspace(),d)
        d['navigation']['expansion_offer']='We can next inspect that independent distributor record, rather than repeating known tests.'
        d['answer']+='\n'+d['navigation']['expansion_offer']
        validate_material_unknowns(workspace(),d)

    def test_rejected_discovery_does_not_force_questions(self):
        d=draft();d['used_claim_ids']=[]
        validate_material_unknowns(workspace(),d)

    def test_self_research_cannot_be_replaced_by_visible_disclaimer(self):
        d=draft();d['information_dispositions'][0]['fallback_if_unknown']='We do not know if the distributor was used; this result remains conditional.'
        d['answer']+='\n'+d['information_dispositions'][0]['fallback_if_unknown']
        d['navigation']['expansion_offer']='Inspect the independent distributor record.'
        d['answer']+='\n'+d['navigation']['expansion_offer']
        with self.assertRaisesRegex(StateDyneError,'acquisition attempt'):
            validate_material_unknowns(workspace(route='materials'),d)
        validate_material_unknowns(workspace(route='materials',investigated=True),d)

    def test_unavailable_information_is_not_automatically_a_user_request(self):
        d=draft();d['information_dispositions'][0]['treatment']='unavailable'
        d['information_dispositions'][0]['fallback_if_unknown']='No accessible record exists; the forecast remains conditional on a separate distributor.'
        d['answer']+='\n'+d['information_dispositions'][0]['fallback_if_unknown']
        validate_material_unknowns(workspace(route='unavailable'),d)


class NumericIntegrityTests(unittest.TestCase):
    def setup_case(self,qty):
        ans=' '.join(x for x in (qty['headline_anchor'],qty['body_anchor'],qty['conclusion_anchor'],qty['visible_reconciliation']) if x)
        d={'answer':ans,'used_claim_ids':['C1'],'pivotal_quantities':[qty]}
        return workspace(),d

    def test_consistent_cross_section_result_passes(self):
        ws,d=self.setup_case(quantity())
        check_pivotal_quantities(ws,d)

    def test_different_numeric_headline_fails_even_with_valid_arithmetic(self):
        ws,d=self.setup_case(quantity(head='4,000–5,000'))
        with self.assertRaisesRegex(StateDyneError,'disagree on the same'):
            check_pivotal_quantities(ws,d)

    def test_gross_and_qualified_are_distinct_when_explicitly_reconciled(self):
        q=quantity(kind='different_measures_explained',head='4,000–5,000',body='2,000–3,000',closing='2,000–3,000')
        q['visible_reconciliation']='The headline counts all additions, while the body and conclusion count only qualified additions.'
        ws,d=self.setup_case(q)
        check_pivotal_quantities(ws,d)
        d['answer']=d['answer'].replace(q['visible_reconciliation'],'')
        with self.assertRaisesRegex(StateDyneError,'user-visible denominator'):
            check_pivotal_quantities(ws,d)

    def test_unit_or_period_missing_is_not_a_valid_numeric_result(self):
        q=quantity();q['period']='';ws,d=self.setup_case(q)
        with self.assertRaisesRegex(StateDyneError,'period'):
            check_pivotal_quantities(ws,d)

    def test_unmentioned_quantity_cannot_appear_in_pivot_register(self):
        ws,d=self.setup_case(quantity())
        d['answer']=d['answer'].replace('Calculation: 2,000–3,000 units','')
        with self.assertRaisesRegex(StateDyneError,'answer anchor'):
            check_pivotal_quantities(ws,d)

    def test_independent_reviewer_cannot_pass_known_numeric_contradiction(self):
        q=quantity();_,d=self.setup_case(q)
        review={'quantity_id':'V1','verdict':'needs_revision','source_scope_and_units':'Checked regional scope.',
           'competing_numeric_interpretation':'One total is a narrower subgroup.',
           'effect_on_conclusion':'The headline would overstate eligible units.'}
        audit={'verdict':'pass','quantity_reviews':[review], 'numeric_coverage_reason':'One pivotal quantity was reviewed.'}
        with self.assertRaisesRegex(StateDyneError,'cannot pass'):
            check_quantity_review(audit,d)
        audit['verdict']='revise'
        check_quantity_review(audit,d)

    def test_adopted_quantified_net_effect_requires_actual_bridge(self):
        ws,d=self.setup_case(quantity()); d['pivotal_quantities']=[]
        ws.state['load_bearing_audit']={'net_effect_checks':[{'status':'reconciled','claim_ids':['C1']}]}
        with self.assertRaisesRegex(StateDyneError,'missing the cross-section'):
            check_pivotal_quantities(ws,d)

    def test_pivotal_quantities_do_not_force_numerical_guessing(self):
        ws,d=self.setup_case(quantity()); d['pivotal_quantities']=[]
        check_pivotal_quantities(ws,d)

if __name__=='__main__':unittest.main()

from importlib.util import spec_from_file_location, module_from_spec
_spec=spec_from_file_location('compare_runs',ROOT/'scripts/compare_runs.py')
_compare=module_from_spec(_spec);_spec.loader.exec_module(_compare)

class IndependentRunComparisonTests(unittest.TestCase):
    def test_different_estimates_not_forced_equal_but_assumptions_preserved(self):
        first=quantity();second=deepcopy(first)
        second['conclusion_value']='2,400–3,800'
        second['scenario']='less competitive market'
        second['assumption_or_limit']='Assumes cost recovery in a different competition scenario.'
        first_run={'assurance':'simulation_only','pivots':[first]}
        second_run={'assurance':'simulation_only','pivots':[second]}
        got=_compare.compare(first_run,second_run)
        self.assertEqual(got['shared_comparable'],0)
        self.assertEqual({r['status'] for r in got['results']},{'only_first','only_second'})
        self.assertIn('different competition',got['results'][-1]['second_assumption'] or
                      got['results'][0]['second_assumption'])
    def test_same_scenario_different_result_is_visible_for_review(self):
        first=quantity();second=deepcopy(first);second['conclusion_value']='2,100–3,100'
        got=_compare.compare({'assurance':'simulation_only','pivots':[first]},
                             {'assurance':'simulation_only','pivots':[second]})
        self.assertEqual(got['shared_comparable'],1)
        self.assertEqual(got['results'][0]['status'],'different_reported_number')


class FullReleaseAndDispatchTests(unittest.TestCase):
    def test_all_relevant_workers_read_unresolved_and_numeric_contracts(self):
        from sd_runtime.engine import instructions
        for role in ('compose','audit','schedule','load_bearing'):
            result=instructions(role)
            self.assertIn('重要未知',result)
            self.assertIn('同口径',result)
        self.assertIn('信息',instructions('relation_scout'))

    def test_released_draft_structural_payload_cannot_change_undetected(self):
        import tempfile
        from sd_runtime.store import Workspace
        from sd_runtime.engine import Engine
        from test_runtime import TASK,FixtureBackend
        with tempfile.TemporaryDirectory() as tmp:
            ws=Workspace.create(Path(tmp)/'run',TASK,backend='fixture')
            engine=Engine(ws,FixtureBackend(ws));engine.advance()
            self.assertEqual(engine.verify_release()['assurance'],'simulation_only')
            ws.state['draft']['output']['pivotal_quantities'].append(quantity())
            with self.assertRaisesRegex(StateDyneError,'structural quantities'):
                engine.verify_release()

    def test_significant_numeric_forecast_needs_registered_bridge(self):
        d={'answer':'250 units are forecast','used_claim_ids':['C1'],'pivotal_quantities':[]}
        ws=workspace()
        ws.active_claims=lambda:{'C1':{'kind':'prediction','statement':'Forecast 250 units by the end of the period.'}}
        with self.assertRaisesRegex(StateDyneError,'numerical forecast'):
            check_pivotal_quantities(ws,d)
