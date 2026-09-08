# kkirikkiri-codex

Codex marketplace package for the curated `kkirikkiri` workflow (synced to upstream kkirikkiri 0.26.0).

Included skills:
- `kkirikkiri` — Assembles a Codex-native agent team (Agent Teams or a deterministic Workflow spec) with cut-line diagnosis, user-chosen model tiers, shared memory and bounded delegation.

Included tooling (`scripts/`, run with `node`):
- `wf-lint.js` — Workflow spec lint (R1~R7 + model-selection cross-check)
- `card-lint.js` — teammate card boundary-block lint (C1~C5)
- `done-gate.js` — completion gate (change evidence or per-file no-change review, completion contract)
- `model-selection.js` — approved model map validator
- `prepare-team.js` — opt-in Teams preparation pilot
- `run-cli.sh` / `run-cli-job.js` / `run-cli-worker.js` — external CLI workers (codex / antigravity / gjc / grok)

Packaging notes:
- Codex plugins have no declarative hooks, so the gates the upstream plugin enforces via hooks are expressed in `SKILL.md` as explicit steps the orchestrator runs itself.
- Upstream `check-env` (host installation check for a different CLI) and hook scripts are not shipped.
- Non-runtime source notes are excluded from the packaged plugin.
