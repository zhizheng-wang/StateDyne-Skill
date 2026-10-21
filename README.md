# Give It Your Hardest Problem.

**Break down any problem. Uncover hidden relationships. Create new paths forward.**

From everyday frustrations to complex real-world challenges, StateDyne helps AI go beyond answering: it investigates more deeply, discovers new possibilities, and looks for ways to change the outcome.

**English** | [中文](README.zh-CN.md)

**See what it can do.**

### 1. Why does “just do five minutes every day” fail, while the first thing you do in the morning can change your entire day?

**The real leverage is not five more minutes of persistence. It is putting the day into a different state.**

Make real progress first thing in the morning → progress creates new questions and momentum → continuing becomes easier → the next start requires less effort.

**You may change only one morning choice, yet affect the rest of the day.**

Waking from a nap or finishing dinner can create the same kind of turning point for what follows.

### 2. Why do you forget something moments after remembering that you need to do it?

**Not writing it down does not save effort. It accepts the risk of forgetting.**

Working memory is limited. As new information enters, older information can disappear.

You may think you are trying to remember, while actually making your mind carry a risk that could have been avoided.

**What needs to change is not your memory, but how the information is preserved.**

### 3. Why can you feel physically exhausted yet become less able to sleep the harder you try?

**Fatigue is not the same as sleepiness, and trying to sleep does not necessarily help you fall asleep.**

Work late → calculate how many hours remain → demand that you fall asleep quickly → keep checking whether you are asleep → become even less able to relax.

Sometimes, instead of forcing your mind to go blank, it is more effective to let a vague image appear and develop on its own, without controlling or completing it.

**You are trying to complete sleep as a task, but falling asleep may require leaving task mode.**

---

**StateDyne studies these overlooked generative relationships: finding where change can truly alter the outcome, rather than merely adding more ways to solve the problem.**

**Current version: 0.1.0 (MVP)**

[Install](#install) · [Try it yourself](#try-it-yourself) · [Open-source method](references/method.zh-CN.md) · [Technical guide](engineering/guide.md)

## Install

Choose the package that matches the layout expected by your importer. All three packages contain the same `SKILL.md` and the same cognitive requirements; only their outer directory structures differ.

| Your installation entry | Download | Structure after extraction |
| --- | --- | --- |
| The uploader expects `SKILL.md` at the archive root | [StateDyne-0.1.0-Install.zip](downloads/StateDyne-0.1.0-Install.zip) | `SKILL.md` is at the ZIP root |
| The OpenAI Skills API, or another importer requiring one top-level skill folder | [StateDyne-0.1.0-Agent-Skill.zip](downloads/StateDyne-0.1.0-Agent-Skill.zip) | `statedyne/SKILL.md` |
| A compatible host explicitly requiring a plugin package | [StateDyne-0.1.0-Plugin.zip](downloads/StateDyne-0.1.0-Plugin.zip) | `plugin.json` and `skills/statedyne/SKILL.md` |

If the installation screen simply says “upload a skill,” start with the **Install ZIP**. If it explicitly requires a ZIP containing one top-level skill directory, use the **Agent Skill ZIP**. Do not use the complete GitHub source archive as the normal direct-install package: it also contains tests, engineering archives, and release-verification materials.

Checksums for every download are listed in the [SHA-256 manifest](downloads/StateDyne-0.1.0-SHA256.txt). Whether `@StateDyne`, `$statedyne`, web research, independent agents, or cross-session state are available depends on the capabilities and permissions of the actual host. Installing the skill does not create those permissions.

### Install from source

The repository root is itself the complete `statedyne` skill directory and contains the single active entry point, `SKILL.md`. After cloning the repository, you may place the entire directory in a skill location supported by your host.

For example, with the default Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R . ~/.codex/skills/statedyne
```

Installation screens and invocation names vary by host. Follow the installation method currently supported by the host you use.

## Try it yourself

You do not need to learn StateDyne terminology first. After installation, describe the problem, your objective, what you already know, and the costs you truly cannot accept.

For example:

> I have already tried several common approaches, but the result did not change for long. Find the relationships that actually generate this outcome, investigate explanations I may have missed, and compare the intervention points and actions most worth pursuing.

> Why did the product pilot show strong metrics while users still failed to adopt it? Do not merely list possible reasons. Look for evidence that distinguishes competing mechanisms, then identify the highest-priority intervention points.

> Challenge our current objective and plan first. Is there a more valuable path with different implementation conditions? If the evidence is insufficient, clearly identify what remains only a conditional hypothesis.

## How it handles complex problems

- It separates observations, hypotheses, causal explanations, competing mechanisms, and remaining unknowns instead of treating one plausible story as fact.
- When tools permit, it actively researches evidence and requires new evidence to update the existing model, intervention points, or plan.
- It searches upstream and downstream in the system, across environments, history, actors, selection mechanisms, and cross-domain relationships for possibilities not stated directly in the prompt.
- It makes conventional solutions, important minority findings, new objectives, and feasible new paths compete on real outcomes rather than frequency of appearance.
- It first compares where change is most worthwhile, then explains how concrete actions would alter those positions. When a complete plan is needed, it also examines dependencies, sequence, and the added value of combining actions.
- It preserves the user's objectives, constraints, and important values. Only information that genuinely requires the user's choice is returned for a decision.
- It checks important numbers, sources, dates, regions, units, counterfactuals, and whether multiple conditions actually apply to the same outcome.
- In long-running work, it preserves completed research state. It respects an explicit request to pause, stop, or change the subject.

There is no fixed limit on questions, exploration rounds, or intervention points. The amount of work depends on unresolved differences, risks, and genuinely valuable opportunities for discovery—not on whether the problem appears ordinary or specialized.

## Open-source method and technical materials

- [StateDyne open-source method](references/method.zh-CN.md)
- [Engineering and runtime guide](engineering/guide.md)
- [Release notes](RELEASE.md)
- [Changelog](CHANGELOG.md)
- [Publication structure and compatibility report](verification/PUBLICATION_REPORT.md)
- [Engineering verification report](verification/REPORT.md)
- [Outstanding real-model acceptance criteria](verification/REAL_MODEL_ACCEPTANCE.md)

With Python 3.11 or later, you can run local checks that do not call a live model:

```bash
python scripts/validate_skill.py --strict-bytes --require-downloads
python scripts/run_test_groups.py
python scripts/run_statedyne.py doctor
```

These checks verify file identity, package structure, and deterministic execution contracts. They do not prove that a live model will produce better insights, nor do they prove that a remote installation service will accept the package. Public test materials are synthetic. Private cases, conversations, credentials, runtime traces, and local user data are not included in the repository.

## Current release

- Version: **0.1.0 (MVP)**
- License: **Apache-2.0**
- Author: **Zhizheng Wang**
- Distribution formats: direct skill ZIP, single-folder Agent Skill ZIP, portable plugin ZIP, and complete GitHub source

StateDyne applies the same cognitive standard across hosts, but it can use only the tools that actually exist and have been authorized in that host. Without real independent workers, it must not describe simulated roles as completed multi-agent research. Without network access, it must not claim to have obtained external evidence.

To report a problem or contribute an improvement, read the [contribution guide](CONTRIBUTING.md) and [security policy](SECURITY.md).
