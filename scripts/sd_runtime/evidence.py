"""Explicitly registered read-only materials and a bounded arithmetic evaluator.

No shell execution, arbitrary Python eval, network fetch, or access to unlisted files.
"""
from __future__ import annotations
import ast
import math
import operator
import re
from .common import StateDyneError
from .schemas import obj, S, I

TOOL_DEFINITIONS = [
    {"type": "function", "name": "list_materials", "description": "List explicitly registered source IDs and labels; no file system access.", "strict": True, "parameters": obj()},
    {"type": "function", "name": "read_material", "description": "Read a registered source by ID, using zero-based character offset. Returns actual source text and truncation status.", "strict": True, "parameters": obj(source_id=S, start=I, length=I)},
    {"type": "function", "name": "search_materials", "description": "Literal case-insensitive search in registered materials. Returns source passages, not a semantic or Internet search.", "strict": True, "parameters": obj(query=S)},
    {"type": "function", "name": "calculate", "description": "Bounded arithmetic only: numbers, + - * / // % ** and parentheses. No code execution.", "strict": True, "parameters": obj(expression=S)},
]


def calculate(expression: str):
    if not isinstance(expression, str) or len(expression) > 300:
        raise StateDyneError("Arithmetic expression too long")
    try:
        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 60:
            raise StateDyneError("Arithmetic tree too large")
        binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                  ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
                  ast.Pow: operator.pow}
        def walk(node):
            if isinstance(node, ast.Expression):
                return walk(node.body)
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                val = node.value
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                val = walk(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            elif isinstance(node, ast.BinOp) and type(node.op) in binary:
                a, b = walk(node.left), walk(node.right)
                if isinstance(node.op, ast.Pow) and (abs(b) > 20 or abs(a) > 1e12):
                    raise StateDyneError("Exponent exceeds safe arithmetic budget")
                val = binary[type(node.op)](a, b)
            else:
                raise StateDyneError("Only bounded arithmetic is allowed")
            if type(val) not in (int, float) or not math.isfinite(val) or abs(val) > 1e100:
                raise StateDyneError("Arithmetic result outside bounds")
            return val
        return {"expression": expression, "result": walk(tree),
                "limit": "A conditional calculation does not validate its assumptions."}
    except (SyntaxError, ZeroDivisionError, OverflowError, ValueError, TypeError) as exc:
        raise StateDyneError(f"Invalid arithmetic: {exc}") from exc


class EvidenceTools:
    def __init__(self, sources: dict):
        self.sources = sources
        self.seen: dict[str, list[str]] = {}
        self.receipts: list[dict] = []

    def _expose(self, sid: str, text: str):
        self.seen.setdefault(sid, []).append(text)

    def call(self, name: str, args: dict) -> dict:
        try:
            if name == "list_materials":
                out = {"materials": [{k: v for k, v in s.items() if k != "text"}
                                      for s in self.sources.values() if s["active"]]}
            elif name == "read_material":
                sid = args["source_id"]
                if sid not in self.sources or not self.sources[sid]["active"]:
                    raise StateDyneError("Unknown or superseded source")
                start, length = args["start"], args["length"]
                if type(start) is not int or type(length) is not int or start < 0 or not 1 <= length <= 20000:
                    raise StateDyneError("start >= 0 and 1 <= length <= 20000 required")
                source = self.sources[sid]
                text = source["text"][start:start + length]
                self._expose(sid, text)
                out = {"source_id": sid, "start": start, "text": text,
                       "next_start": start + len(text), "truncated": start + length < len(source["text"]),
                       "source_status": source["kind"], "precision": source["precision"]}
            elif name == "search_materials":
                query = args["query"]
                if not isinstance(query, str) or not query.strip() or len(query) > 300:
                    raise StateDyneError("A nonempty literal query of at most 300 characters is required")
                matches = []
                has_more = False
                for sid, source in self.sources.items():
                    if not source["active"]:
                        continue
                    for match in re.finditer(re.escape(query), source["text"], re.IGNORECASE):
                        if len(matches) >= 20:
                            has_more = True
                            break
                        start = max(0, match.start() - 160)
                        text = source["text"][start:match.end() + 280]
                        self._expose(sid, text)
                        matches.append({"source_id": sid, "start": start, "text": text})
                out = {"matches": matches, "truncated": has_more, "search_type": "literal_local"}
            elif name == "calculate":
                out = calculate(args["expression"])
            else:
                raise StateDyneError("Tool is not allowlisted")
        except (KeyError, StateDyneError, TypeError) as exc:
            out = {"error": str(exc)}
        self.receipts.append({"tool": name, "arguments": args, "result": out})
        return out
