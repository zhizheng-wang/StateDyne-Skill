"""Cross-domain source-to-answer numeric checks, independently of creativity tasks.

Synthetic sources avoid hard-coding a prior personal, financial, or city case
into the actual skill's generative instructions. Examples recreate the known
failure *types* (unit scale, wrong official source year/geography) exactly.
"""
from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from sd_runtime.common import StateDyneError
from sd_runtime.numeric_provenance import (validate_numeric_sources,
    validate_numeric_source_review, check_declared_equity_identity, normalize, number_occurs)


def ledger(value='138600', source_value='138600', unit='USD/year', tier='registered_material'):
    return dict(local_id='L1', kind='sourced_fact', base_dimension='usd_per_year',
                population_and_scope='Four-person family median household, Example County',
                period='2026', visible_anchor=f'2026年中位收入 {value} {unit}',
                displayed_value=value, displayed_unit=unit, source_tier=tier,
                source_locator='src1', source_quote=f'Example County Median Income: ${int(source_value):,}',
                source_value=source_value, source_unit=unit,
                formula=source_value, absolute_tolerance_base='1', user_visible_limit='')


def ws(source='Example County Median Income: $138,600'):
    return SimpleNamespace(state={'sources':{'src1':{'active': True,'text':source}}})


def draft(fact):
    return {'answer':fact['visible_anchor']+'\n'+fact['user_visible_limit'],
            'numeric_source_checks':[fact]}


def review(fact):
    return {'verdict':'pass','source_fact_coverage_reason':'The decisive source datum, scope and unit were checked independently.',
            'numeric_source_reviews':[{'local_id':fact['local_id'], 'verdict':'verified_fact',
              'verified_source_locator':fact['source_locator'],
              'actual_source_measure':'Annual income of four-person households in Example County.',
              'original_unit_and_date':'USD/year; 2026.',
              'independent_unit_reconciliation':'Original USD/year equals published USD/year.',
              'consequence_if_wrong':'Income affordability thresholds change.',
              'independent_retrieval_receipt':'source-read-123'}]}


class NumericSourceTests(unittest.TestCase):
    def test_registered_primary_source_agrees(self):
        item=ledger();validate_numeric_sources(ws(),draft(item))
    def test_wrong_year_or_region_value_cannot_be_substituted(self):
        item=ledger(value='130900')
        with self.assertRaisesRegex(StateDyneError,'source-to-display|Original primary source'):
            validate_numeric_sources(ws(),draft(item))
    def test_original_primary_quote_must_exist(self):
        item=ledger()
        with self.assertRaisesRegex(StateDyneError,'actual active source text'):
            validate_numeric_sources(ws(source='Example County Median Income: $130,900'),draft(item))
    def test_source_quote_must_really_include_original_value(self):
        item=ledger();item['source_quote']='The official income limit was not published here.'
        with self.assertRaisesRegex(StateDyneError,'cannot be found'):
            validate_numeric_sources(ws(),draft(item))
    def test_sourced_fact_cannot_use_arbitrary_formula_to_override_source(self):
        item=ledger(value='130900');item['formula']='130900'
        with self.assertRaisesRegex(StateDyneError,'Original primary source'):
            validate_numeric_sources(ws(),draft(item))
    def test_unknown_source_unit_rejected(self):
        item=ledger();item['source_unit']='local currency as USD'
        with self.assertRaisesRegex(StateDyneError,'Unsupported numeric unit'):
            validate_numeric_sources(ws(),draft(item))
    def test_public_external_source_not_proven_by_url_alone(self):
        item=ledger(tier='retrieved_primary');item['source_locator']='https://example.org/original'
        validate_numeric_sources(ws(),draft(item))  # arithmetic only
        audit=review(item);audit['numeric_source_reviews'][0]['independent_retrieval_receipt']=''
        with self.assertRaisesRegex(StateDyneError,'independent actual retrieval'):
            validate_numeric_source_review(audit,draft(item))
        audit['numeric_source_reviews'][0]['independent_retrieval_receipt']='actual source retrieval ref'
        validate_numeric_source_review(audit,draft(item))
    def test_audit_cannot_pass_flagged_source_discrepancy(self):
        item=ledger();audit=review(item)
        audit['numeric_source_reviews'][0]['verdict']='needs_revision'
        with self.assertRaisesRegex(StateDyneError,'cannot pass'):
            validate_numeric_source_review(audit,draft(item))
        audit['verdict']='revise';validate_numeric_source_review(audit,draft(item))
    def test_audit_cannot_silently_omit_bearing_fact(self):
        item=ledger();audit=review(item)
        audit['numeric_source_reviews']=[]
        with self.assertRaisesRegex(StateDyneError,'every recorded'):
            validate_numeric_source_review(audit,draft(item))
    def test_assumptions_not_mislabeled_as_observations(self):
        item=ledger(tier='unverified_assumption')
        with self.assertRaisesRegex(StateDyneError,'Unverified assumptions'):
            validate_numeric_sources(ws(),draft(item))
        item['kind']='scenario';item['user_visible_limit']='This assumption has not been verified.'
        validate_numeric_sources(ws(),draft(item))
        audit=review(item)
        with self.assertRaisesRegex(StateDyneError,'not an independently verified fact'):
            validate_numeric_source_review(audit,draft(item))
        audit['numeric_source_reviews'][0]['verdict']='conditional_assumption'
        validate_numeric_source_review(audit,draft(item))
    def test_derived_equity_value_good_unit(self):
        f=ledger();f.update(kind='derived',base_dimension='usd',source_tier='derived_from_checked_inputs',
              visible_anchor='市值约 929.8 亿美元',displayed_value='929.8',displayed_unit='亿美元',
              formula='1834*50697000',absolute_tolerance_base='3000000', source_quote='',source_value='',source_unit='',
              source_locator='source a share price and verified dated share count',period='2026-10-16')
        validate_numeric_sources(ws(),draft(f))
    def test_derived_equity_value_wrong_billion_scale(self):
        f=ledger();f.update(kind='derived',base_dimension='usd',source_tier='derived_from_checked_inputs',
              visible_anchor='市值约 92.98 亿美元',displayed_value='92.98',displayed_unit='亿美元',
              formula='1834*50697000',absolute_tolerance_base='3000000', source_quote='',source_value='',source_unit='',
              source_locator='verified price and dated shares',period='2026-10-16')
        with self.assertRaisesRegex(StateDyneError,'unit or computation mismatch'):
            validate_numeric_sources(ws(),draft(f))
    def test_headline_tripwire_catches_missing_registry_10x_error(self):
        text='10月16日收盘价为$1,834；按最新披露的5,069.7万股计算，股权市值约$92.98亿。'
        with self.assertRaisesRegex(StateDyneError,'market capitalization'):
            check_declared_equity_identity(text)
    def test_correct_headline_tripwire_passes(self):
        text='10月16日收盘价为$1,834；按最新披露的5,069.7万股计算，股权市值约$929.8亿。'
        check_declared_equity_identity(text)
    def test_unrelated_share_counts_do_not_trigger_false_positive(self):
        check_declared_equity_identity('去年股价约$100，股数随后减少；今年市值约$3bn，仍需核实。')
    def test_writing_only_claims_do_not_need_fabricated_numbers(self):
        validate_numeric_sources(ws(),{'answer':'Qualitative mechanism only','numeric_source_checks':[]})
        validate_numeric_source_review({'verdict':'pass','numeric_source_reviews':[],
                                       'source_fact_coverage_reason':'This is a qualitative task.'},
                                       {'numeric_source_checks':[]})
    def test_unit_normalization(self):
        self.assertEqual(normalize('92.98','USD billion')[1],normalize('929.8','亿美元')[1])
        self.assertEqual(normalize('50.697','million shares')[1],normalize('5069.7','万股')[1])
    def test_quote_token_boundary(self):
        self.assertTrue(number_occurs('138600','Median Income $138,600.'))
        self.assertFalse(number_occurs('130900','Median Income $138,600.'))
    def test_all_quality_roles_get_numeric_source_check(self):
        from sd_runtime.engine import instructions
        for role in ('compose','audit','load_bearing','schedule','evidence_scout','environment_scout'):
            self.assertIn('源头先于计算', instructions(role))

if __name__=='__main__':unittest.main()
