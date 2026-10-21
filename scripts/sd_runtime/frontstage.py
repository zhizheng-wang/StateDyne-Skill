"""Minimum interface discipline; semantic plain-language quality needs a reviewer.

Never mechanically replace the meaning of the model. Reject only demonstrable
internal protocol leaks in ordinary nontechnical answers; allow real code
review questions to quote technical identifiers literally.
"""
from __future__ import annotations
import re
from .common import StateDyneError

_INTERNAL = re.compile(r"\b(?:worker_ref|model_gap|probe_portfolio|delivery_units|entry_review|scope_intent|claim_ids|load_bearing_audit|recognition_prompt)\b")
# Conservative heading-only protection: exact scope has already been checked
# against registered delivery units. The independent reviewer still owns prose
# semantics, which a keyword filter cannot certify. No domain names here.
_FUTURE_ACTION_HEADER = re.compile(
    r"(?m)^\s*#{1,6}\s*(?:具体动作|执行动作|操作步骤|练习安排|实施步骤|行动方案|执行安排|行动计划)(?:\s|$|[：:])")
_FUTURE_PLAN_HEADER = re.compile(
    r"(?m)^\s*#{1,6}\s*(?:完整实施方案|实施时间表|阶段实施计划|完整行动方案)(?:\s|$|[：:])")
_UNTRANSLATED_META = re.compile(r"(?:更节约且更贴合原话的解释|模型外预测|候选机制晋级|后台字段审核)")
# A table that duplicates internal intervention-review columns is generally
# worse than connected explanations. This guard is scoped to intervention
# delivery; quantitative/research tables in analysis remain allowed.
_INTERVENTION_MATRIX = re.compile(r"(?m)^\s*\|\s*(?:排名|干预点|干预位置|可改变位置|具体动作|旧传导|新传导|目标传导)\s*\|")
_REQUESTS_TABLE = re.compile(r"(?:请用表格|用表格展示|做一个表格|对照表|comparison table|as a table)", re.I)
_REJECTS_TABLE = re.compile(r"(?:不要|不用|避免|别用|不需要).{0,6}(?:表格|对照表)")
_TECH_INTENT = re.compile(r"(?:源码|代码|程序|架构审计|技能审计|JSON|API|Python|CLI|调度器|协议字段|schema|source code|implementation|debug)", re.I)


def validate_frontstage(ws, draft):
    requested = " ".join(src['text'] for src in ws.raw_view()['task_sources'])
    technical = bool(_TECH_INTENT.search(requested))
    if not technical and (_INTERNAL.search(draft['answer']) or _UNTRANSLATED_META.search(draft['answer'])):
        raise StateDyneError('User-facing answer leaked internal analysis language; explain the concrete meaning instead')
    requested_table = bool(_REQUESTS_TABLE.search(requested) and not _REJECTS_TABLE.search(requested))
    scope = ws.state.get('delivery_scope', ws.state.get('scope', 'analysis'))
    if scope == 'auto':
        scope = 'analysis'
    if not technical and not requested_table and scope in ('points', 'actions') and _INTERVENTION_MATRIX.search(draft['answer']):
        raise StateDyneError('Explain intervention leverage and actions in causal prose, not a backend audit matrix')
    # Only high-confidence section headings are blocked here. Inline examples
    # and nuanced discussion require independent model review, not regex.
    if not technical and scope in ('analysis', 'points') and _FUTURE_ACTION_HEADER.search(draft['answer']):
        raise StateDyneError('Current stage jumped to unrequested action instructions')
    if not technical and scope in ('analysis', 'points', 'actions') and _FUTURE_PLAN_HEADER.search(draft['answer']):
        raise StateDyneError('Current stage jumped to an unrequested execution plan')
