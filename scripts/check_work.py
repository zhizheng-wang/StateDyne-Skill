#!/usr/bin/env python3
"""Bind StateDyne reviews to exact local file versions (standard library only).

snapshot creates, but never overwrites, a target with schema, phase, scope,
inputs, and digest. Each input is {path, sha256, bytes}; paths are resolved
absolute paths. Required quality inputs are task, work, independent. Final
targets additionally require draft, quality_target, quality_review. Other
named inputs are allowed and are checked too. A final target must preserve the
exact path, hash, and byte count of every alias shared with its quality target.
Quality-only inputs remain recursively checked; final-only inputs are allowed.

The digest is SHA-256 of the entire target except its digest member, encoded
as UTF-8 JSON using ensure_ascii=False, sort_keys=True, separators=(',', ':'),
and allow_nan=False. There is no trailing newline in those canonical bytes.
The on-disk JSON may be pretty-printed without changing this digest.

check validates structure and file versions, not semantic quality, actual
independence, or reviewer identity. It is not a host-enforced delivery gate.
Files can change after a check. Review content and real collaboration traces
still need substantive inspection. Self-review uses reviewer="self" and a
nonempty limits list. waiting_for, when needed, is nonblank explanatory text.

checkpoint and check-checkpoint preserve compact turn handoffs on Windows,
Linux, or macOS. They bind each turn to immutable inputs and its previous turn,
reject silently dropped open candidates/questions, and require a recorded
reason plus new located material (or an explanation of ended value) for changes.
They do not verify that a question was asked, an explanation is competitive,
the cited location supports a change, or the conversation has been understood.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


SCHEMA = "statedyne.work-target.v1"
CHECKPOINT_SCHEMA = "statedyne.turn-checkpoint.v1"
SCOPES = ("answer", "question", "conditional")
PHASES = ("quality", "final")
CORE_INPUTS = frozenset(("task", "work", "independent"))
REQUIRED_INPUTS = {
    "quality": CORE_INPUTS,
    "final": CORE_INPUTS | {"draft", "quality_target", "quality_review"},
}
ASSESSMENT_AXES = {
    "quality": frozenset(("breadth", "depth", "innovation", "information", "change")),
    "final": frozenset(("coverage", "grounding", "safety", "delivery")),
}
ALIAS_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")


class CheckError(Exception):
    """An invalid target, review, or input file, suitable for CLI reporting."""


def boundaries():
    return {
        "assurance": "structural_only",
        "semantic_quality": "not_checked",
        "reviewer_identity": "not_authenticated",
        "host_delivery_gate": "not_enforced",
    }


def require_object(value, label):
    if not isinstance(value, dict):
        raise CheckError(f"{label} must be a JSON object")
    return value


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CheckError(f"{label} must be nonempty text")
    return value


def require_choice(value, choices, label):
    if not isinstance(value, str) or value not in choices:
        raise CheckError(f"{label} must be one of: {', '.join(choices)}")
    return value


def require_keys(value, required, label, exact=False):
    require_object(value, label)
    missing = set(required) - set(value)
    if missing:
        raise CheckError(f"{label} is missing: {', '.join(sorted(missing))}")
    extra = set(value) - set(required)
    if exact and extra:
        raise CheckError(f"{label} has unknown fields: {', '.join(sorted(extra))}")


def require_digest(value, label):
    if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
        raise CheckError(f"{label} must be a lowercase SHA-256 hex digest")


def canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def target_digest(target):
    payload = {key: value for key, value in target.items() if key != "digest"}
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def file_stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_file(path, label, collect=False):
    """Hash one regular file; detect ordinary replacement/writes while reading."""
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
        # NONBLOCK keeps a replaced path that is now a FIFO from hanging open().
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(resolved, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise CheckError(f"{label} is not a regular file: {resolved}")
            if before.st_size == 0:
                raise CheckError(f"{label} is empty: {resolved}")
            digest = hashlib.sha256()
            size = 0
            chunks = [] if collect else None
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                if collect:
                    chunks.append(chunk)
            after = os.fstat(stream.fileno())
        # Windows stat(path) and fstat(fd) can expose different ctime semantics.
        # Reopen the current path to compare identity and timestamps via one API.
        if os.name == "nt":
            with os.fdopen(os.open(resolved, flags), "rb") as current:
                path_info = os.fstat(current.fileno())
        else:
            path_info = resolved.stat()
        if (
            file_stamp(before) != file_stamp(after)
            or file_stamp(after) != file_stamp(path_info)
            or size != after.st_size
        ):
            raise CheckError(f"{label} changed while being read; retry: {resolved}")
        if size == 0:
            raise CheckError(f"{label} is empty: {resolved}")
        record = {"path": str(resolved), "sha256": digest.hexdigest(), "bytes": size}
        return record, b"".join(chunks) if collect else None
    except (OSError, ValueError, RuntimeError) as exc:
        raise CheckError(f"cannot read {label} ({path}): {exc}") from exc


def assert_version(actual, expected, label):
    if actual != expected:
        changed = [key for key in ("path", "sha256", "bytes") if actual[key] != expected[key]]
        raise CheckError(
            f"{label} version mismatch ({', '.join(changed)}): {expected['path']}; "
            "create a new target and review the changed version"
        )


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise CheckError(f"non-finite JSON number is not allowed: {value}")


def load_json(path, label, expected=None):
    record, content = read_file(path, label, collect=True)
    if expected is not None:
        # Parse the exact bytes that were matched, not a second unbound read.
        assert_version(record, expected, label)
    try:
        return json.loads(
            content.decode("utf-8"), object_pairs_hook=unique_object,
            parse_constant=invalid_constant,
        )
    except (UnicodeError, ValueError, RecursionError, CheckError) as exc:
        raise CheckError(f"invalid JSON in {label} ({record['path']}): {exc}") from exc


def validate_target(target, label):
    require_keys(target, {"schema", "phase", "scope", "inputs", "digest"}, label, exact=True)
    if target["schema"] != SCHEMA:
        raise CheckError(f"{label}.schema must be {SCHEMA}")
    phase = require_choice(target["phase"], PHASES, f"{label}.phase")
    require_choice(target["scope"], SCOPES, f"{label}.scope")
    require_digest(target["digest"], f"{label}.digest")
    inputs = require_object(target["inputs"], f"{label}.inputs")
    require_keys(inputs, REQUIRED_INPUTS[phase], f"{label}.inputs")
    for alias, record in inputs.items():
        if not ALIAS_RE.fullmatch(alias):
            raise CheckError(f"invalid input alias in {label}: {alias!r}")
        field = f"{label}.inputs.{alias}"
        require_keys(record, {"path", "sha256", "bytes"}, field, exact=True)
        path = require_text(record["path"], f"{field}.path")
        if not Path(path).is_absolute():
            raise CheckError(f"{field}.path must be absolute")
        require_digest(record["sha256"], f"{field}.sha256")
        if type(record["bytes"]) is not int or record["bytes"] <= 0:
            raise CheckError(f"{field}.bytes must be a positive integer")
    if target_digest(target) != target["digest"]:
        raise CheckError(f"{label} digest mismatch: target content was changed or is not canonical")


def validate_review(review, target, label):
    require_keys(
        review,
        {"target_digest", "reviewer", "mode", "verdict", "assessment", "findings", "limits"},
        label,
    )
    require_digest(review["target_digest"], f"{label}.target_digest")
    if review["target_digest"] != target["digest"]:
        raise CheckError(f"{label}.target_digest does not match the reviewed target")
    reviewer = require_text(review["reviewer"], f"{label}.reviewer")
    mode = require_choice(review["mode"], ("peer", "self"), f"{label}.mode")
    verdict = require_choice(review["verdict"], ("ready", "needs_info", "rework"), f"{label}.verdict")
    phase = target["phase"]
    assessment = review["assessment"]
    require_keys(assessment, ASSESSMENT_AXES[phase], f"{label}.assessment", exact=True)
    for axis, text in assessment.items():
        require_text(text, f"{label}.assessment.{axis}")
    limits = review["limits"]
    if not isinstance(limits, list):
        raise CheckError(f"{label}.limits must be a list of nonempty text items")
    for index, text in enumerate(limits):
        require_text(text, f"{label}.limits[{index}]")
    if mode == "self":
        if reviewer != "self":
            raise CheckError(f'{label}: self-review must use reviewer="self"')
        if not limits:
            raise CheckError(f"{label}: self-review requires nonempty limits")
    elif reviewer.strip().casefold() == "self":
        raise CheckError(f"{label}: reviewer self cannot claim mode peer")
    findings = review["findings"]
    if not isinstance(findings, list):
        raise CheckError(f"{label}.findings must be a list")
    has_blocker = False
    for index, finding in enumerate(findings):
        field = f"{label}.findings[{index}]"
        require_keys(finding, {"axis", "severity", "gap", "consequence", "return_to"}, field)
        for key in ("axis", "gap", "consequence", "return_to"):
            require_text(finding[key], f"{field}.{key}")
        require_choice(finding["severity"], ("blocker", "note"), f"{field}.severity")
        has_blocker |= finding["severity"] == "blocker"
    if "waiting_for" in review:
        require_text(review["waiting_for"], f"{label}.waiting_for")
    if verdict == "rework":
        raise CheckError(f"{label}: verdict rework requires revision and cannot pass")
    if verdict == "ready" and has_blocker:
        raise CheckError(f"{label}: verdict ready cannot contain a blocker")
    if phase == "final" and verdict != "ready":
        raise CheckError(f"{label}: final review permits only verdict ready")
    if verdict == "needs_info":
        if target["scope"] not in ("question", "conditional"):
            raise CheckError(f"{label}: needs_info requires scope question or conditional")
        require_text(review.get("waiting_for"), f"{label}.waiting_for")


def check_pair(target_path, review_path, expected_target=None, expected_review=None, required_phase=None):
    target = load_json(target_path, "target", expected_target)
    validate_target(target, "target")
    if required_phase is not None and target["phase"] != required_phase:
        raise CheckError(f"referenced quality_target must have phase {required_phase}")
    for alias, record in target["inputs"].items():
        current, _ = read_file(record["path"], f"input {alias}")
        assert_version(current, record, f"input {alias}")
    review = load_json(review_path, "review", expected_review)
    validate_review(review, target, "review")
    result = {
        "phase": target["phase"], "scope": target["scope"],
        "target_digest": target["digest"], "verdict": review["verdict"],
        "mode": review["mode"], "reviewer": review["reviewer"],
    }
    if review["verdict"] == "needs_info":
        result["waiting_for"] = review["waiting_for"]
    if target["phase"] == "final":
        inputs = target["inputs"]
        quality_target, quality_result = check_pair(
            inputs["quality_target"]["path"], inputs["quality_review"]["path"],
            expected_target=inputs["quality_target"],
            expected_review=inputs["quality_review"], required_phase="quality",
        )
        if quality_target["scope"] != target["scope"]:
            raise CheckError("final scope must equal the referenced quality target scope")
        # Additional dependencies shared by both phases need the same binding
        # as core artifacts; otherwise an old quality review could approve a
        # replacement source that the final target merely hashes for itself.
        shared_inputs = set(inputs) & set(quality_target["inputs"])
        for alias in sorted(shared_inputs):
            if inputs[alias] != quality_target["inputs"][alias]:
                raise CheckError(
                    f"final input {alias} is not the exact version bound by quality_target; "
                    "an old quality review cannot approve a new work package"
                )
        result["quality"] = quality_result
    return target, result


def snapshot(args):
    inputs = {}
    for specification in args.input:
        alias, separator, path = specification.partition("=")
        if not separator or not ALIAS_RE.fullmatch(alias) or not path.strip():
            raise CheckError(f"--input must be NAME=PATH with a nonempty path: {specification!r}")
        if alias in inputs:
            raise CheckError(f"duplicate input alias: {alias}")
        inputs[alias], _ = read_file(path, f"input {alias}")
    require_keys(inputs, REQUIRED_INPUTS[args.phase], "snapshot inputs")
    target = {"schema": SCHEMA, "phase": args.phase, "scope": args.scope, "inputs": inputs}
    target["digest"] = target_digest(target)
    # Do not resolve a pre-existing output symlink into a different new path.
    output = Path(os.path.abspath(os.path.expanduser(args.out)))
    text = json.dumps(target, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    try:
        with output.open("x", encoding="utf-8") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise CheckError(f"output already exists; use a new filename: {output}") from exc
    return {"target": str(output), "target_digest": target["digest"], "phase": args.phase, "scope": args.scope}


def validate_record(record, label):
    require_keys(record, {"path", "sha256", "bytes"}, label, exact=True)
    if not Path(require_text(record["path"], f"{label}.path")).is_absolute():
        raise CheckError(f"{label}.path must be absolute")
    require_digest(record["sha256"], f"{label}.sha256")
    if type(record["bytes"]) is not int or record["bytes"] <= 0:
        raise CheckError(f"{label}.bytes must be a positive integer")


def without_change(item):
    return {key: value for key, value in item.items() if key != "change"}


def validate_change(change, label, inputs, previous, allow_ended):
    require_keys(change, {"reason"}, label)
    if set(change) - {"reason", "evidence", "value_ended"}:
        raise CheckError(f"{label} has unknown fields")
    require_text(change["reason"], f"{label}.reason")
    evidence = change.get("evidence", [])
    if not isinstance(evidence, list):
        raise CheckError(f"{label}.evidence must be a list")
    prior_material = {record["sha256"] for record in previous["inputs"].values()} if previous else set()
    new_material = False
    for index, reference in enumerate(evidence):
        field = f"{label}.evidence[{index}]"
        require_keys(reference, {"input", "at"}, field, exact=True)
        alias = require_text(reference["input"], f"{field}.input")
        require_text(reference["at"], f"{field}.at")
        if alias not in inputs:
            raise CheckError(f"{field} refers to unbound input: {alias}")
        new_material |= inputs[alias]["sha256"] not in prior_material
    ended = change.get("value_ended")
    if ended is not None:
        require_text(ended, f"{label}.value_ended")
        if not allow_ended:
            raise CheckError(f"{label}: value_ended only closes an item or revises the task")
    if not new_material and ended is None:
        raise CheckError(f"{label} needs located new material or an explanation of ended value")


def validate_turn_state(state, inputs, previous=None):
    require_keys(state, {"task", "candidates", "questions"}, "state", exact=True)
    task = state["task"]
    require_keys(task, {"goal", "current", "unfinished", "return_to"}, "state.task")
    if set(task) - {"goal", "current", "unfinished", "return_to", "change"}:
        raise CheckError("state.task has unknown fields")
    for key in ("goal", "current"):
        require_text(task[key], f"state.task.{key}")
    if task["return_to"] is not None:
        require_text(task["return_to"], "state.task.return_to")
    if not isinstance(task["unfinished"], list):
        raise CheckError("state.task.unfinished must be a list")
    for index, item in enumerate(task["unfinished"]):
        require_text(item, f"state.task.unfinished[{index}]")
    prior_state = previous["state"] if previous else None
    if prior_state and without_change(task) != without_change(prior_state["task"]) and "change" not in task:
        raise CheckError("state.task changed without a recorded change")
    if "change" in task and (not prior_state or task != prior_state["task"]):
        validate_change(task["change"], "state.task.change", inputs, previous, True)
    for collection in ("candidates", "questions"):
        entries = state[collection]
        if not isinstance(entries, list):
            raise CheckError(f"state.{collection} must be a list")
        prior_entries = {item["id"]: item for item in prior_state[collection]} if prior_state else {}
        current = {}
        statuses = ("open", "closed") if collection == "candidates" else ("open", "answered", "closed")
        for index, item in enumerate(entries):
            field = f"state.{collection}[{index}]"
            require_keys(item, {"id", "summary", "status"}, field)
            if set(item) - {"id", "summary", "status", "change"}:
                raise CheckError(f"{field} has unknown fields")
            key = require_text(item["id"], f"{field}.id")
            if not ALIAS_RE.fullmatch(key) or key in current:
                raise CheckError(f"{field}.id must be unique and use the input-alias syntax")
            current[key] = item
            require_text(item["summary"], f"{field}.summary")
            require_choice(item["status"], statuses, f"{field}.status")
            prior = prior_entries.get(key)
            changed = prior is not None and without_change(item) != without_change(prior)
            if (changed or (prior is None and item["status"] != "open")) and "change" not in item:
                raise CheckError(f"{field} changed or closed without a recorded change")
            if "change" in item and item != prior:
                validate_change(item["change"], f"{field}.change", inputs, previous, item["status"] == "closed")
        missing = [key for key, item in prior_entries.items() if item["status"] == "open" and key not in current]
        if missing:
            raise CheckError(f"state.{collection} silently drops open items: {', '.join(missing)}")


def check_checkpoint(path, expected=None):
    """Read an immutable chain once, then check its transitions oldest first."""
    chain, seen = [], set()
    while path is not None:
        checkpoint = load_json(path, "checkpoint", expected)
        require_keys(checkpoint, {"schema", "turn", "previous", "source", "inputs", "state", "digest"}, "checkpoint", exact=True)
        if checkpoint["schema"] != CHECKPOINT_SCHEMA:
            raise CheckError(f"checkpoint.schema must be {CHECKPOINT_SCHEMA}")
        if type(checkpoint["turn"]) is not int or checkpoint["turn"] < 1:
            raise CheckError("checkpoint.turn must be a positive integer")
        require_digest(checkpoint["digest"], "checkpoint.digest")
        if target_digest(checkpoint) != checkpoint["digest"]:
            raise CheckError("checkpoint digest mismatch")
        resolved = str(Path(path).resolve())
        if resolved in seen:
            raise CheckError("checkpoint ancestry contains a cycle")
        seen.add(resolved)
        inputs = require_object(checkpoint["inputs"], "checkpoint.inputs")
        if not inputs:
            raise CheckError("checkpoint needs at least one bound material input")
        for alias, record in inputs.items():
            if not ALIAS_RE.fullmatch(alias):
                raise CheckError(f"invalid checkpoint input alias: {alias!r}")
            validate_record(record, f"checkpoint.inputs.{alias}")
            actual, _ = read_file(record["path"], f"checkpoint input {alias}")
            assert_version(actual, record, f"checkpoint input {alias}")
        validate_record(checkpoint["source"], "checkpoint.source")
        source = load_json(checkpoint["source"]["path"], "checkpoint source", checkpoint["source"])
        if source != checkpoint["state"]:
            raise CheckError("checkpoint state differs from its bound source")
        chain.append(checkpoint)
        expected = checkpoint["previous"]
        if expected is not None:
            validate_record(expected, "checkpoint.previous")
            path = expected["path"]
        else:
            path = None
    previous = None
    for checkpoint in reversed(chain):
        expected_turn = previous["turn"] + 1 if previous else 1
        if checkpoint["turn"] != expected_turn:
            raise CheckError("checkpoint turn does not follow its previous turn")
        validate_turn_state(checkpoint["state"], checkpoint["inputs"], previous)
        previous = checkpoint
    return chain[0]


def checkpoint(args):
    previous, previous_record = None, None
    if args.previous:
        previous_record, _ = read_file(args.previous, "previous checkpoint")
        previous = check_checkpoint(args.previous, previous_record)
    inputs = {}
    for specification in args.input:
        alias, separator, path = specification.partition("=")
        if not separator or not ALIAS_RE.fullmatch(alias) or not path.strip():
            raise CheckError(f"--input must be NAME=PATH: {specification!r}")
        if alias in inputs:
            raise CheckError(f"duplicate input alias: {alias}")
        inputs[alias], _ = read_file(path, f"input {alias}")
    source, _ = read_file(args.state, "turn state")
    state = load_json(args.state, "turn state", source)
    validate_turn_state(state, inputs, previous)
    target = {"schema": CHECKPOINT_SCHEMA, "turn": previous["turn"] + 1 if previous else 1,
              "previous": previous_record, "source": source, "inputs": inputs, "state": state}
    target["digest"] = target_digest(target)
    output = Path(os.path.abspath(os.path.expanduser(args.out)))
    text = json.dumps(target, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    try:
        with output.open("x", encoding="utf-8") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise CheckError(f"output already exists; use a new filename: {output}") from exc
    return {"checkpoint": str(output), "turn": target["turn"], "digest": target["digest"],
            "continuity": "registered_items_only", "source_locations": "declared_not_verified"}


def parser():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = cli.add_subparsers(dest="command", required=True)
    create = commands.add_parser("snapshot", help="create a new exact-version review target")
    create.add_argument("--phase", required=True, choices=PHASES)
    create.add_argument("--scope", required=True, choices=SCOPES)
    create.add_argument("--out", required=True, help="new JSON path; existing paths are never overwritten")
    create.add_argument("--input", action="append", required=True, metavar="NAME=PATH")
    check = commands.add_parser("check", help="check structure, current versions, and the review binding")
    check.add_argument("--target", required=True)
    check.add_argument("--review", required=True)
    carry = commands.add_parser("checkpoint", help="save a new immutable turn handoff and check continuity")
    carry.add_argument("--state", required=True, help="compact turn-state JSON; preserve this file unchanged")
    carry.add_argument("--previous", help="previous checkpoint JSON; omitted only for the first turn")
    carry.add_argument("--out", required=True, help="new checkpoint JSON path; never overwritten")
    carry.add_argument("--input", action="append", required=True, metavar="NAME=PATH")
    carry_check = commands.add_parser("check-checkpoint", help="verify turn continuity and all bound file versions")
    carry_check.add_argument("--checkpoint", required=True)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            result = snapshot(args)
        elif args.command == "check":
            _, result = check_pair(args.target, args.review)
        elif args.command == "checkpoint":
            result = checkpoint(args)
        else:
            target = check_checkpoint(args.checkpoint)
            result = {"turn": target["turn"], "digest": target["digest"],
                      "continuity": "registered_items_only", "source_locations": "declared_not_verified"}
        print(json.dumps({"ok": True, "operation": args.command, **result, **boundaries()}, ensure_ascii=False, indent=2))
        return 0
    except (CheckError, OSError, ValueError, UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "operation": args.command, "error": str(exc), **boundaries()}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
