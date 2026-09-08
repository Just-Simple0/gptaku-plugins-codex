# insane-search-codex

Codex marketplace package for the `insane-search` skill — a resilient public-content reader for
blocked / WAF-heavy URLs. No API keys, no proxy setup.

Included skills:
- `insane-search` — generic WAF-profile fetch chain (curl_cffi TLS impersonation, mobile URL
  transforms incl. `m_prefix_subdomain` for portal hosts, local Playwright / patchright / nodriver
  fallback) plus Phase 0 platform routes (Reddit `.rss`, X tweet-result / syndication, YouTube via
  yt-dlp, Threads inline video, Jina, public APIs) and 12 platform/diagnostic references.
  Engine and references track the upstream plugin at **v0.16.3**, ported to Codex idiom.

What the engine adds on top of a plain fetch (upstream 0.9 → 0.16):
- Markdown-by-default content (`markdownify`), opt-in main-content extraction (`--maincontent`),
  PDF text via pdfplumber/pypdf (lazy-loaded), JSON-LD / rendered-innerText rescue for thin SPA shells.
- Transient-status retry on the probe (429/502/503/504, `Retry-After` honoured, 10s cap) and
  `block_class` (`bot_detection` vs `infra_or_auth`) on failure.
- Per-host self-learning of the route that last worked (`~/.insane_search/learned.json`).
- Untrusted-content envelope (`[BEGIN/END UNTRUSTED WEB CONTENT]` with boundary id),
  `--json-content` for metadata + trace + wrapped body in a single fetch, credential masking in
  URLs that reach logs/trace, fail-closed browser envelope parsing.
- X keyword discovery without paid APIs: `python3 -m engine.x_search "<kw>"` (Brave + Yahoo,
  optional xAI `x_search`, every URL revalidated through tweet-result).
- Node deps for the browser fallback auto-install once into `~/.insane-search/node`; browser lanes
  run headful by default; `protocol_stealth_chrome` (nodriver → patchright) for gates that
  fingerprint the automation protocol.

Entry points:
- `bash scripts/run_engine.sh "<URL>" [--selector "<CSS>"] [--device auto|desktop|mobile] [--trace] [--json-content]`
  (= `python3 -m engine "<URL>" ...`)
- `python3 -m engine.x_search "<keyword>" --limit 10` — X keyword discovery + tweet-result validation
- `bash scripts/bootstrap.sh [--install]` — check / install Python + Node prerequisites
- `bash scripts/smoke_test.sh` — bias linter + offline smoke tests (run after touching `engine/**`)

Packaging notes:
- Harness rules R1–R6 and R8, the Phase 0→3 scheduler, 4-layer validation, and the No-Site-Name rule
  are all carried over in `skills/insane-search/SKILL.md`. The former R7 recon branch and internal
  API discovery were removed upstream (0.14.0) and are not shipped here either.
- Platform-hook features of the upstream plugin (first-run setup prompt, update notifier) have no
  Codex plugin primitive and are intentionally not ported.
- Where the upstream skill drives a session browser tool, this port says "use the assistant's
  browser tool if available, otherwise report the limit and continue with the engine's local
  Node template / Jina / archive / platform API routes".
- The engine test files run under both `pytest` and direct script execution
  (`test_u5.py` needs `PYTHONPATH=.` when run directly).
