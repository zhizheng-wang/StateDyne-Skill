# StateDyne

**A unified method for understanding reality and changing reality.**  
**理解现实、改变现实的统一元方法**

StateDyne is an open-source Agent Skill for difficult, open-ended problems. It helps an AI system identify the user's real objective, investigate competing explanations, discover overlooked causal relationships, seek evidence, challenge its own conclusions, and choose **where** to intervene before deciding **what** actions to take.

It is designed for research, strategy, learning, organizational decisions, product design, policy, and other situations where a plausible answer is not enough. You can use it with natural language; you do **not** need to learn StateDyne terminology first.

[中文首页](README.md) · [Method (Chinese)](references/method.zh-CN.md) · [Engineering guide](engineering/guide.md) · [Changelog](CHANGELOG.md)

## What it does

- **Investigate before committing.** Separate observations, assumptions, causal interpretations, alternatives, and uncertainties. Seek sources and discriminating evidence when tools permit.
- **Discover beyond the prompt.** Search across systems, history, stakeholders, environments, selection mechanisms, and domains; generate testable, *not-yet-reported* consequences without inventing facts.
- **Make independent findings compete on outcomes, not votes.** A distinct real worker compares the ordinary incumbent with minority causal mechanisms and new feasible routes; decisive new evidence can reopen research before the answer is drafted. Strong minority findings cannot silently vanish into a generic summary.
- **Keep an information loop.** Incorporate corrections and new evidence into the parts of the model and research plan they actually affect.
- **Design effective change.** Compare causal intervention points, feasibility, alternatives and combinations; store possible actions separately and preserve analysis → intervention points → actions → plan as separate auditable outputs, but deliver points and concrete actions together when the user asks for actionable help.
- **Preserve the user's values.** Clarify goals, real constraints, risks, and important tradeoffs rather than silently replacing the user's objective.
- **Audit consequential conclusions.** Check source period, geography, units, counterfactuals and whether multiple required conditions hold for the **same** outcome or entities.
- **Keep difficult questions alive across turns.** Recover an active goal after digressions, short corrections or refusal to share private details, without treating every question as a fresh task. Before closing an open-ended decision, independently challenge whether a substantially better objective or solution family was overlooked.

There is no fixed cap on questions, exploration rounds, or worthwhile intervention points. Research quality takes precedence over speed.

## Distribution formats and uniform execution

This project releases three install layouts with byte-identical skill contents: a direct **Install ZIP** with `SKILL.md` at the archive root, an **Agent Skill ZIP** with one top-level `statedyne/` folder, and a **portable Plugin ZIP** with root `plugin.json` and `skills/statedyne/`. Use the layout required by the actual importer; for source installation or cloning use this GitHub directory. A plugin manifest does **not** grant browsing, independent-agent or persistent-state tools. The same research, intervention and review standards apply wherever the skill is loaded.

[Direct Install ZIP](downloads/StateDyne-0.1.0-Install.zip) · [Agent Skill ZIP](downloads/StateDyne-0.1.0-Agent-Skill.zip) · [Plugin ZIP](downloads/StateDyne-0.1.0-Plugin.zip) · [SHA-256](downloads/StateDyne-0.1.0-SHA256.txt)

**Intervention quality:** each important point must explain the actual generating relationship, why changing it adds net value, and why it outranks a real competing point. When two points interact, their separate and combined effects must be shown. A plan must explain how its constituent actions work together and whether that is better than the best single action. User-visible reasons cannot be replaced by a hidden audit.

## Install

The canonical skill directory is **`statedyne/`**, containing `SKILL.md`, `references/`, `scripts/`, and supporting files.

**From this repository:** clone it as `statedyne`, or download the Agent Skill archive and extract the `statedyne/` folder. Place that complete directory in the skills location supported by your AI host and enable it using that host's UI or tooling. If an upload UI expects `SKILL.md` directly at ZIP root, upload the Direct Install ZIP instead. Do not use the complete source repository as the direct-upload package unless that importer explicitly accepts source trees.

**OpenAI Codex example** (if using the default skills directory):

```bash
# From a cloned repository root named statedyne
mkdir -p ~/.codex/skills
cp -R . ~/.codex/skills/statedyne
```

For ChatGPT and third-party harnesses, follow their supported skill-installation process; `@StateDyne` / `$statedyne` naming and tool availability are host-dependent. Installing this ZIP **does not** create autonomous subagents, browsing access, persistent storage, or API credentials.

## Use

Ask naturally, for example:

> Analyze why a product pilot performed well but customers did not adopt it. Find important explanations I may have missed, investigate the evidence available, and explain which intervention points would have the most value.

> Research whether our proposed policy can achieve its stated outcome within five years, subject to budget and safety constraints. Distinguish actual net effect from activity measures.

**Conversations:** You can interrupt with a side question, decline optional personal questions, or say *next*, *look for a better alternative*, *pause*, or *change the goal*. With the controlled runtime, `update` routes an ordinary follow-up before changing the original research task. This behavior requires actual runtime/host integration, not just loading Markdown instructions. The model should still give a natural next step where meaningful.

**Language:** StateDyne aims to respond in the language of the user's request, unless another output language is explicitly requested. The underlying method and several internal protocols are authored in Chinese; multilingual performance depends on the model and host. You do not need to translate the skill to ask in English.

## Execution modes and limits

- **Portable skill:** `SKILL.md` and the relevant protocols guide the host model. Actual workers and tools depend on the host. The model must not pretend that a list of planned worker tasks was executed.
- **Controlled runtime:** Python modules can issue separate requests, record results and check structural contracts using supported, authorized backends. The `native` backend creates pending tasks until a compatible host actually executes and returns them; an API backend requires access and configuration.
- **Not proof of correctness:** Engineering tests and multiple simulated roles cannot establish causal truth, empirical superiority, model isolation, or real-world intervention success. Validate important advice independently before acting.

The runtime uses only the tools and access actually granted. It does not automatically take action on external accounts or execute a plan without authorization. For medical, legal, financial or other high-stakes matters, verify important facts and seek qualified human judgment as appropriate.

## Verify locally

Python 3.11+ is recommended. The deterministic checks do not call a live model:

```bash
python scripts/validate_skill.py --strict-bytes
python scripts/run_test_groups.py
python scripts/run_statedyne.py doctor
```

For example, to create an **unexecuted**, auditable first-wave batch with the native backend:

```bash
python scripts/run_statedyne.py start --backend native --task-file examples/task.txt --workdir ../statedyne-run --scope analysis
python scripts/run_statedyne.py status --workdir ../statedyne-run
python scripts/run_statedyne.py trace --workdir ../statedyne-run
```

**After a completed audited turn**, provide a new utterance in a UTF-8 text file and route it without manually tagging every digression:

```bash
python scripts/run_statedyne.py update --workdir ../statedyne-run --source-file ../follow-up.txt
python scripts/run_statedyne.py advance --workdir ../statedyne-run
```

With `native`, the host must actually execute pending workers and submit their receipts for the turn to complete. New independent alternative-value discovery adds a genuine worker job before a primary response can be declared complete; it does **not** prove novel conclusions exist. User-controlled pause/close and safety limits remain in effect.

That flow prepares requests; it does **not** mean the agents have run. Keep private work directories outside the repository.

## Project status and provenance

- Version: **0.1.0 (MVP)**, distributed as a direct-root skill ZIP, a single-folder Agent Skill ZIP, a portable plugin ZIP, and complete GitHub source.
- License: **Apache-2.0**. Author: **Zhizheng Wang / 王之政**.
- Methodology and original execution specification are archived in the repository, with identity hashes in `references/source-map.json`.
- Public test fixtures are synthetic. Previous engineering tests cover structural contracts, not real-model outcome quality. See [`verification/REPORT.md`](verification/REPORT.md) and [`verification/PUBLICATION_REPORT.md`](verification/PUBLICATION_REPORT.md).
- Private case transcripts, evaluation answers, runtime traces, credentials and local user data are **not bundled**.

For bugs or proposed changes, see [Contributing](CONTRIBUTING.md) and [Security](SECURITY.md).

## 11.1 install / workflow compatibility

For an upload surface that expects `SKILL.md` at archive root, use the dedicated **Install ZIP**. For the OpenAI Skills API or another surface that requires one top-level skill folder, use the **Agent Skill ZIP**. The full GitHub ZIP has a single `statedyne/` parent folder and also contains tests and engineering archives; publish that folder's **contents** as repository root rather than treating it as the normal direct-upload package. Never install the `engineering/history` materials as separate skills. Structural validation cannot guarantee a remote service response. Portable Markdown execution and controlled Python execution have identical quality goals but different actually available tools. Read `RELEASE.md` and `references/breakthrough-engine.md`.

### 11.0.0 architecture additions

The governing cycle is now **goal and current reality → differentiated mechanisms / independent competition → autonomous evidence → re-evaluation and changed interventions → visible continuation**. Stage output and continued discovery are different things; the research agenda does not vanish after a plan or when the user asks a small unrelated question. Primary goal alternatives are examined before the final scheduling decision and cannot be selected without the user. Runtime source-bound continuation offers name actual unfinished questions rather than vaguely advertising exploration. **Time-box suggestions are conditional milestones, not causally derived precise optima.** See [`references/generative-loop.md`](references/generative-loop.md), [`RELEASE.md`](RELEASE.md) and [`verification/REAL_MODEL_ACCEPTANCE.md`](verification/REAL_MODEL_ACCEPTANCE.md). All benefits must be verified by real-model tests; the deterministic suite does not prove superior insight.

### 11.1 — Outcome realization, not timeline decoration

Open-ended analysis now treats competing **ways the result is actually generated** as the primary source of useful discovery. Generic timeboxes remain optional management tools. User-tested low-burden methods and explicit refusals are respected; a one-turn request to stop discussing further research need not destroy the persistent research frontier. See [Result realization](references/result-realization.md) and [Release](RELEASE.md). This is an engineering/protocol improvement, **not** validated live-model superiority.
