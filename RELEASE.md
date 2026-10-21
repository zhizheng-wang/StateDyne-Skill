# StateDyne 11.3.0 — Multi-agent outcome tournament release

**Research architecture:** existing genuine parallel workers are preserved. After evidence and premise review, a separate outcome tournament compares structurally different generated pathways, including strong minority findings, against the user's protected objectives, implementation feasibility, best mature alternative and no-action baseline. Pivotal recommendations and serious dissent must receive actual user-visible treatment. A new obtainable, decision-reversing relation can re-enter autonomous research before composition. This is neither a majority vote nor a novelty quota.

**Release caveat:** deterministic tests cover execution contracts, worker receipts and synthetic failure cases. They do not show actual superior creativity, user value, external research accuracy or host `@` feature behavior. Host tool permissions and agent execution must be verified in practice.

## Prior 11.2.1 engineering release

**Release scope:** final authored skill and engineering package. Deterministic tests can verify structural invariants; real-model superiority, host permissions and live import results remain empirical questions.

## Final 11.2.1 bridge corrections

- All fresh, material relations from any worker now compete for immediate research; environment/selection relationships route to dedicated environmental investigation rather than generic model restatement.
- Environment scouts' material unknowns enter the same inquiry route even when no separate opportunity record was created; research attempts are not misrepresented as acquired evidence.
- Attempted/no-increment leads remain stored with their conditional limitations but do not become fresh user-facing expansion suggestions. New primary evidence can reopen them.
- Bounded parallel batches fairly rotate model, environment and evidence work. Current front-stage intervention quality and cross-host cognitive contract remain intact.

## What was corrected at the root of delivery

- Every visible intervention point now needs separate exact-answer anchors for its causal leverage, **incremental value over doing nothing**, and reason it outranks a serious competitor. Merely filling a backend audit row cannot pass.
- When points interact, the actual response must explain how a joint, substitute or conditional relationship creates a different outcome from the individual points. The independent reviewer evaluates that explanation. The controlled runtime rejects a missing visible explanation.
- Newly delivered plans receive an action-composition review linking every included action to the plan and requiring visible dependency/sequence **and** net gain vs best single action/no additional activity. No synergy is invented solely to satisfy formatting.
- Natural-language `@`, `$`, implicit and supported API invocations share the **same cognitive and visible-delivery criteria**. `agents/openai.yaml` no longer embeds a stale version or a different standard. The same `SKILL.md` is reused byte-for-byte in every release distribution.
- Source-grounded continuation remains available after analysis, point choice, action or plan; a small detour does not erase the main phase. No empty suggestion is required when the user clearly asks for a closed direct answer.

## Distributions

- **Skill-install ZIP**: single root `SKILL.md`, runtime and current references. Use with a supported skill importer.
- **Agent-skill ZIP**: one top-level `statedyne/` folder containing the same installable files. Use with the OpenAI Skills API or another importer that requires a single top-level skill directory.
- **Plugin ZIP**: current portable Agent Plugins layout (`plugin.json`, `skills/statedyne/SKILL.md` and the exact same skill files). This package is for **plugin import/`@` discovery** on compatible hosts. It is not an MCP server and grants no new tools.
- **GitHub ZIP**: source repository in top-level `statedyne/` including tests, engineering archives, all required current references and CI.

The publishable repository includes all four archives under `downloads/` with a SHA-256 manifest. Archive validation enforces one active `SKILL.md`, case-insensitive path uniqueness, safe relative paths, OpenAI upload size/count limits and byte identity of the cognitive skill across layouts. These checks do not constitute a successful remote upload.

A tool-free host can still attempt every cognitive search under the same standards, but it cannot actually parallelize ten independent model calls or search data it cannot access. Do not claim full tool parity without real execution.

## Verify

From the repository root:

```bash
python scripts/validate_skill.py --strict-bytes
python scripts/run_test_groups.py
```

These tests do not call a live model or establish empirical discovery superiority. Before public plugin directory submission, host-side upload/review and any publishing permissions still apply.
