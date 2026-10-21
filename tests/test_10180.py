"""10.18: prompt/validator separation, fresh discovery ordering, and natural payoff.

All tests are synthetic deterministic contracts, not real LLM performance.
"""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))

from sd_runtime import __version__
from sd_runtime.schemas import SCHEMAS, validate
from sd_runtime.inquiry_contract import validate_question_groups, validate_question_payoff
from sd_runtime.inquiry_frontier import discovery_inquiries
from sd_runtime.common import StateDyneError
from test_10170 import grp, response

ROOT=Path(__file__).resolve().parents[1]

class FakeWorkspace:
    def __init__(self):
        self.state={'unknowns':{},'investigated_unknowns':[]}
        self.claims={}
    def active_claims(self):return self.claims
    def job_request(self,jid):return {'role':'reframe'}
    def unknown(self,qid, origin='system_map', priority='important', related=(), state='open'):
        self.state['unknowns'][qid]={'id':qid,'origin':origin,'priority':priority,'route':'user',
           'state':state,'question':qid+'?', 'why_it_matters':'different causal hypotheses',
           'related_claims':list(related),'recognition_prompt':'','counter_cue':''}
    def candidate(self,cid, consequence):
        self.claims[cid]={'id':cid,'origin_job':'job1','distinct_consequences':[consequence]}

class NaturalFrontstageTests(unittest.TestCase):
    def test_internal_purpose_not_required_in_answer(self):
        obj=response()
        self.assertNotIn(obj['question_groups'][0]['analytic_purpose'],obj['answer'])
        validate_question_groups(obj)
    def test_questions_can_precede_any_explanation(self):
        obj=response()
        obj['answer']='Is Q1 slow only when overlapped?'
        validate_question_groups(obj)
    def test_internal_purpose_still_must_be_meaningful(self):
        obj=response();obj['question_groups'][0]['analytic_purpose']='foo'
        with self.assertRaisesRegex(StateDyneError,'INTERNAL'):
            validate_question_groups(obj)
    def test_group_schema_rejects_retired_visible_purpose(self):
        group=grp()
        validate(group,SCHEMAS['draft']['properties']['question_groups']['items'])
        group['visible_purpose']=group.pop('analytic_purpose')
        with self.assertRaises(StateDyneError):
            validate(group,SCHEMAS['draft']['properties']['question_groups']['items'])
    def test_payoff_allows_one_fluent_para_and_one_anchor(self):
        claim='Observed serial-run behavior does not distinguish limiting from contention.'
        r={'answer':'Earlier suggestions were provisional. '+claim+' More evidence would help.',
           'question_payoff':{'covered_groups':['G1'],
            'evidence_gained':'The serial-run observation weakens one candidate but does not settle the bottleneck.',
            'still_unknown':'The external throughput limit and the lock owner are still not independently observed.',
            'answer_anchor':claim}}
        validate_question_payoff(r,[{'group_id':'G1'}])
    def test_payoff_does_not_accept_invisible_anchor(self):
        r={'answer':'No useful new facts.',
           'question_payoff':{'covered_groups':['G1'],
            'evidence_gained':'We received meaningful but ambiguous timings for the processes.',
            'still_unknown':'We lack any accurate resource ownership records.',
            'answer_anchor':'This precise sentence is not in the user answer.'}}
        with self.assertRaisesRegex(StateDyneError,'visibly communicate'):
            validate_question_payoff(r,[{'group_id':'G1'}])

class NoveltyRoutingTests(unittest.TestCase):
    def test_fresh_independent_prediction_first_within_importance(self):
        ws=FakeWorkspace();ws.unknown('Q-A','system_map')
        ws.candidate('MZ','A nonreported consequence occurs in a different environment')
        ws.unknown('Q-Z','prediction',related=['MZ'])
        self.assertEqual([x['unknown_id'] for x in discovery_inquiries(ws)],['Q-Z','Q-A'])
    def test_blocking_overrides_novelty(self):
        ws=FakeWorkspace();ws.unknown('Q-A','system_map','blocking')
        ws.candidate('MZ','Distinct prediction beyond the existing model')
        ws.unknown('Q-Z','prediction','important',['MZ'])
        self.assertEqual([x['unknown_id'] for x in discovery_inquiries(ws)],['Q-A','Q-Z'])
    def test_uninvestigated_before_already_investigated_at_same_importance(self):
        ws=FakeWorkspace();ws.unknown('Q-A','system_map')
        ws.candidate('MB','Different predicted downstream result')
        ws.unknown('Q-B','reframe',related=['MB']);ws.state['investigated_unknowns']=['Q-B']
        self.assertEqual([x['unknown_id'] for x in discovery_inquiries(ws)],['Q-A','Q-B'])
    def test_no_candidate_is_not_fabricated(self):
        ws=FakeWorkspace();ws.unknown('Q-A','system_map')
        self.assertEqual([x['unknown_id'] for x in discovery_inquiries(ws)],['Q-A'])
    def test_stale_prediction_never_returns(self):
        ws=FakeWorkspace();ws.candidate('MA','Predicts difference but already addressed')
        ws.unknown('Q-A','prediction',related=['MA'],state='addressed')
        self.assertEqual(discovery_inquiries(ws),[])
    def test_priority_never_turns_into_forced_question_count(self):
        ws=FakeWorkspace()
        for i in range(23):ws.unknown(f'Q-{i:02d}','system_map')
        self.assertEqual(len(discovery_inquiries(ws)),23)

class ArtifactInvariantTests(unittest.TestCase):
    def test_version_consistency(self):
        import json
        released=json.loads((ROOT/'references/source-map.json').read_text('utf8'))['skill_version']
        self.assertEqual(__version__,released)
        self.assertIn('StateDyne '+released,(ROOT/'SKILL.md').read_text('utf8'))
    def test_method_and_archived_spec_unchanged(self):
        import hashlib
        m=hashlib.sha256((ROOT/'references/method.zh-CN.md').read_bytes()).hexdigest()
        s=hashlib.sha256((ROOT/'engineering/execution-spec-v3.7.zh-CN.md').read_bytes()).hexdigest()
        self.assertEqual(m,'fd2f4323daf95cc2c05f8e02b6daa98cec6184a34496be1ee82510fc46802f03')
        self.assertEqual(s,'0363d8df83d38ce1bed594c97a3493d24a4cac58f934df1a01872617b5b2eb45')

if __name__=='__main__': unittest.main()
