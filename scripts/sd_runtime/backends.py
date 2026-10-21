"""Actual model transport and a host-native job bridge.

API mode makes independent Responses requests; native mode never pretends to
spawn a worker. It pauses until a host executes the immutable job and submits a
receipt. A host receipt is an attestation, not cryptographic proof of isolation.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import threading
import time
from urllib import error, request as urllib_request
from .common import StateDyneError, digest, loads, read_json, save_json, utc_now
from .evidence import EvidenceTools, TOOL_DEFINITIONS
from .schemas import validate

BUDGET_LOCK = threading.Lock()


def write_result(root: Path, job: dict, output: dict, *, kind: str, worker_ref: str,
                 actual_model: str, exposed=None, usage=None, response_ids=None,
                 elapsed=0.0, independent_context=True, web_research=None, web_research_leads=None):
    validate(output, job["schema"])
    record = {"job_id": job["id"], "input_sha256": job["input_sha256"],
              "output": output, "output_sha256": digest(output), "backend_kind": kind,
              "worker_ref": worker_ref, "actual_model": actual_model,
              "independent_context": independent_context,
              "exposed_passages": exposed or {}, "usage": usage or {},
              "response_ids": response_ids or [], "elapsed_seconds": elapsed, "completed_at": utc_now(),
              "web_research": web_research or [], "web_research_leads": web_research_leads or []}
    save_json(root / "jobs" / job["id"] / "result.json", record)
    return record


class NativeBackend:
    kind = "native"

    def __init__(self, root: Path, sources: dict, config: dict):
        self.root, self.sources, self.config = root, sources, config

    def execute(self, job: dict):
        path = self.root / "jobs" / job["id"] / "result.json"
        if path.exists():
            return read_json(path)
        # request.json was created by the controller. Never fill it ourselves.
        return None

    def submit(self, job: dict, output: dict, *, input_sha: str, worker_ref: str, actual_model: str,
               independent_context: bool):
        if input_sha != job["input_sha256"]:
            raise StateDyneError("Submission input hash does not match the immutable worker request")
        if not worker_ref.strip() or not actual_model.strip():
            raise StateDyneError("A host worker/tool-call reference and actual model label are required")
        target = self.root / "jobs" / job["id"] / "result.json"
        if target.exists():
            raise StateDyneError("Result already exists. Do not overwrite an executed job")
        tools_path = self.root / "jobs" / job["id"] / "native-tools.json"
        exposed = read_json(tools_path)["exposed"] if tools_path.exists() else {}
        return write_result(self.root, job, output, kind="native_attested", worker_ref=worker_ref,
                            actual_model=actual_model, exposed=exposed,
                            independent_context=independent_context)

    def tool(self, job: dict, name: str, args: dict):
        folder = self.root / "jobs" / job["id"]
        path = folder / "native-tools.json"
        old = read_json(path) if path.exists() else {"exposed": {}, "receipts": []}
        tools = EvidenceTools(self.sources)
        output = tools.call(name, args)
        for sid, passages in tools.seen.items():
            old["exposed"].setdefault(sid, []).extend(passages)
        old["receipts"].extend(tools.receipts)
        save_json(path, old)
        return output


def _http_post(payload: dict, key: str, timeout: int) -> dict:
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    req = urllib_request.Request("https://api.openai.com/v1/responses", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib_request.urlopen(req, timeout=timeout) as response:
        content = response.read(16_000_001)
        if len(content) > 16_000_000:
            raise StateDyneError("API response exceeds the transport limit")
        return loads(content.decode("utf-8"))


class OpenAIBackend:
    kind = "openai_live"

    def __init__(self, root: Path, sources: dict, config: dict, *, transport=None, sleeper=time.sleep):
        if not config.get("allow_remote"):
            raise StateDyneError("Remote transmission requires explicit --allow-api authorization")
        key = os.environ.get("OPENAI_API_KEY")
        if not key and transport is None:
            raise StateDyneError("OPENAI_API_KEY is not configured. No model call has been made")
        self.root, self.sources, self.config = root, sources, config
        self.key = key or "injected-test-transport"
        self.transport = transport or _http_post
        self.sleeper = sleeper
        # A substituted transport is always test-only, even if it returns plausible IDs.
        if transport is not None:
            self.kind = "fixture"

    def _reserve(self):
        with BUDGET_LOCK:
            path = self.root / "api-ledger.json"
            ledger = read_json(path) if path.exists() else {"requests_attempted": 0}
            if ledger["requests_attempted"] >= self.config["max_api_requests"]:
                raise StateDyneError("API request budget exhausted; this is not a completed cognitive task")
            ledger["requests_attempted"] += 1
            save_json(path, ledger)

    def _request(self, payload: dict):
        for attempt in range(self.config["max_retries"] + 1):
            self._reserve()  # Retries and tool continuations also consume the budget.
            try:
                return self.transport(payload, self.key, self.config["timeout_seconds"])
            except error.HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if not retryable or attempt >= self.config["max_retries"]:
                    raise StateDyneError(f"OpenAI HTTP {exc.code}; no alternate model was substituted") from exc
                wait = min(2 ** attempt, 8)
                header = exc.headers.get("Retry-After", "") if exc.headers else ""
                try:
                    wait = min(max(wait, float(header)), 30)
                except ValueError:
                    pass
                self.sleeper(wait)
            except (error.URLError, TimeoutError, OSError) as exc:
                # Unknown delivery/charging status: do not automatically duplicate this POST.
                raise StateDyneError("API connection failed or timed out. Request delivery/charging is unknown; no automatic network retry or model substitution") from exc
        raise StateDyneError("Transport retry budget exhausted")

    def execute(self, job: dict):
        path = self.root / "jobs" / job["id"]
        if (path / "result.json").exists():
            return read_json(path / "result.json")
        if (path / "failure.json").exists():
            raise StateDyneError(f"{job['id']}: previous attempt failed; use the explicit retry command rather than silently repeating the sample")
        started = time.monotonic()
        tools = EvidenceTools(self.sources)
        messages = [{"role": "user", "content": json.dumps(job["inputs"], ensure_ascii=False)}]
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        ids, transcript, web_actions, web_leads = [], [], [], {}
        # The hosted tool is an explicit API opt-in, not a local web crawler.
        allow_web = bool(self.config.get("web_search_enabled")) and (
            job["role"] in ("discovery", "reframe", "contrast_probe", "environment_scout", "system_map", "system_reconcile", "delta_integrate", "delta_challenge",
                            "evidence_scout", "frontier_scout", "entry_repair") or
            job["role"] in ("acquire", "environment", "transfer", "predict", "deepen") or
            (job["role"] == "operation" and job["inputs"].get("operation") in
             ("acquire", "environment", "transfer", "predict", "deepen", "reframe")))
        try:
            for turn in range(self.config["max_tool_rounds"] + 1):
                payload = {"model": job["model"], "instructions": job["instructions"], "input": messages,
                           "store": False, "include": ["reasoning.encrypted_content"], "max_output_tokens": self.config["max_output_tokens"],
                           "text": {"format": {"type": "json_schema", "name": f"statedyne_{job['schema_name']}",
                                                "schema": job["schema"], "strict": True}},
                           "tools": TOOL_DEFINITIONS + ([{"type": "web_search", "search_context_size": "high"}] if allow_web else [])}
                if allow_web:
                    payload["include"].append("web_search_call.results")
                if self.config.get("reasoning_effort"):
                    payload["reasoning"] = {"effort": self.config["reasoning_effort"]}
                response = self._request(payload)
                rid = response.get("id")
                if not isinstance(rid, str) or not rid:
                    raise StateDyneError("API response has no request identity")
                ids.append(rid)
                measured = response.get("usage") or {}
                for key in usage:
                    value = measured.get(key, 0)
                    if isinstance(value, int):
                        usage[key] += value
                output = response.get("output", [])
                # Preserve reasoning items in-memory for protocol continuation only;
                # never collect private reasoning in the persistent audit trail.
                observable = [item for item in output if item.get("type") != "reasoning"]
                # Preserve independently inspectable URLs and actual search actions.
                # Citations/returned excerpts are leads, NOT proof that the controller
                # fetched and authenticated the complete source document.
                if allow_web:
                    for item in output:
                        if item.get("type") == "web_search_call":
                            web_actions.append({"id": item.get("id"), "action": item.get("action"),
                                                "status": item.get("status")})
                            for hit in item.get("results", []) or []:
                                if isinstance(hit, dict) and isinstance(hit.get("url"), str):
                                    url = hit["url"]
                                    if url.startswith(("http://", "https://")):
                                        web_leads[url] = {"url": url, "title": hit.get("title", "")}
                        if item.get("type") == "message":
                            for part in item.get("content", []):
                                for ann in part.get("annotations", []):
                                    if ann.get("type") != "url_citation":
                                        continue
                                    info = ann.get("url_citation", ann)
                                    url = info.get("url")
                                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                                        web_leads[url] = {"url": url, "title": info.get("title", "")}
                transcript.append({"response_id": rid, "status": response.get("status"),
                                   "model": response.get("model"), "observable_output": observable,
                                   "usage": measured})
                save_json(path / "transport.json", {"kind": self.kind, "calls": transcript,
                                                     "tool_receipts": tools.receipts, "web_actions": web_actions,
                                                     "web_citation_leads": list(web_leads.values())})
                if response.get("status") != "completed":
                    raise StateDyneError(f"API response is {response.get('status')!r}, not completed; truncated/refused outputs are not accepted")
                for item in output:
                    if item.get("type") == "message":
                        if any(c.get("type") == "refusal" for c in item.get("content", [])):
                            raise StateDyneError("The model refused this job; no synthetic answer was substituted")
                calls = [item for item in output if item.get("type") == "function_call"]
                if calls:
                    if turn >= self.config["max_tool_rounds"]:
                        raise StateDyneError("Tool-round budget exhausted")
                    messages.extend(output)
                    for item in calls:
                        call_id = item.get("call_id")
                        if not call_id:
                            raise StateDyneError("Function call has no call_id")
                        args = loads(item.get("arguments", "{}"))
                        definitions = {t["name"]: t for t in TOOL_DEFINITIONS}
                        name = item.get("name", "")
                        if name in definitions:
                            try:
                                validate(args, definitions[name]["parameters"])
                                result = tools.call(name, args)
                            except StateDyneError as exc:
                                result = {"error": str(exc)}
                        else:
                            result = {"error": "Tool is not allowlisted"}
                        messages.append({"type": "function_call_output", "call_id": call_id,
                                         "output": json.dumps(result, ensure_ascii=False)})
                    save_json(path / "transport.json", {"kind": self.kind, "calls": transcript,
                                                         "tool_receipts": tools.receipts, "web_actions": web_actions,
                                                     "web_citation_leads": list(web_leads.values())})
                    continue
                text = "".join(c.get("text", "") for item in output if item.get("type") == "message"
                               for c in item.get("content", []) if c.get("type") == "output_text")
                if not text.strip():
                    raise StateDyneError("API response contains no observable JSON output")
                # Exact returned text is retained even when it fails parsing.
                from .common import atomic_write
                atomic_write(path / "raw-output.txt", text)
                product = loads(text)
                validate(product, job["schema"])
                return write_result(self.root, job, product, kind=self.kind, worker_ref=ids[0],
                                    actual_model=response.get("model") or job["model"], exposed=tools.seen,
                                    usage=usage, response_ids=ids, elapsed=time.monotonic() - started,
                                    web_research=web_actions, web_research_leads=list(web_leads.values()))
        except (StateDyneError, ValueError, TypeError, KeyError) as exc:
            save_json(path / "failure.json", {"error": str(exc), "response_ids": ids,
                                              "kind": self.kind, "usage": usage, "time": utc_now()})
            raise StateDyneError(f"{job['id']} ({job['role']}): {exc}") from exc
        raise StateDyneError("Model did not return a completed work product")
