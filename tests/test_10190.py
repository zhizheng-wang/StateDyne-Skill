"""10.19 independent-search and decision-robustness software checks.

These tests use fabricated data and certify neither semantic discovery nor
true multi-agent execution, market outcomes or intervention effectiveness.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sd_runtime import __version__
from sd_runtime.probe_portfolio import verify_exploration_attempts
from sd_runtime.load_bearing import register_load_bearing, check_draft_against_load_bearing
from sd_runtime.evaluation import paired_diagnostics, DIMENSIONS
from sd_runtime.common import StateDyneError
from sd_runtime.backends import write_result
from sd_runtime.store import Workspace
from sd_runtime.engine import instructions
from test_runtime import TASK, work
from fixture_helpers_10190 import search_for

ROOT=Path(__file__).resolve().parents[1]

class SearchOpportunityTest(unittest.TestCase):
    def item(self, advanced=True):
        return {'local_id':'P1','advance':advanced}
    def package(self, advanced=True):
        p=self.item(advanced)
        return {'probes':[p], 'exploration_attempts':search_for([p])}
    def test_outside_current_model_admitted(self):
        verify_exploration_attempts(self.package())
    def test_valid_explicit_deferral_preserved(self):
        verify_exploration_attempts(self.package(False))
    def test_grounded_null_search_allowed(self):
        verify_exploration_attempts({'probes':[],'exploration_attempts':search_for([])})
    def test_no_attempt_is_not_independent_search(self):
        with self.assertRaisesRegex(StateDyneError,'exploration receipt'):
            verify_exploration_attempts({'probes':[],'exploration_attempts':[]})
    def test_incumbent_only_not_model_outside(self):
        obj=self.package();obj['exploration_attempts'][0]['focus']='within_current_model'
        with self.assertRaisesRegex(StateDyneError,'beyond'):
            verify_exploration_attempts(obj)
    def test_same_prediction_and_counterprediction_invalid(self):
        obj=self.package();obj['exploration_attempts'][0]['rival_prediction']=obj['exploration_attempts'][0]['distinct_prediction']
        with self.assertRaisesRegex(StateDyneError,'discriminating'):
            verify_exploration_attempts(obj)
    def test_admitted_probe_must_really_advance(self):
        obj=self.package();obj['probes'][0]['advance']=False
        with self.assertRaisesRegex(StateDyneError,'really admitted'):
            verify_exploration_attempts(obj)
    def test_deferred_probe_cannot_falsely_advance(self):
        obj=self.package(False);obj['probes'][0]['advance']=True
        with self.assertRaisesRegex(StateDyneError,'explicitly deferred'):
            verify_exploration_attempts(obj)
    def test_fabricated_link_is_rejected(self):
        obj=self.package();obj['exploration_attempts'][0]['probe_local_ids']=['invented']
        with self.assertRaisesRegex(StateDyneError,'does not exist'):
            verify_exploration_attempts(obj)
    def test_null_search_needs_real_negative_explanation(self):
        obj={'probes':[],'exploration_attempts':search_for([])}
        obj['exploration_attempts'][0]['reason']='None.'
        with self.assertRaisesRegex(StateDyneError,'concrete negative'):
            verify_exploration_attempts(obj)
    def test_duplicate_attempt_identifier_fails(self):
        obj=self.package();obj['exploration_attempts'].append(deepcopy(obj['exploration_attempts'][0]))
        with self.assertRaisesRegex(StateDyneError,'unique'):
            verify_exploration_attempts(obj)

class PivotalRobustnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ws=Workspace.create(Path(self.tmp.name)/'run',TASK,backend='fixture')
        src=self.ws.get_job('source','discovery','work',self.ws.raw_view(),instructions('discovery'))
        write_result(self.ws.root,src,work(),kind='fixture',worker_ref='simulated-raw',actual_model='fixture')
        self.ws.merge_work(src['id']);self.cid=next(iter(self.ws.active_claims()))
    def payload(self,role='forecast',importance='critical'):
        return {'thesis_at_risk':'Business value could be discounted after a strong growth story.',
           'as_of_scope':'No historical date stated in this synthetic case.',
           'as_of_handling':'All observed inputs are synthetic and timeless.',
           'examined_claim_ids':[self.cid],
           'tests':[{'local_id':'L1','claim_ids':[self.cid],
                'proposition':'Long-run forecast depends on the assumption about persistent cash generation.',
                'role':role,'support':'conditional','evidence':[],
                'importance':importance,'hidden_premise':'Mature margin persists after growth investment.',
                'strongest_rival':'The margin stabilizes much lower after competition.',
                'differentiated_outcome':'The economic value drops even though current revenue rises.',
                'decisive_test':'Compare mature unit margins and customer cohorts under both scenarios.',
                'route':'unavailable','disposition':'retain',
                'reason':'Current synthetic inputs do not prove long-run margin durability.',
                'quantified_incremental_claim':False}],
           'recalculations':[],'robustness_checks':[],'net_effect_checks':[],
           'best_countermodel':'A competitive market may permanently lower margin.',
           'decision_reversal':'Lower mature margin would reverse the valuation conclusion.',
           'discovery_limit':'No independent future customer and margin data are available.'}
    def stress(self,kind='forecast_sensitivity'):
        return {'local_id':'S1','claim_ids':[self.cid], 'kind':kind,
          'base_assumption':'A mature margin of 10% is sustainable.',
          'changed_assumption':'Competition reduces the mature margin to 6%.',
          'base_outcome':'The modeled operating value justifies the proposed price.',
          'changed_outcome':'The modeled operating value falls below that price.',
          'impact_on_judgment':'The recommendation changes when normalized margin is lower.',
          'would_reverse':True,'evidence_route':'unavailable',
          'evidence_or_test':'Review a full cohort margin after discounts and acquisition costs mature.',
          'visible_limit':'估值高度依赖长期利润率，较低的成熟利润率将改变投资判断。'}
    def register(self,obj):
        job=self.ws.get_job('burden','load_bearing','load_bearing',self.ws.current_view(),instructions('load_bearing'))
        write_result(self.ws.root,job,obj,kind='fixture',worker_ref='simulated-auditor',actual_model='fixture')
        register_load_bearing(self.ws,job['id'])
    def test_pivotal_forecast_must_receive_sensitivity(self):
        with self.assertRaisesRegex(StateDyneError,'alternate-assumption sensitivity'):
            self.register(self.payload())
    def test_valid_pivotal_forecast_sensitivity_accepted(self):
        obj=self.payload();obj['robustness_checks']=[self.stress()]
        self.register(obj)
        self.assertEqual(len(self.ws.state['load_bearing_audit']['robustness_checks']),1)
    def test_pivotal_innovation_must_compare_baseline(self):
        with self.assertRaisesRegex(StateDyneError,'no-intervention/strong-existing-alternative'):
            self.register(self.payload('intervention'))
    def test_incrementality_counterfactual_counts(self):
        obj=self.payload('intervention');obj['robustness_checks']=[self.stress('incrementality_counterfactual')]
        self.register(obj)
    def test_existing_alternative_baseline_counts(self):
        obj=self.payload('intervention');obj['robustness_checks']=[self.stress('strong_alternative_baseline')]
        self.register(obj)
    def test_minor_unquantified_forecast_does_not_force_math(self):
        self.register(self.payload('forecast','minor'))
    def test_rival_world_identical_assumption_rejected(self):
        obj=self.payload();c=self.stress();c['changed_assumption']=c['base_assumption'];obj['robustness_checks']=[c]
        with self.assertRaisesRegex(StateDyneError,'differ in assumptions'):
            self.register(obj)
    def test_rival_world_identical_result_rejected(self):
        obj=self.payload();c=self.stress();c['changed_outcome']=c['base_outcome'];obj['robustness_checks']=[c]
        with self.assertRaisesRegex(StateDyneError,'differ in assumptions'):
            self.register(obj)
    def test_false_claim_id_rejected(self):
        obj=self.payload();c=self.stress();c['claim_ids']=['nonexistent'];obj['robustness_checks']=[c]
        with self.assertRaisesRegex(StateDyneError,'unknown'):
            self.register(obj)
    def test_changing_conclusion_must_reach_visible_answer(self):
        obj=self.payload();obj['robustness_checks']=[self.stress()];self.register(obj)
        draft={'claim_dispositions':[{'claim_id':self.cid,'treatment':'conditional'}],
               'answer':'High growth may create value, but the conclusion is conditional.'}
        with self.assertRaisesRegex(StateDyneError,'alternative-assumption limit'):
            check_draft_against_load_bearing(self.ws,draft)
        draft['answer']+=' '+self.stress()['visible_limit']
        check_draft_against_load_bearing(self.ws,draft)
    def test_unused_premise_does_not_force_display_of_its_limit(self):
        obj=self.payload();obj['robustness_checks']=[self.stress()];self.register(obj)
        check_draft_against_load_bearing(self.ws,{'claim_dispositions':[{'claim_id':self.cid,'treatment':'not_selected'}],
             'answer':'The forecast cannot be validated with currently available evidence.'})

class PairedEvaluationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.samples=[{'sample_id':'a','case_id':'one','arm':'baseline','repetition':0,
                       'status':'answered','elapsed_seconds':10,'api_responses':1,
                       'usage':{'input_tokens':100,'output_tokens':100,'total_tokens':200}},
                      {'sample_id':'b','case_id':'one','arm':'statedyne','repetition':0,
                       'status':'complete','elapsed_seconds':25,'api_responses':4,
                       'usage':{'input_tokens':300,'output_tokens':400,'total_tokens':700}}]
        self.key={'r1':{k:self.samples[0][k] for k in ('sample_id','case_id','arm','repetition')},
                  'r2':{k:self.samples[1][k] for k in ('sample_id','case_id','arm','repetition')}}
        self.review=[{'review_id':'r1','scores':{d:2 for d in DIMENSIONS},'evidence_notes':'A visible but conditional hypothesis was recorded.'},
                     {'review_id':'r2','scores':{d:3 for d in DIMENSIONS},'evidence_notes':'A concrete new tested prediction was recorded.'}]
    def files(self):
        for n,v in (('review.json',self.review),('key.json',self.key),('samples.json',self.samples)):
            (self.root/n).write_text(json.dumps(v),encoding='utf8')
        return self.root/'review.json',self.root/'key.json',self.root/'samples.json'
    def test_paired_quality_and_resource_cost(self):
        review,key,samples=self.files();out=paired_diagnostics(review,key,samples,'R1')
        self.assertEqual(out['complete_pairs'],1)
        self.assertEqual(out['by_dimension']['discovery']['mean_delta'],1)
        self.assertEqual(out['by_dimension']['discovery']['wins'],1)
        self.assertEqual(out['pairs'][0]['resource_comparison']['total_tokens']['ratio'],3.5)
        self.assertEqual(out['pairs'][0]['resource_comparison']['elapsed_seconds']['ratio'],2.5)
    def test_run_failure_cannot_be_silently_excluded(self):
        self.samples[1]['status']='failed';rev,key,sa=self.files()
        out=paired_diagnostics(rev,key,sa,'R1')
        self.assertEqual(out['complete_pairs'],0)
        self.assertIn('did not complete',out['skipped_pairs'][0]['reason'])
    def test_missing_counterpart_is_recorded(self):
        self.samples=self.samples[:1];self.review=self.review[:1];self.key={"r1":self.key["r1"]};rev,key,sa=self.files()
        out=paired_diagnostics(rev,key,sa,'R1')
        self.assertEqual(out['complete_pairs'],0)
        self.assertIn('missing',out['skipped_pairs'][0]['reason'])
    def test_duplicate_sample_ids_detected(self):
        self.samples[1]['sample_id']='a';rev,key,sa=self.files()
        with self.assertRaisesRegex(StateDyneError,'Duplicate sample'):
            paired_diagnostics(rev,key,sa,'R1')
    def test_blind_key_mismatch_detected(self):
        self.key['r2']['arm']='baseline';rev,key,sa=self.files()
        with self.assertRaisesRegex(StateDyneError,'does not match'):
            paired_diagnostics(rev,key,sa,'R1')
    def test_scores_require_observable_notes(self):
        self.review[0]['evidence_notes']='';rev,key,sa=self.files()
        with self.assertRaisesRegex(StateDyneError,'evidence notes'):
            paired_diagnostics(rev,key,sa,'R1')
    def test_identical_score_is_tie_not_win(self):
        self.review[1]['scores']['discovery']=2;rev,key,sa=self.files()
        out=paired_diagnostics(rev,key,sa,'R1')
        self.assertEqual(out['by_dimension']['discovery']['ties'],1)
    def test_unscored_dimension_cannot_be_invented(self):
        self.review[1]['scores']['discovery']=None;rev,key,sa=self.files()
        out=paired_diagnostics(rev,key,sa,'R1')
        self.assertEqual(out['by_dimension']['discovery']['n_pairs'],0)
        self.assertIsNone(out['by_dimension']['discovery']['mean_delta'])

class ArtifactIdentityTest(unittest.TestCase):
    def test_version_and_source_bytes(self):
        from sd_runtime import __version__
        import json
        released=json.loads((ROOT/'references/source-map.json').read_text('utf8'))['skill_version']
        self.assertEqual(__version__,released)
        self.assertIn('StateDyne '+released,(ROOT/'SKILL.md').read_text('utf8'))
        import hashlib
        self.assertEqual(hashlib.sha256((ROOT/'references/method.zh-CN.md').read_bytes()).hexdigest(),
                         'fd2f4323daf95cc2c05f8e02b6daa98cec6184a34496be1ee82510fc46802f03')
        self.assertEqual(hashlib.sha256((ROOT/'engineering/execution-spec-v3.7.zh-CN.md').read_bytes()).hexdigest(),
                         '0363d8df83d38ce1bed594c97a3493d24a4cac58f934df1a01872617b5b2eb45')

if __name__=='__main__':unittest.main()
