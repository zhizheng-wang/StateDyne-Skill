# StateDyne 0.1.0 (MVP) — publication, paths and compatibility

**Publication candidate, structural checks only.** A single `SKILL.md` cognitive core is assembled into four ZIP layouts:

- Skill install: root `SKILL.md`, supporting `references/`, `agents/`, runtime and other required files (excludes tests, CI and history).
- Agent skill: one top-level `statedyne/` folder containing the byte-identical install profile for the OpenAI Skills API and other single-folder importers.
- Plugin install: root `plugin.json`, `skills/statedyne/SKILL.md` and byte-identical skill contents to the skill ZIP. This follows the portable Agent Plugins manifest-directory layout; plugin import and `@StateDyne` discovery require a compatible host.
- GitHub source: `statedyne/SKILL.md`, complete sources and tests, engineering original, archived entry and verification reports.

Every distribution contains exactly one active SKILL.md and no second historical skill entry. The publishable repository carries the four generated archives and their SHA-256 manifest under `downloads/`; the validator checks archive paths, CRC, file count, size limits, expected entry location and source-byte identity. The earlier 10.31 stale version reference in `agents/openai.yaml` has been replaced with a versionless invocation of the current full-strength skill. No 'light reasoning' alternative is shipped.

The release preserves the original method manuscript bytes and engineering archive, Apache-2.0 and author attribution; synthetic tests do not reproduce private conversation cases. Release source manifests track exact byte identity and repository link targets. SHA-256 archive digests are in the separately emitted `StateDyne-0.1.0-SHA256.txt`.

## Final bridge audit

Material environment gaps (including worker-reported unknowns with no separate exploratory opportunity) now enter environment-specific investigation; ordinary new relations receive immediate model-research priority. Attempted-with-no-increment work persists as a conditional limitation without misleading fresh expansion invitations. Small work budgets fairly rotate research lanes. Original method, current point/action quality and common cognitive entry standards remain untouched.

## Independent multi-agent outcome competition

The work was already multi-agent in capable `@` hosts; this version does **not** claim to invent multi-agent support. Instead an extra real isolated judgment compares worker-originated causal and intervention paths. Strong minority insights must appear as genuine explanation/conditional disagreement, or have an actual visible reason for rejection. A nonduplicate self-researchable route can return to the scheduler. No novelty is forced. See `verification/WORLD_CLASS_ACCEPTANCE.md` for the *unperformed* empirical benchmark.

## Release verification

**575/575 deterministic tests** passed across four isolated groups. Byte inventory, source manifests and archive cross-format equality verified by the build/validation commands. An actual ChatGPT/portable-plugin upload has not been observed, so a server-side HTTP 500 or host-specific policy cannot be excluded. Actual independent-model, web-search, persistence and parallel worker execution require host tools and user permissions. No semantic superiority is claimed from passing these tests.
