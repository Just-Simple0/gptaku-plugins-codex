# goaljaby-codex

Codex marketplace package for the `goaljaby` skill — a PRD-to-`/goal` bridge. Current version: **0.6.3** (tracks the original goaljaby 0.6.3).

Included skills:
- `goaljaby` — Turns a PRD folder into five review documents in the user's language (VALIDATION/RECOVERY/PLAN/PROGRESS/goal-command) plus a `PLANS.md` ExecPlan, then hands off a ready-to-copy Codex `/goal` command after human approval.

## What it does

1. Read a PRD folder (manual or from `show-me-the-prd`). Detects an assumption ledger and design references (`references/` + `sources.json`) if the PRD carries them.
2. Generate six documents in `output_lang` (the language of the user's request — auto-detected, ko/en first-class with deterministic heading validation, never Korean by default): `VALIDATION.md`, `RECOVERY.md`, `PLAN.md`, `PROGRESS.md`, `goal-command.md`, and `PLANS.md` (the Codex ExecPlan with **Progress / Validation / Decision-Log** sections).
3. Enforce a 4,000-character compact on the `/goal` body (file-pointer pattern — the objective references `./PLANS.md`) with Korean+English OR protected-clause regex enforcement.
4. Show a review summary in chat (no extra file) and prepend a 4-line summary to `PROGRESS.md` and the `PLANS.md` Progress section.
5. After a mandatory approval gate (numbered-choice chat block), present a ready-to-copy `/goal` command.

**Inherited context (0.6.0+ / 0.6.2+)**: if the PRD folder carries `references/` + `sources.json` from `show-me-the-prd` v0.10+, the style keywords and kept images are inherited into PLAN.md/VALIDATION.md (with a copyright guard). If a kkirikkiri plugin is installed in the Codex plugin cache, RECOVERY.md also gets the multi-agent gate rule (boundary blocks for teammates, read-only reviewers, `wf-lint` when the installed kkirikkiri ships it) — silently skipped when kkirikkiri is absent. File names, command identifiers, and shell commands stay as-is.

## Codex vs the original edition

The original edition emits `/goal` on the assistant's last line so its host starts the goal loop on the next turn. **Codex cannot auto-emit a slash command** — so this edition ends by presenting a ready-to-copy command instead:

```
/goal Execute ./PLANS.md to completion; keep the Progress section current; stop when <verifiable done condition>
```

Codex has a native `/goal` (the `goals` feature is stable in codex 0.139) plus `/plan` mode and the `PLANS.md`/ExecPlan convention, which this package targets directly.

## Packaging notes

- Chat-first interview model (`shared/questioning-policy.md §A`) instead of any widget-based question flow.
- No hooks. The original edition's `setup/setup.sh` (first-run prompt, update check) is intentionally not ported (Codex plugins do not support hooks); the skill needs no bootstrap.
- Bundled policy excerpt at `skills/goaljaby/references/policy-excerpt.md` mirrors `shared/language-policy.md` and `shared/questioning-policy.md`.
- All paths use `$PLUGIN_ROOT`.

## License

MIT
