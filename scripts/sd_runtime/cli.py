"""Command-line entry for actual execution and native-host handoff."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from . import __version__
from .backends import NativeBackend, OpenAIBackend
from .common import StateDyneError, controller_lock, loads, read_json, save_json
from .engine import Engine
from .store import Workspace


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def backend_for(ws):
    if ws.state["backend"] == "native":
        return NativeBackend(ws.root, ws.state["sources"], ws.state["config"])
    if ws.state["backend"] == "openai":
        return OpenAIBackend(ws.root, ws.state["sources"], ws.state["config"])
    raise StateDyneError("Fixture backend is test-only and cannot be selected from the product CLI")


def parser():
    p = argparse.ArgumentParser(description=f"StateDyne {__version__} generative-loop executor; Python >= 3.10; no private reasoning capture.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Report capabilities without making any model or network call")
    start = sub.add_parser("start", help="Create a new run and advance to an actual result or pending host jobs")
    start.add_argument("--task-file", type=Path, required=True, help="UTF-8 plain text/Markdown")
    start.add_argument("--workdir", type=Path, required=True, help="New empty directory OUTSIDE this skill")
    start.add_argument("--backend", choices=("native", "openai"), default="native")
    start.add_argument("--model", default="host-selected", help="Exact API model ID for OpenAI; no default or fallback model")
    start.add_argument("--scope", choices=("auto", "analysis", "points", "actions", "plan"), default="auto")
    start.add_argument("--material", type=Path, action="append", default=[], help="Explicitly authorized UTF-8 material; repeatable")
    start.add_argument("--allow-api", action="store_true", help="Authorize sending this task and registered materials to the official OpenAI API")
    start.add_argument("--web-search", action="store_true", help="Enable the official Responses web_search hosted tool for authorized API jobs. Supported model and account required; cited leads are not independently verified source text.")
    start.add_argument("--max-operations", type=int, default=None,
                       help="Optional explicit operational safety ceiling; default is no cognitive exploration quota")
    start.add_argument("--parallel-workers", type=int, default=12,
                       help="Maximum genuine independent worker calls in flight; default 12")
    start.add_argument("--max-parallel-operations", type=int, default=12,
                       help="Concurrent independent exploration tasks per scheduling decision")
    start.add_argument("--max-repairs", type=int, default=8)
    start.add_argument("--max-entry-repairs", type=int, default=8, help="Max independent first-pass gap repairs; fail closed after exhaustion")
    start.add_argument("--max-jobs", type=int, default=2048)
    start.add_argument("--max-api-requests", type=int, default=4096)
    start.add_argument("--max-output-tokens", type=int, default=16000)
    start.add_argument("--max-question-characters", type=int, default=None, help="Optional user-configured visible-question character limit (no default cap)")
    start.add_argument("--reasoning-effort", default=None, help="Optional; must be supported by the specified API model")
    retry = sub.add_parser("retry", help="Retain a failed unaccepted attempt and create a fresh explicitly requested job")
    retry.add_argument("--workdir", type=Path, required=True)
    retry.add_argument("--job", required=True)
    retry.add_argument("--reason", required=True)
    for name in ("advance", "status", "trace", "verify"):
        item = sub.add_parser(name)
        item.add_argument("--workdir", type=Path, required=True)
    submit = sub.add_parser("submit", help="Submit an actual native worker's schema-conforming observable output")
    submit.add_argument("--workdir", type=Path, required=True)
    submit.add_argument("--job", required=True)
    submit.add_argument("--output-file", type=Path, required=True)
    submit.add_argument("--input-sha", required=True)
    submit.add_argument("--worker-ref", required=True, help="Actual host spawn/tool-call reference; never invent a receipt")
    submit.add_argument("--actual-model", required=True)
    submit.add_argument("--independent-context", action="store_true", help="Attest this worker received only the specified context in a fresh host session")
    tool = sub.add_parser("tool", help="Execute an allowlisted local evidence tool for a native worker")
    tool.add_argument("--workdir", type=Path, required=True)
    tool.add_argument("--job", required=True)
    tool.add_argument("--name", required=True)
    tool.add_argument("--args", required=True, help="Strict JSON arguments")
    cont = sub.add_parser("continue", help="Continue to intervention points, actions or plan without re-running unchanged raw discovery")
    cont.add_argument("--workdir", type=Path, required=True)
    cont.add_argument("--scope", choices=("next", "points", "actions", "plan"), required=True)
    expand = sub.add_parser("expand", help="Explicitly broaden an already released analysis without replaying the initial discovery")
    expand.add_argument("--workdir", type=Path, required=True)
    expand.add_argument("--focus", default="", help="Optional user-named difference to investigate; leave empty for independent model-outside search")
    source = sub.add_parser("add-evidence", help="Import actually retrieved/authorized external evidence with its URL; never asserts it was verified by this program")
    source.add_argument("--workdir", type=Path, required=True)
    source.add_argument("--source-file", type=Path, required=True)
    source.add_argument("--url", required=True, help="Actual public source HTTP(S) URL")
    source.add_argument("--label", required=True, help="Human-readable real source title")
    update = sub.add_parser("update", help="Automatically route a user turn; explicit --side-question or --force-primary override for trusted host adapters")
    update.add_argument("--workdir", type=Path, required=True)
    update.add_argument("--source-file", type=Path, required=True)
    update.add_argument("--supersedes", default=None, help="Explicit source ID whose old contents are replaced")
    update.add_argument("--scope", choices=("auto", "analysis", "points", "actions", "plan"), default=None)
    update.add_argument("--side-question", action="store_true", help="Explicitly route as a side question")
    update.add_argument("--force-primary", action="store_true", help="Explicitly route as new main-task evidence without independent intent classification")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            print_json({"skill_version": __version__, "python": sys.version.split()[0],
                        "api_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
                        "doctor_performs_model_test": False,
                        "native_worker_availability": "Must be inspected through the current host's actual tools",
                        "local_tools": ["registered_material_read", "literal_material_search", "bounded_arithmetic"],
                        "public_web_in_api_runner": "opt-in via --backend openai --allow-api --web-search; records URLs and search actions, does not automatically verify full original text",
                        "network_calls_made": 0})
            return 0
        if args.command == "start":
            if args.web_search and args.backend != "openai":
                raise StateDyneError("--web-search requires --backend openai with explicit --allow-api; native jobs use the host's separately authorized search tools")
            package_root = Path(__file__).resolve().parents[2]
            if args.workdir.resolve().is_relative_to(package_root):
                raise StateDyneError("Keep private run data outside the distributable skill directory")
            if args.backend == "openai":
                if not args.allow_api:
                    raise StateDyneError("Use --allow-api only after authorizing remote transmission")
                if args.model == "host-selected" or not args.model.strip():
                    raise StateDyneError("Specify an API model ID available to your account; a ChatGPT UI name is not assumed to be an API ID")
                if not os.environ.get("OPENAI_API_KEY"):
                    raise StateDyneError("No OPENAI_API_KEY; no API request or capability test has run")
            task = args.task_file.read_text(encoding="utf-8")
            materials = [(path.name, path.read_text(encoding="utf-8")) for path in args.material]
            config = {k: getattr(args, k) for k in ("max_operations", "parallel_workers", "max_parallel_operations", "max_repairs", "max_entry_repairs", "max_jobs", "max_api_requests", "max_output_tokens", "max_question_characters", "reasoning_effort")}
            config["allow_remote"] = args.allow_api
            config["web_search_enabled"] = bool(args.web_search and args.backend == "openai")
            ws = Workspace.create(args.workdir, task, scope=args.scope, backend=args.backend,
                                  model=args.model, config=config, materials=materials)
            with controller_lock(ws.root):
                print_json(Engine(ws, backend_for(ws)).advance())
            return 0
        ws = Workspace(args.workdir)
        with controller_lock(ws.root):
            if args.command == "status":
                print_json({"phase": ws.state["phase"], "generation": ws.state["generation"],
                            "revision": ws.state["revision"], "claims": len(ws.active_claims()),
                            "unknowns": len(ws.state["unknowns"]),
                            "foci": len(ws.state.get("foci", [])),
                            "system_goal": (ws.state.get('system_map') or {}).get('goal_text'),
                            "open_system_dimensions": [row['dimension'] for row in (ws.state.get('system_map') or {}).get('coverage',[]) if row['state']=='open'],
                            "processed_delta_sources": ws.state.get('processed_delta_sources',[]),
                            "public_citation_leads": len(ws.state.get("web_research_leads", {})),
                            "entry_repairs_done": ws.state.get("entry_repairs_done", 0), "backend": ws.state["backend"],
                            "last_error": ws.state.get("last_error"),
                            "pending_jobs": [j for j in ws.state["jobs"].values() if j["status"] == "pending"
                                             and ws.job_request(j["id"])["generation"] == ws.state["generation"]],
                            "stop_reason": ws.state["stop_reason"],
                            "expansion_runs":len(ws.state.get("expansion_runs",[])),
                            "expand_available":ws.state["phase"]=="done"})
            elif args.command == "trace":
                # A factual execution audit, not the model's hidden thoughts.
                jobs = []
                for jid, info in ws.state["jobs"].items():
                    req = ws.job_request(jid)
                    receipt = ws.result(jid)
                    jobs.append({"job_id": jid, "role": req["role"], "generation": req["generation"],
                                 "status": info["status"],
                                 "execution": None if receipt is None else {
                                     "backend_kind": receipt["backend_kind"],
                                     "actual_model": receipt["actual_model"],
                                     "independent_context_attested": receipt["independent_context"],
                                     "worker_ref": receipt["worker_ref"],
                                     "elapsed_seconds": receipt.get("elapsed_seconds"),
                                     "usage": receipt.get("usage", {}),
                                     "web_search_actions": receipt.get("web_research", []),
                                     "public_citation_leads": receipt.get("web_research_leads", [])}})
                latest = ws.state.get("entry_review") or {}
                from .probe_bridge import unbridged_model_outside
                confirmed_workers = [j for j in jobs if j["execution"] is not None and
                                     j["execution"]["independent_context_attested"]]
                print_json({"skill_version": ws.state["skill_version"],
                            "phase": ws.state["phase"], "generation": ws.state["generation"],
                            "real_worker_receipts": len(confirmed_workers),
                            "claimed_multiagent_without_receipts": False,
                            "unbridged_model_outside_candidates": unbridged_model_outside(ws),
                            "engine_claims_internal_thought_access": False,
                            "system_goal": (ws.state.get('system_map') or {}).get('goal_text'),
                            "system_coverage": [{"dimension":row['dimension'], "state":row['state'], "basis":row['basis']} for row in (ws.state.get('system_map') or {}).get('coverage',[])],
                            "processed_delta_sources": ws.state.get('processed_delta_sources',[]),
                            "initial_contrasts": [{"id": f["id"], "observation": f["observation"],
                                                  "priority": f["priority"]} for f in ws.state.get("foci", [])],
                            "latest_boundary_review": latest.get("output", {}).get("coverage", []),
                            "first_pass_unresolved": ws.state.get("entry_unresolved", False),
                            "boundary_reviews": len(ws.state.get("entry_reviews", [])),
                            "repair_count": ws.state.get("entry_repairs_done", 0),
                            "expansion_runs": ws.state.get("expansion_runs",[]),
                            "jobs": jobs,
                            "release": read_json(ws.root / "release.json") if (ws.root / "release.json").exists() else None,
                            "limitation": "Records actual job receipts, declared relations and model review; it does not prove independent semantics or AI capability."})
            elif args.command == "retry":
                job = ws.retry_job(args.job, args.reason)
                print_json({"status": "new_attempt_created_old_attempt_retained", "job": job["id"], "next": "advance"})
            elif args.command == "submit":
                if ws.state["backend"] != "native":
                    raise StateDyneError("Native submissions cannot overwrite API execution records")
                job = ws.job_request(args.job)
                if job["generation"] != ws.state["generation"] or ws.state["jobs"][args.job]["status"] != "pending":
                    raise StateDyneError("This job is not a current pending attempt")
                output = read_json(args.output_file)
                provider = NativeBackend(ws.root, ws.state["sources"], ws.state["config"])
                provider.submit(job, output, input_sha=args.input_sha, worker_ref=args.worker_ref,
                                actual_model=args.actual_model, independent_context=args.independent_context)
                print_json({"status": "actual_output_received_schema_checked", "job": args.job,
                            "semantic_quality": "not inferred from schema validation",
                            "next": "advance"})
            elif args.command == "tool":
                if ws.state["backend"] != "native":
                    raise StateDyneError("The explicit tool bridge is for native jobs only")
                job = ws.job_request(args.job)
                if job["generation"] != ws.state["generation"] or ws.state["jobs"][args.job]["status"] != "pending" or ws.result(args.job) is not None:
                    raise StateDyneError("Tool access is restricted to a current pending job")
                definitions = __import__("sd_runtime.evidence", fromlist=["TOOL_DEFINITIONS"]).TOOL_DEFINITIONS
                by_name = {t["name"]: t for t in definitions}
                if args.name not in by_name:
                    raise StateDyneError("Tool is not allowlisted")
                data = loads(args.args)
                from .schemas import validate
                validate(data, by_name[args.name]["parameters"])
                print_json(NativeBackend(ws.root, ws.state["sources"], ws.state["config"]).tool(job, args.name, data))
            elif args.command == "continue":
                ws.continue_stage(args.scope)
                print_json({"status": "continuing_verified_evidence_without_restarting_discovery",
                            "scope": ws.state["scope"], "next": "advance"})
            elif args.command == "expand":
                ws.expand_search(args.focus)
                print_json({"status":"explicit_broad_search_requested",
                            "focus":args.focus,"next":"advance",
                            "true_workers_started":False})
            elif args.command == "add-evidence":
                sid = ws.update(args.source_file.read_text(encoding="utf-8"),
                                source_kind="retrieved_public", source_url=args.url, source_label=args.label)
                print_json({"source_id": sid, "kind": "retrieved_public",
                            "source_url": args.url, "note": "External document imported and attributed; accuracy and retrieval were not independently verified by the CLI.",
                            "next": "advance"})
            elif args.command == "update":
                if args.side_question and args.force_primary:
                    raise StateDyneError("Cannot force a turn to be both side and primary")
                content=args.source_file.read_text(encoding="utf-8")
                if args.supersedes or args.scope is not None or args.side_question or args.force_primary:
                    sid=ws.update(content, args.supersedes, args.scope,
                                  interaction="side_question" if args.side_question else "feedback")
                    print_json({"source_id":sid,"status":"explicit_update_scheduled",
                                "mode":ws.state.get("interaction_mode"),"next":"advance"})
                else:
                    print_json(ws.receive_user_turn(content))
            elif args.command == "advance":
                print_json(Engine(ws, backend_for(ws)).advance())
            elif args.command == "verify":
                ws.verify_events()
                if ws.state["phase"] == "done":
                    print_json(Engine(ws, None).verify_release())
                else:
                    print_json({"integrity": "PASS", "released": False, "phase": ws.state["phase"],
                                "limit": "Integrity is not evidence of semantic quality or completed execution"})
        return 0
    except (StateDyneError, OSError, UnicodeError, ValueError, KeyError) as exc:
        print(f"StateDyne: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
