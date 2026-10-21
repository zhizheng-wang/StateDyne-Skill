"""Live-model evaluation, isolated inputs, complete failure retention and blind export.

No LLM self-score is used as truth. This tool never substitutes fixtures for live calls.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import time
from .backends import OpenAIBackend
from .common import StateDyneError, atomic_write, controller_lock, digest, read_json, save_json
from .engine import Engine
from .schemas import obj, arr, S, validate, SCHEMAS
from .store import Workspace

CASE_SCHEMA = obj(id=S, task=S, materials=arr(obj(label=S, text=S)))
SCHEMAS["answer"] = obj(answer=S)
DIMENSIONS = ("discovery", "first_turn_contrast_bridge", "cross_context_prediction",
              "information_value", "first_turn_question_focus", "generative_depth",
              "evidence_discipline", "unfounded_hidden_cause_control",
              "innovation_value", "adoption_and_action", "user_burden")


def load_cases(path: Path):
    cases = read_json(path)
    validate(cases, arr(CASE_SCHEMA))
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)) or not cases or any(not x.strip() for x in ids):
        raise StateDyneError("Case IDs must be unique and nonempty")
    if any(not c["task"].strip() for c in cases):
        raise StateDyneError("Case tasks must be nonempty")
    # Extra fields are rejected by the schema, so private rubrics / expected answers
    # cannot accidentally be concatenated into a solver prompt.
    return cases


def legacy_instructions(root: Path):
    paths = ["SKILL.md", "references/runtime.md", "references/dialogue.md", "references/review.md",
             "references/generation.md", "references/reality.md", "references/exploration.md", "references/change.md"]
    texts = []
    for rel in paths:
        path = (root / rel).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise StateDyneError(f"Legacy source is missing: {rel}")
        texts.append(f"\n--- {rel} ---\n{path.read_text(encoding='utf-8')}")
    return ("Apply the supplied method to the user task. In this evaluation you have only the provided evidence tools; "
            "do not claim to execute unavailable scripts or host agents. Return the requested substantive answer in the answer field.\n" + "\n".join(texts))


def run_evaluation(cases_path: Path, out: Path, model: str, arms: list[str], repetitions: int,
                   *, allow_api: bool, legacy_root: Path | None = None, seed=1729, max_operations=5):
    if not allow_api or not os.environ.get("OPENAI_API_KEY"):
        raise StateDyneError("Live evaluation requires --allow-api and OPENAI_API_KEY; no simulated substitute is permitted")
    if not model.strip() or model == "host-selected":
        raise StateDyneError("An explicit accessible API model identifier is required")
    if repetitions < 1 or not arms or len(arms) != len(set(arms)):
        raise StateDyneError("Use positive repetitions and unique arms")
    if not set(arms).issubset({"baseline", "legacy_prompt", "statedyne"}):
        raise StateDyneError("Unknown evaluation arm")
    cases = load_cases(cases_path)
    legacy = legacy_instructions(legacy_root) if "legacy_prompt" in arms and legacy_root else None
    if "legacy_prompt" in arms and legacy is None:
        raise StateDyneError("--legacy-skill is required for the legacy_prompt arm")
    package = Path(__file__).resolve().parents[2]
    out = out.resolve()
    if out.is_relative_to(package) or (out.exists() and any(out.iterdir())):
        raise StateDyneError("Use a new evaluation directory outside the distributable skill")
    out.mkdir(parents=True, exist_ok=True)
    save_json(out / "evaluation-contract.json", {"model": model, "arms": arms, "repetitions": repetitions,
        "case_input_sha256": digest(cases), "seed": seed, "judgment": "awaiting independent scoring",
        "comparison_limit": "API runs, not exact ChatGPT @Skill reproduction. Controlled arm has more calls and may cost more. No gain is inferred without scores.",
        "legacy_prompt_sha256": hashlib.sha256((legacy or "").encode()).hexdigest() if legacy else None})
    schedule = [(case, arm, rep) for case in cases for rep in range(repetitions) for arm in arms]
    random.Random(seed).shuffle(schedule)
    records = []
    for index, (case, arm, rep) in enumerate(schedule):
        sample_id = hashlib.sha256(f"{seed}|{case['id']}|{arm}|{rep}".encode()).hexdigest()[:16]
        folder = out / "runs" / sample_id
        config = {"allow_remote": True, "max_operations": max_operations}
        ws = Workspace.create(folder, case["task"], backend="openai", model=model, config=config,
                              materials=[(m["label"], m["text"]) for m in case["materials"]])
        record = {"sample_id": sample_id, "case_id": case["id"], "arm": arm, "repetition": rep,
                  "model_requested": model, "status": "attempted", "run_path": f"runs/{sample_id}"}
        started = time.monotonic()
        try:
            provider = OpenAIBackend(folder, ws.state["sources"], ws.state["config"])
            with controller_lock(folder):
                if arm == "statedyne":
                    result = Engine(ws, provider).advance()
                    if result.get("answer_file"):
                        record["answer"] = (folder / result["answer_file"]).read_text(encoding="utf-8")
                        record["status"] = result["status"]
                        record["execution_provenance"] = result["assurance"]
                    else:
                        record["status"] = "failed"
                        record["failure"] = result
                else:
                    instruction = legacy if arm == "legacy_prompt" else (
                        "Answer the user's actual task carefully and use available evidence tools when useful. "
                        "Distinguish facts from hypotheses and ask only material unanswered questions. Return your answer in the answer field.")
                    job = ws.get_job("single-forward", "baseline", "answer", ws.raw_view(), instruction)
                    result = provider.execute(job)
                    record.update(answer=result["output"]["answer"], status="answered", execution_provenance=result["backend_kind"])
                    ws.mark_result(job["id"])
                    ws.save("live_baseline_completed")
        except Exception as exc:
            # Retain the very first failure; no best-of or silent retry of a sample.
            record.update(status="failed", failure={"type": type(exc).__name__, "message": str(exc)})
        record["elapsed_seconds"] = time.monotonic() - started
        token_counts = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        actual_models = set()
        calls = 0
        for path in folder.glob("jobs/*/transport.json"):
            transport = read_json(path)
            if transport["kind"] != "openai_live":
                raise StateDyneError("A non-live transport was found in live evaluation")
            for item in transport["calls"]:
                calls += 1
                actual_models.add(item.get("model") or model)
                for key in token_counts:
                    token_counts[key] += (item.get("usage") or {}).get(key, 0) or 0
        record.update(api_responses=calls, usage=token_counts, actual_models=sorted(actual_models),
                      financial_cost="not computed; no guessed model pricing")
        records.append(record)
        save_json(out / "samples.json", records)
        # One line of progress; no claimed performance score.
        print(json.dumps({"sample": index + 1, "total": len(schedule), "status": record["status"]}, ensure_ascii=False), flush=True)
    return {"attempts": len(records), "failed": sum(r["status"] == "failed" for r in records),
            "semantic_quality": "not scored", "samples": str(out / "samples.json")}


def blind_export(samples_path: Path, out: Path, seed=31):
    samples = read_json(samples_path)
    if out.exists() and any(out.iterdir()):
        raise StateDyneError("Blind export directory must be empty")
    out.mkdir(parents=True, exist_ok=True)
    order = list(samples)
    random.Random(seed).shuffle(order)
    review, key = [], {}
    for index, sample in enumerate(order):
        opaque = f"sample-{index + 1:04d}"
        review.append({"review_id": opaque, "case_id": sample["case_id"],
                       "answer": sample.get("answer", "[No completed answer; execution failed]"),
                       "scores": {d: None for d in DIMENSIONS}, "evidence_notes": ""})
        key[opaque] = {k: sample[k] for k in ("sample_id", "case_id", "arm", "repetition", "status")}
    save_json(out / "review.json", review)
    save_json(out / "keep-from-reviewer-key.json", key)
    atomic_write(out / "README.txt", "Give review.json and the original case materials to independent reviewers. Keep the key separate.\nScores: 0..4 for each applicable dimension, null when not applicable. Require evidence_notes and identify the reviewer separately.\nStylistic clues may still reveal an arm. Missing output is an execution failure, not automatically a semantic score of zero.\n")
    return {"review_file": str(out / "review.json"), "key_file": str(out / "keep-from-reviewer-key.json"), "scored": False}


def score_summary(review_path: Path, key_path: Path, reviewer: str):
    if not reviewer.strip():
        raise StateDyneError("Reviewer identity/label is required")
    reviews, keys = read_json(review_path), read_json(key_path)
    seen, groups = set(), {}
    for item in reviews:
        rid = item["review_id"]
        if rid in seen or rid not in keys:
            raise StateDyneError("Unknown or duplicate review ID")
        seen.add(rid)
        if set(item["scores"]) != set(DIMENSIONS):
            raise StateDyneError("Scoring dimension mismatch")
        values = [v for v in item["scores"].values() if v is not None]
        if values and not item["evidence_notes"].strip():
            raise StateDyneError("Scores require observable evidence notes")
        arm = keys[rid]["arm"]
        group = groups.setdefault(arm, {d: [] for d in DIMENSIONS})
        for d, value in item["scores"].items():
            if value is not None:
                if type(value) is not int or not 0 <= value <= 4:
                    raise StateDyneError("Scores must be integers 0..4 or null")
                group[d].append(value)
    result = {arm: {d: {"n": len(values), "minimum": min(values) if values else None,
                       "median": statistics.median(values) if values else None,
                       "mean": statistics.mean(values) if values else None}
                    for d, values in dims.items()} for arm, dims in groups.items()}
    return {"reviewer": reviewer, "by_arm": result, "unreturned_reviews": len(keys) - len(seen),
            "limit": "Reviewer scores are evidence, not truth certificates. Do not infer general superiority from this summary alone."}


def paired_diagnostics(review_path: Path, key_path: Path, samples_path: Path, reviewer: str):
    """Report truly paired scores and resource costs, without inventing significance.

    This tool neither assigns semantic scores nor certifies independence.
    Missing/failing samples are retained as visible incomplete pairs.
    """
    if not reviewer.strip():
        raise StateDyneError('Reviewer identity is required')
    reviews=read_json(review_path)
    keys=read_json(key_path)
    samples=read_json(samples_path)
    if len({s['sample_id'] for s in samples})!=len(samples):
        raise StateDyneError('Duplicate sample IDs')
    evidence={s['sample_id']:s for s in samples}
    review_by_sample={}
    for item in reviews:
        rid=item['review_id']
        if rid not in keys or keys[rid]['sample_id'] not in evidence:
            raise StateDyneError('A blind review has no matching run/evaluation key')
        sample_id=keys[rid]['sample_id']
        if sample_id in review_by_sample:
            raise StateDyneError('Same sample reviewed more than once under one reviewer')
        key=keys[rid];original=evidence[sample_id]
        if any(key[k]!=original[k] for k in ('case_id','arm','repetition')):
            raise StateDyneError('Blind review key does not match the immutable sample identity')
        values=item['scores']
        if set(values)!=set(DIMENSIONS):
            raise StateDyneError('Scoring dimensions inconsistent with current evaluator')
        for dim,val in values.items():
            if val is not None and (type(val) is not int or not 0<=val<=4):
                raise StateDyneError('Score must be 0..4 or null')
        if any(v is not None for v in values.values()) and not item['evidence_notes'].strip():
            raise StateDyneError('Every scored review needs observable evidence notes')
        review_by_sample[sample_id]=item
    by_case={}
    for sample in samples:
        group=(sample['case_id'],sample['repetition'])
        arms=by_case.setdefault(group,{})
        if sample['arm'] in arms:
            raise StateDyneError('More than one run per arm/case/repetition pair')
        arms[sample['arm']]=sample
    pair_rows=[]; skipped=[]
    for (case,repeat),arms in sorted(by_case.items()):
        if set(('baseline','statedyne'))-set(arms):
            skipped.append({'case_id':case,'repetition':repeat,'reason':'missing baseline or statedyne arm'})
            continue
        base=arms['baseline'];sk=arms['statedyne']
        if base.get('status') not in ('answered','complete','provisional','needs_information') or sk.get('status') not in ('answered','complete','provisional','needs_information'):
            skipped.append({'case_id':case,'repetition':repeat,'reason':'one or both runs did not complete'})
            continue
        if base['sample_id'] not in review_by_sample or sk['sample_id'] not in review_by_sample:
            skipped.append({'case_id':case,'repetition':repeat,'reason':'missing blind score for one of the paired runs'})
            continue
        s0=review_by_sample[base['sample_id']]['scores'];s1=review_by_sample[sk['sample_id']]['scores']
        delta={d: (s1[d]-s0[d] if s1[d] is not None and s0[d] is not None else None) for d in DIMENSIONS}
        resources={}
        for key in ('elapsed_seconds','api_responses'):
            x0=base.get(key);x1=sk.get(key)
            resources[key]={'baseline':x0,'statedyne':x1,'ratio':x1/x0 if isinstance(x0,(int,float)) and x0>0 and isinstance(x1,(int,float)) else None}
        for key in ('input_tokens','output_tokens','total_tokens'):
            x0=base.get('usage',{}).get(key);x1=sk.get('usage',{}).get(key)
            resources[key]={'baseline':x0,'statedyne':x1,'ratio':x1/x0 if isinstance(x0,(int,float)) and x0>0 and isinstance(x1,(int,float)) else None}
        pair_rows.append({'case_id':case,'repetition':repeat,'score_deltas_statedyne_minus_baseline':delta,
                          'resource_comparison':resources})
    aggregate={}
    for d in DIMENSIONS:
        vals=[r['score_deltas_statedyne_minus_baseline'][d] for r in pair_rows
              if r['score_deltas_statedyne_minus_baseline'][d] is not None]
        aggregate[d]={'n_pairs':len(vals),'mean_delta':statistics.mean(vals) if vals else None,
                      'wins':sum(v>0 for v in vals),'ties':sum(v==0 for v in vals),'losses':sum(v<0 for v in vals)}
    return {'reviewer':reviewer,'complete_pairs':len(pair_rows),'skipped_pairs':skipped,
            'by_dimension':aggregate,'pairs':pair_rows,
            'limitations':('Scores are reviewer judgments, not ground truth; paired tests need matched model, '
                           'source access and disclosure timing. Extra model/API calls are resources, not evidence of skill gain. '
                           'Incomplete pairs and repeated cases constrain generalization. No significance or win claim is calculated.')}

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--cases", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--arms", default="baseline,statedyne")
    run.add_argument("--repetitions", type=int, default=3)
    run.add_argument("--legacy-skill", type=Path, default=None)
    run.add_argument("--allow-api", action="store_true")
    run.add_argument("--max-operations", type=int, default=5)
    export = sub.add_parser("blind-export")
    export.add_argument("--samples", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    score = sub.add_parser("summarize-scores")
    score.add_argument("--review", type=Path, required=True)
    score.add_argument("--key", type=Path, required=True)
    score.add_argument("--reviewer", required=True)
    paired = sub.add_parser("paired-diagnostics", help="Compare already blind-scored, matching case/repetition pairs; never auto-score content")
    paired.add_argument("--review", type=Path, required=True)
    paired.add_argument("--key", type=Path, required=True)
    paired.add_argument("--samples", type=Path, required=True)
    paired.add_argument("--reviewer", required=True)
    args = p.parse_args(argv)
    try:
        if args.command == "run":
            result = run_evaluation(args.cases, args.out, args.model, args.arms.split(","), args.repetitions,
                                    allow_api=args.allow_api, legacy_root=args.legacy_skill, max_operations=args.max_operations)
        elif args.command == "blind-export":
            result = blind_export(args.samples, args.out)
        elif args.command == "paired-diagnostics":
            result = paired_diagnostics(args.review, args.key, args.samples, args.reviewer)
        else:
            result = score_summary(args.review, args.key, args.reviewer)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (StateDyneError, OSError, ValueError, KeyError, TypeError) as exc:
        import sys
        print(f"StateDyne evaluation: {exc}", file=sys.stderr)
        return 2
