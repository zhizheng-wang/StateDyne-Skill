"""11.2 structural contracts: visible intervention explanations and one skill across hosts.

These are synthetic negative tests and archive checks, not live-model evals.
"""
from __future__ import annotations
from pathlib import Path
import json
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sd_runtime import __version__
from sd_runtime.common import StateDyneError
from sd_runtime.delivery_quality import validate_delivery_quality
from build_release import assemble
import test_10220

class FullStrengthVisibleDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_10220.InterventionPhaseTests(methodName='test_combinations_use_real_points_and_text_anchors')
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def setup_claims(self, scope):
        return self.fixture.setup_claims(scope)

    def drafted(self, ws, scope):
        return self.fixture.drafted(ws, scope)

    def review(self, ws, draft):
        return self.fixture.review(ws, draft)

    def test_each_point_must_show_net_added_value_separately_from_leverage_and_rank(self):
        ws,_ = self.setup_claims('points')
        d=self.drafted(ws,'points');a=self.review(ws,d)
        validate_delivery_quality(ws,a,d)
        r=a['point_value_reviews'][0]
        # A hidden value review cannot substitute for the actual text.
        r['user_visible_value']='Secret audit-only value that the user never saw.'
        with self.assertRaisesRegex(StateDyneError, 'visible in this exact turn'):
            validate_delivery_quality(ws,a,d)
        # Reusing the rank sentence is likewise not an independent-value explanation.
        r['user_visible_value']=r['user_visible_priority']
        with self.assertRaisesRegex(StateDyneError, 'distinct visible explanations'):
            validate_delivery_quality(ws,a,d)

    def test_joint_point_cannot_be_approved_if_only_in_backend(self):
        ws,ids=self.setup_claims('points')
        d=self.drafted(ws,'points');a=self.review(ws,d)
        r=a['point_value_reviews'][0]
        r['combination_mode']='complement';r['companion_point_ids']=[ids['P2']]
        r['joint_value']='Only together do these two constraints allow the result.'
        with self.assertRaisesRegex(StateDyneError,'exact visible answer'):
            validate_delivery_quality(ws,a,d)
        joint='只有 P1 与 P2 在现实中同时形成瓶颈，联合改变才额外降低等待；否则优先单独处理实际瓶颈。'
        r['user_visible_combination']=joint
        d['answer']+='\n'+joint
        validate_delivery_quality(ws,a,d)

    def test_plan_combination_requires_a_visible_separate_sequence_and_incremental_gain(self):
        ws,ids=self.setup_claims('plan')
        d=self.drafted(ws,'plan');a=self.review(ws,d)
        validate_delivery_quality(ws,a,d)
        a['plan_combination_reviews']=[]
        with self.assertRaisesRegex(StateDyneError,'separate action-combination review'):
            validate_delivery_quality(ws,a,d)
        a=self.review(ws,d)
        r=a['plan_combination_reviews'][0]
        r['user_visible_comparison']='This is only in the backstage plan review.'
        with self.assertRaisesRegex(StateDyneError,'visible in the exact plan'):
            validate_delivery_quality(ws,a,d)
        r=a['plan_combination_reviews'][0]
        r['user_visible_comparison']=r['user_visible_composition']
        with self.assertRaisesRegex(StateDyneError,'distinct comparison'):
            validate_delivery_quality(ws,a,d)

    def test_plan_cannot_claim_a_joint_gain_with_one_action(self):
        ws,ids=self.setup_claims('plan')
        d=self.drafted(ws,'plan');a=self.review(ws,d)
        r=a['plan_combination_reviews'][0]
        r['action_claim_ids']=[ids['A1']]
        with self.assertRaisesRegex(StateDyneError,'dependencies'):
            validate_delivery_quality(ws,a,d)

class UniformEntryAndDistributionTests(unittest.TestCase):
    def test_universal_entry_references_required_full_strength_cognition(self):
        skill=(ROOT/'SKILL.md').read_text('utf8')
        yaml=(ROOT/'agents/openai.yaml').read_text('utf8')
        self.assertIn('普通 `@StateDyne`',skill)
        self.assertIn('没有“日常简化/深度专用”',skill)
        self.assertIn('单点',skill)
        self.assertIn('联合',skill)
        self.assertIn('同一最高认知标准',yaml)
        self.assertIn('只要能调用就实际派发',yaml)
        self.assertNotIn('10.31.0',yaml)
        self.assertEqual(__version__,'0.1.0')

    def test_all_install_and_source_distributions_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            archives=assemble(ROOT,Path(folder))
            with zipfile.ZipFile(archives['Plugin']) as plugin, zipfile.ZipFile(archives['Install']) as install, zipfile.ZipFile(archives['Agent-Skill']) as agent, zipfile.ZipFile(archives['GitHub-Ready']) as github:
                manifest=json.loads(plugin.read('plugin.json'))
                self.assertEqual(manifest['name'],'statedyne')
                self.assertEqual(manifest['version'],__version__)
                self.assertEqual(manifest['$schema'],'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json')
                self.assertEqual([x for x in plugin.namelist() if x.lower().endswith('/skill.md')],['skills/statedyne/SKILL.md'])
                self.assertEqual([x for x in agent.namelist() if x.lower().endswith('/skill.md')],['statedyne/SKILL.md'])
                self.assertEqual({x.split('/',1)[0] for x in agent.namelist()},{'statedyne'})
                for rel in ('SKILL.md','agents/openai.yaml','references/intervention-leverage.md','references/operators/audit.md','scripts/sd_runtime/delivery_quality.py'):
                    content=(ROOT/rel).read_bytes()
                    self.assertEqual(content,install.read(rel))
                    self.assertEqual(content,agent.read('statedyne/'+rel))
                    self.assertEqual(content,plugin.read('skills/statedyne/'+rel))
                    self.assertEqual(content,github.read('statedyne/'+rel))

if __name__=='__main__': unittest.main()
