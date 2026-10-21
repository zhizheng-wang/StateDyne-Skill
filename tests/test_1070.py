"""10.7 unified-quality skill contract regression tests.

Static/protocol tests, not evidence of real language-model reasoning accuracy.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from sd_runtime import __version__
from sd_runtime.store import Workspace
from sd_runtime.cli import parser


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


class UnifiedQualityContractTests(unittest.TestCase):
    def test_skill_is_single_uniform_cognitive_standard(self):
        entry = read('SKILL.md')
        self.assertIn('只有**一个认知标准、一条接续逻辑**', entry)
        self.assertIn('不决定启用“强/弱模式”', entry)
        self.assertIn('便携模式下也执行同一认知契约', entry)
        self.assertIn('不是一个必须另外安装', entry)
        self.assertIn('不设问题', read('references/portable-discovery.md'))
        self.assertNotIn('简单任务保持简洁', entry)

    def test_all_hosts_share_discovery_obligations(self):
        guide = read('references/portable-discovery.md')
        runtime = read('references/runtime.md')
        self.assertIn('所有调用的同一质量标准', guide)
        self.assertIn('开放问题均默认使用完整认知能力', runtime)
        for token in ('尚未被报告', '重建', '独立', '证据'):
            self.assertIn(token, guide)
        self.assertIn('没有真实独立工作者', runtime)
        self.assertIn('模型里', runtime)

    def test_no_hard_question_count_or_agent_tier(self):
        entry = read('SKILL.md')
        self.assertIn('绝无固定问数、候选数、发现轮数、干预点数或创新数上限', entry)
        self.assertIn('同一最高认知标准', read('agents/openai.yaml'))
        self.assertIn('用户明确要求一轮完成', entry)

    def test_agent_is_optional_actual_tool_not_an_unlock(self):
        entry = read('SKILL.md')
        self.assertIn('拥有运行条件时应优先使用的执行工具', entry)
        self.assertIn('不声称调用过没有发生的多智能体', entry)
        self.assertIn('工具适配器', read('references/runtime.md'))
        self.assertEqual(__version__, '11.3.0')

    def test_intervention_work_has_distinct_scope_and_continuation(self):
        entry = read('SKILL.md')
        self.assertIn('干预点', entry)
        self.assertIn('动作', entry)
        self.assertIn('方案', entry)
        self.assertIn('下一步', entry)
        self.assertIn('相对排序', read('references/dialogue.md'))
        self.assertIn('只重开受影响的关系', read('references/runtime.md'))

    def test_optional_runner_retains_real_concurrency_and_native_safety(self):
        args = parser().parse_args(['start', '--task-file', 'a.txt', '--workdir', 'run'])
        self.assertEqual(args.parallel_workers, 12)
        self.assertEqual(args.max_parallel_operations, 12)
        self.assertFalse(args.allow_api)
        self.assertFalse(args.web_search)
        self.assertIsNone(args.max_question_characters)

    def test_workspace_version_is_not_reused_from_10_6(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Workspace.create(Path(d) / 'run', 'Explain a surprising observed process')
            self.assertEqual(ws.state['skill_version'], '11.3.0')

    def test_method_and_engineering_source_identities_remain_unchanged(self):
        manifest = json.loads(read('references/source-map.json'))
        import hashlib
        for name in ('method', 'engineering'):
            info = manifest[name]
            got = hashlib.sha256((ROOT / info['path']).read_bytes()).hexdigest()
            self.assertEqual(got, info['sha256'])


if __name__ == '__main__':
    unittest.main()
