#!/usr/bin/env python3
"""Small, local StateDyne record keeper. It never performs external actions."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:
    fcntl = None


KINDS = {"fact", "source", "inference", "calculation", "candidate", "adopted",
         "action", "result", "obligation", "unknown", "goal", "constraint"}
USES = {"working", "exploration", "support"}
STATUSES = {"active", "stale", "invalid"}
ACTION_STATES = {"proposed", "authorized", "initiated", "tool_confirmed",
                 "observed", "failed", "cancelled"}
TRANSITIONS = {
    "proposed": {"authorized", "cancelled"},
    "authorized": {"initiated", "cancelled"},
    "initiated": {"tool_confirmed", "observed", "failed", "cancelled"},
    "tool_confirmed": {"observed", "failed", "cancelled"},
    "observed": set(), "failed": set(), "cancelled": set(),
}
IDENTIFIER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]*\Z")


class StateError(Exception):
    pass


def need(condition, message):
    if not condition:
        raise StateError(message)


def integer(value, minimum=1):
    return type(value) is int and value >= minimum


def string(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value):
    return isinstance(value, list) and all(string(x) for x in value)


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def fields(data, allowed, required=()):
    need(isinstance(data, dict), "expected a JSON object")
    need(set(data) <= set(allowed), "unknown fields: " + ", ".join(sorted(set(data) - set(allowed))))
    need(set(required) <= set(data), "missing fields: " + ", ".join(sorted(set(required) - set(data))))


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(stream):
    def bad_constant(value):
        raise StateError("non-finite JSON number: " + value)
    return json.load(stream, object_pairs_hook=no_duplicates, parse_constant=bad_constant)


def external_path(state_path, value):
    need(string(value), "file path must be a nonempty string")
    path = Path(value).expanduser()
    return path if path.is_absolute() else state_path.parent / path


def digest(path):
    need(path.is_file(), "not a readable regular file: " + str(path))
    with path.open("rb") as handle:
        result = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
        return result.hexdigest()


@contextmanager
def locked(path, timeout):
    need(fcntl is not None, "this CLI requires POSIX flock (Linux/macOS)")
    need(path.parent.is_dir(), "state directory does not exist: " + str(path.parent))
    # Never unlink this file: waiters must keep locking the same inode.
    with path.with_name(path.name + ".lock").open("a+b") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                need(time.monotonic() < deadline, "state lock busy; no write performed")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_save(path, state):
    temporary = None
    replaced = False
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name + ".", suffix=".tmp",
                                         delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(state, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        replaced = True
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        if replaced:
            raise StateError("state was replaced but directory sync failed; reread state before retry: " + str(error)) from error
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def task_valid(task):
    fields(task, {"request", "goal", "constraints", "revision"}, {"request", "goal", "constraints"})
    need(string(task["request"]) and string(task["goal"]), "request and goal must be nonempty")
    need(strings(task["constraints"]), "constraints must be a list of nonempty strings")
    if "revision" in task:
        need(integer(task["revision"]), "bad task revision")


def refs_valid(refs):
    need(isinstance(refs, dict), "dependencies must map IDs to consumed revisions")
    for key, version in refs.items():
        need((key == "@task" or identifier(key)) and integer(version), "bad dependency reference")


def node_refs(item):
    """Both premise and subject changes require recomputation; only premises support truth."""
    premises = item.get("depends_on")
    subjects = item.get("recompute_on", {})  # Existing schema-1 records need no migration.
    refs_valid(premises)
    refs_valid(subjects)
    need(all(key not in premises or premises[key] == version for key, version in subjects.items()),
         "conflicting versions across depends_on and recompute_on")
    return {**premises, **subjects}


def ref_value(state, key):
    if key == "@task":
        return state["task"]["revision"], "active"
    need(key in state["nodes"], "missing dependency: " + key)
    item = state["nodes"][key]
    return item["revision"], item["status"]


def fresh_refs(state, refs, require_active=True):
    refs_valid(refs)
    for key, expected in refs.items():
        version, status = ref_value(state, key)
        need(version == expected, f"outdated dependency {key}: expected {expected}, current {version}")
        need(not require_active or status == "active", f"dependency {key} is {status}")


def acyclic(nodes):
    # Iterative DFS also handles graphs longer than Python's recursion limit.
    visited, visiting = set(), set()
    for root in nodes:
        if root in visited:
            continue
        stack = [(root, False)]
        while stack:
            key, leaving = stack.pop()
            if leaving:
                visiting.remove(key)
                visited.add(key)
                continue
            need(key not in visiting, "dependency cycle at " + key)
            if key in visited:
                continue
            visiting.add(key)
            stack.append((key, True))
            for parent in node_refs(nodes[key]):
                if parent != "@task":
                    need(parent in nodes, "missing dependency: " + parent)
                    stack.append((parent, False))


def support_valid(state):
    # Subject references track what is being tested or conditionally examined,
    # not propositions adopted as true; do not traverse them as support.
    for root, node in state["nodes"].items():
        if node["use"] != "support" or node["status"] != "active":
            continue
        queue, seen = list(node["depends_on"]), set()
        while queue:
            key = queue.pop()
            if key == "@task" or key in seen:
                continue
            seen.add(key)
            parent = state["nodes"][key]
            need(parent["kind"] != "candidate" and parent["use"] != "exploration",
                 f"support {root} depends on exploratory {key}; keep the result exploratory or supply qualified evidence")
            queue.extend(parent["depends_on"])


def validate(state):
    need(isinstance(state, dict) and type(state.get("schema_version")) is int and state["schema_version"] == 1, "unsupported state schema")
    need(integer(state.get("revision")), "bad state revision")
    task_valid(state.get("original_task"))
    task_valid(state.get("task"))
    need(integer(state["task"].get("revision")), "missing task revision")
    nodes = state.get("nodes")
    need(isinstance(nodes, dict), "nodes must be an object")
    for key, item in nodes.items():
        need(identifier(key) and isinstance(item, dict) and item.get("id") == key, "bad node ID")
        need(integer(item.get("revision")) and item.get("kind") in KINDS, "bad node revision or kind")
        need(string(item.get("body")) and item.get("status") in STATUSES, "bad node body or status")
        need(item.get("use") in USES and type(item.get("central")) is bool, "bad node use or central flag")
        need(strings(item.get("basis")), "basis must be a list of source/justification records")
        node_refs(item)
        need(item["use"] != "support" or item["basis"] or item["depends_on"], "support needs declared basis or dependencies")
        need(item["kind"] != "candidate" or item["use"] == "exploration", "candidate must remain exploration")
        need(item["kind"] != "adopted" or item["use"] == "support", "adopted must declare support")
        need(isinstance(item.get("artifacts"), list), "artifacts must be a list")
        for artifact in item["artifacts"]:
            need(isinstance(artifact, dict) and string(artifact.get("path")) and string(artifact.get("visible_at")), "artifact needs path and visible_at")
            need(isinstance(artifact.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]), "bad artifact hash")
    acyclic(nodes)
    for item in nodes.values():
        for key, version in node_refs(item).items():
            need(version <= ref_value(state, key)[0], "dependency references a future revision: " + key)
        if item["status"] == "active":
            fresh_refs(state, node_refs(item))
    support_valid(state)
    archive = state.get("archive")
    need(isinstance(archive, dict) and isinstance(archive.get("task"), list)
         and isinstance(archive.get("nodes"), dict), "bad revision archive")
    task_versions = set()
    for old in archive["task"]:
        task_valid(old)
        version = old.get("revision")
        need(integer(version) and version < state["task"]["revision"] and version not in task_versions, "bad archived task revision")
        task_versions.add(version)
    for key, versions in archive["nodes"].items():
        need(key in nodes and isinstance(versions, list), "bad archived node ID")
        seen = set()
        for old in versions:
            need(isinstance(old, dict) and old.get("id") == key and string(old.get("body")), "bad archived node")
            version = old.get("revision")
            need(integer(version) and version < nodes[key]["revision"] and version not in seen, "bad archived node revision")
            node_refs(old)
            seen.add(version)
    impact = state.get("impact")
    need(isinstance(impact, dict) and type(impact.get("pending")) is bool, "bad impact state")
    need(isinstance(impact.get("events"), list) and isinstance(impact.get("reviews"), list), "bad impact records")
    actions = state.get("actions")
    need(isinstance(actions, dict), "actions must be an object")
    keys = set()
    for key, item in actions.items():
        need(identifier(key) and isinstance(item, dict) and item.get("id") == key, "bad action ID")
        need(integer(item.get("revision")) and item.get("status") in ACTION_STATES, "bad action revision or status")
        need(string(item.get("body")) and string(item.get("idempotency_key")), "bad action body or idempotency key")
        need(item["idempotency_key"] not in keys, "duplicate idempotency key")
        keys.add(item["idempotency_key"])
        need(isinstance(item.get("authorization"), str), "bad authorization record")
        need(item["status"] in {"proposed", "cancelled"} or string(item["authorization"]), "action lacks recorded authorization")
        need(type(item.get("needs_reconciliation")) is bool and isinstance(item.get("history"), list), "bad action history")
        refs_valid(item.get("depends_on"))
        for parent, version in item["depends_on"].items():
            need(version <= ref_value(state, parent)[0], "action references a future dependency revision: " + parent)


def load_state(path):
    need(path.is_file(), "state does not exist; use init")
    with path.open(encoding="utf-8") as handle:
        state = read_json(handle)
    validate(state)
    return state


def archive_node(state, key):
    state["archive"]["nodes"].setdefault(key, []).append(copy.deepcopy(state["nodes"][key]))


def stale_downstream(state, changed):
    reverse = {}
    for key, item in state["nodes"].items():
        for parent in node_refs(item):
            reverse.setdefault(parent, []).append(key)
    queue, seen, marked = [changed], {changed}, []
    while queue:
        parent = queue.pop()
        for key in reverse.get(parent, []):
            if key in seen:
                continue
            seen.add(key)
            queue.append(key)
            item = state["nodes"][key]
            if item["status"] == "active":
                archive_node(state, key)
                item["status"] = "stale"
                item["revision"] += 1
                item["stale_because"] = changed
                marked.append(key)
    return sorted(marked)


def flag_impact(state, reason, affected_nodes):
    state["impact"]["pending"] = True
    state["impact"]["events"].append({"state_revision": state["revision"] + 1,
                                      "reason": reason, "affected_nodes": sorted(set(affected_nodes)), "at": now()})


def expected_item(data, existing):
    expected = data.get("expected_revision")
    need(integer(expected, 0), "expected_revision must be 0 for new records, or the current record revision")
    actual = existing["revision"] if existing else 0
    need(expected == actual, f"record revision conflict: expected {expected}, current {actual}")
    return actual + 1


def put_node(state, data, path):
    fields(data, {"id", "expected_revision", "kind", "body", "use", "central", "depends_on", "recompute_on", "basis", "artifacts"},
           {"id", "expected_revision", "kind", "body"})
    key = data["id"]
    need(identifier(key), "bad node ID")
    old = state["nodes"].get(key)
    item = {"id": key, "revision": expected_item(data, old), "kind": data["kind"],
            "body": data["body"], "use": data.get("use", "exploration" if data["kind"] == "candidate" else "support" if data["kind"] == "adopted" else "working"),
            "central": data.get("central", old["central"] if old else False), "status": "active",
            "depends_on": data.get("depends_on", {}), "recompute_on": data.get("recompute_on", {}),
            "basis": data.get("basis", []), "artifacts": []}
    dependencies = node_refs(item)
    proposed = dict(state["nodes"])
    proposed[key] = item
    acyclic(proposed)
    fresh_refs(state, dependencies)
    artifacts = data.get("artifacts", [])
    need(isinstance(artifacts, list), "artifacts must be a list")
    for artifact in artifacts:
        fields(artifact, {"path", "visible_at"}, {"path", "visible_at"})
        need(string(artifact["visible_at"]), "artifact requires a recorded visible location")
        item["artifacts"].append({**artifact, "sha256": digest(external_path(path, artifact["path"]))})
    if old:
        archive_node(state, key)
    state["nodes"][key] = item
    marked = stale_downstream(state, key) if old else []
    if item["central"] or (old and old["central"]):
        flag_impact(state, "central node written: " + key, [key, *marked])
    return {"node_revision": item["revision"], "stale": marked}


def invalidate(state, data):
    fields(data, {"id", "expected_revision", "reason"}, {"id", "expected_revision", "reason"})
    need(identifier(data["id"]) and data["id"] in state["nodes"], "node does not exist")
    need(string(data["reason"]), "invalidation requires a reason")
    item = state["nodes"][data["id"]]
    revision = expected_item(data, item)
    archive_node(state, item["id"])
    item["revision"] = revision
    item["status"] = "invalid"
    item["invalid_reason"] = data["reason"]
    marked = stale_downstream(state, item["id"])
    if item["central"]:
        flag_impact(state, "central node invalidated: " + item["id"], [item["id"], *marked])
    return {"node_revision": item["revision"], "stale": marked}


def review_impact(state, data):
    fields(data, {"scope", "findings", "checked_nodes", "unresolved"}, {"scope", "findings", "checked_nodes", "unresolved"})
    need(string(data["scope"]) and string(data["findings"]) and strings(data["unresolved"]), "record scope, findings and unresolved items")
    fresh_refs(state, data["checked_nodes"], require_active=False)
    if state["impact"]["pending"]:
        # Cover every event since the most recent fully resolved review.
        # Legacy events lack explicit scope: conservatively cover all nodes.
        resolved_through = max((review.get("through_state_revision", 0)
                                for review in state["impact"]["reviews"]
                                if not review.get("unresolved")), default=0)
        required = set()
        for event in state["impact"]["events"]:
            if event.get("state_revision", 0) > resolved_through:
                required.update(event.get("affected_nodes", ["@task", *state["nodes"]]))
        need(bool(data["checked_nodes"]), "pending impact requires nonempty current-version coverage")
        need(required <= set(data["checked_nodes"]),
             "impact review omits affected nodes: " + ", ".join(sorted(required - set(data["checked_nodes"]))))
    state["impact"]["reviews"].append({**data, "through_state_revision": state["revision"], "at": now()})
    state["impact"]["pending"] = bool(data["unresolved"])
    return {"impact_pending": state["impact"]["pending"], "review_is_a_record_not_verification": True}


def put_action(state, data):
    fields(data, {"id", "expected_revision", "idempotency_key", "body", "depends_on", "status", "authorization"},
           {"id", "expected_revision", "idempotency_key", "body"})
    key = data["id"]
    need(identifier(key), "bad action ID")
    old = state["actions"].get(key)
    revision = expected_item(data, old)
    need(old is None or old["status"] in {"proposed", "authorized"}, "launched/terminal action cannot be rewritten")
    need(old is None or data["idempotency_key"] == old["idempotency_key"], "idempotency key is immutable")
    for other_key, other in state["actions"].items():
        need(other_key == key or other["idempotency_key"] != data["idempotency_key"], "idempotency key already registered: " + other_key)
    status = data.get("status", "proposed")
    need(status in {"proposed", "authorized"}, "new/revised action must be proposed or authorized")
    deps = data.get("depends_on", {})
    fresh_refs(state, deps)
    item = {"id": key, "revision": revision, "idempotency_key": data["idempotency_key"],
            "body": data["body"], "depends_on": deps, "status": status,
            "authorization": data.get("authorization", ""), "needs_reconciliation": False,
            "history": copy.deepcopy(old["history"]) if old else []}
    item["history"].append({"at": now(), "revision": revision, "status": status, "note": "record created/revised",
                            "body": item["body"], "depends_on": deps,
                            "authorization": item["authorization"]})
    state["actions"][key] = item
    return {"action_revision": revision, "status": status}


def advance_action(state, data):
    fields(data, {"id", "expected_revision", "status", "note", "authorization", "reconciliation"},
           {"id", "expected_revision", "status", "note"})
    need(identifier(data["id"]) and data["id"] in state["actions"], "action does not exist")
    item = state["actions"][data["id"]]
    revision = expected_item(data, item)
    target = data["status"]
    need(target in TRANSITIONS[item["status"]], "invalid/repeated action transition")
    need(string(data["note"]), "transition needs an actual authorization/tool/observation record")
    if target in {"authorized", "initiated"}:
        fresh_refs(state, item["depends_on"])
    if "authorization" in data:
        need(target == "authorized" and string(data["authorization"]), "authorization can be recorded when authorizing")
        item["authorization"] = data["authorization"]
    if item["needs_reconciliation"]:
        need(string(data.get("reconciliation")), "recovery requires an external-state reconciliation record")
    elif "reconciliation" in data:
        need(string(data["reconciliation"]), "reconciliation record must be nonempty")
    item["status"], item["revision"] = target, revision
    item["needs_reconciliation"] = False
    item["history"].append({**data, "at": now(), "revision": revision})
    return {"action_revision": revision, "status": target}


def recover(state):
    pending = []
    for key, item in state["actions"].items():
        if item["status"] in {"initiated", "tool_confirmed"}:
            pending.append(key)
            if not item["needs_reconciliation"]:
                item["needs_reconciliation"] = True
                item["revision"] += 1
                item["history"].append({"at": now(), "revision": item["revision"], "status": item["status"],
                                        "note": "recovery: external state must be checked before recording outcome"})
    return {"reconciliation_pending": sorted(pending), "external_actions_performed": 0}


def check(state, path):
    errors, warnings = [], []
    if state["impact"]["pending"]:
        errors.append("global impact review is pending (declared graph may omit relationships)")
    for key, item in state["nodes"].items():
        if item["status"] == "stale":
            destination = errors if item["use"] == "support" or item["kind"] == "obligation" else warnings
            destination.append("stale node: " + key)
        if item["kind"] == "obligation" and item["status"] != "invalid" and not item["artifacts"]:
            errors.append("obligation has no linked output file/visible location: " + key)
        for artifact in item["artifacts"]:
            try:
                actual = digest(external_path(path, artifact["path"]))
                if actual != artifact["sha256"]:
                    errors.append("artifact hash changed: " + key + " / " + artifact["path"])
            except (StateError, OSError) as error:
                errors.append(str(error))
    for key, item in state["actions"].items():
        if item["status"] in {"initiated", "tool_confirmed"} or item["needs_reconciliation"]:
            errors.append("external action outcome needs checking: " + key)
        if item["status"] in {"proposed", "authorized"}:
            try:
                fresh_refs(state, item["depends_on"])
            except StateError as error:
                errors.append("action " + key + ": " + str(error))
    return {"ok": not errors, "state_revision": state["revision"],
            "scope": "record structure, declared revisions, file identity and recorded visible locations only",
            "semantic_sufficiency": "not_checked", "delivery_or_authorization_authenticity": "not_checked",
            "declared_dependency_truth_or_recomputation": "not_checked",
            "errors": errors, "warnings": warnings}


def run(args):
    path = Path(args.state).expanduser().resolve()
    with locked(path, args.lock_timeout):
        if args.command in {"show", "check"}:
            state = load_state(path)
            result = state if args.command == "show" else check(state, path)
            return result, 0 if args.command == "show" or result["ok"] else 1
        need(args.command == "init" or integer(args.expect_revision, 1), "--expect-revision must be a positive integer")
        data = None
        if args.command != "recover":
            if args.data == "-":
                data = read_json(sys.stdin)
            else:
                with external_path(path, args.data).open(encoding="utf-8") as handle:
                    data = read_json(handle)
        if args.command == "init":
            need(not path.exists(), "state already exists; init will not overwrite")
            fields(data, {"request", "goal", "constraints"}, {"request", "goal", "constraints"})
            task_valid(data)
            stamp = now()
            state = {"schema_version": 1, "revision": 1, "created_at": stamp, "updated_at": stamp,
                     "original_task": copy.deepcopy(data), "task": {**data, "revision": 1},
                     "nodes": {}, "actions": {}, "archive": {"task": [], "nodes": {}},
                     "impact": {"pending": False, "events": [], "reviews": []}}
            result = {}
        else:
            state = load_state(path)
            need(state["revision"] == args.expect_revision,
                 f"state revision conflict: expected {args.expect_revision}, current {state['revision']}; reread and retry only still-valid work")
            if args.command == "put":
                result = put_node(state, data, path)
            elif args.command == "invalidate":
                result = invalidate(state, data)
            elif args.command == "task":
                fields(data, {"request", "goal", "constraints"}, {"request", "goal", "constraints"})
                task_valid(data)
                state["archive"]["task"].append(copy.deepcopy(state["task"]))
                state["task"] = {**data, "revision": state["task"]["revision"] + 1}
                result = {"task_revision": state["task"]["revision"], "stale": stale_downstream(state, "@task")}
                flag_impact(state, "current task/goal/constraints changed; original task preserved", ["@task", *state["nodes"]])
            elif args.command == "review-impact":
                result = review_impact(state, data)
            elif args.command == "action":
                result = put_action(state, data)
            elif args.command == "advance":
                result = advance_action(state, data)
            else:
                result = recover(state)
            state["revision"] += 1
            state["updated_at"] = now()
        validate(state)
        atomic_save(path, state)
        return {"ok": True, "state_revision": state["revision"], **result}, 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="state JSON path; all other relative file paths use its directory")
    parser.add_argument("--lock-timeout", type=float, default=5.0, help="local lock wait in seconds (default: 5)")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "show", "check", "put", "invalidate", "task", "review-impact", "action", "advance", "recover"):
        child = commands.add_parser(command)
        if command not in {"init", "show", "check"}:
            child.add_argument("--expect-revision", required=True, type=int)
        if command not in {"show", "check", "recover"}:
            child.add_argument("--data", default="-", help="JSON file relative to state directory, or - for stdin")
    args = parser.parse_args()
    try:
        need(0 <= args.lock_timeout <= 60, "lock timeout must be between 0 and 60 seconds")
        result, code = run(args)
    except (StateError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
