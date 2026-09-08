# docs-guide-codex

Codex marketplace package for the `docs-guide` skill.

Included skills:
- `docs-guide` — Fetches and explains official documentation using an `llms.txt`-first strategy and official-source fallbacks.

Packaging notes:
- The package keeps the known-site index and fallback strategy references because they are part of the retrieval logic.
- Tracks upstream `docs-guide` 1.4.4 (retrieval logic, spec-level drill-down, references). Upstream first-run setup/star prompt and update-notifier hook are intentionally not ported.
