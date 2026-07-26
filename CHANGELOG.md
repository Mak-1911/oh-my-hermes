# Changelog

All notable changes will be documented here.

## 1.0.3 - 2026-07-26

- Added a `/omh` meta-router gateway skill with live-catalog routing, four Hermes setup-guide skills, and a generated full-catalog index reference so Hermes can discover the workflow surface from chat.
- Added an `omh-` display prefix to generated skill frontmatter, so a Hermes status line shows `omh-ultrawork` instead of a bare name that could belong to any skill, and made echo-back of those display names route correctly.
- Bounded the deep interview: every question now carries a `Round {n}/6` header with a clarity percentage over three fixed dimensions, and the interview stops on resolution, an explicit user stop, or the round budget.
- Reworked coding delegation around request-led states: coding route next actions split into four states, named coding-agent delivery takes precedence over advisor and feedback lanes, and setup asks one question with usage-time owner delegation.
- Added an opt-in local dispatch bridge that executes fan-out contracts in parallel against a deterministic merge contract, plus executor-scoped handoff validation.
- Made messenger rendering honor the render-profile contract on the chat route-hint path, which is the only limited-rendering path for the Hermes platforms that are not named individually, and made a present-but-unsafe body warn instead of passing silently.
- Surfaced wrapper degradation to chat users instead of dropping it at the wrapper, and taught progress reporting to detect claim/observation mismatches rather than only exempting them.
- Added an `omh doctor` advisory lane for the costliest Hermes misconfigurations, including noticing when the plugin is installed but disabled.
- Added a pinned Ruff static-analysis gate to CI and contributor docs, and a self-checking broad-exception policy gate.
- Cut repeated common-rail context in generated skills and bounded prompt, capability, stdout, and status payload budgets so shared context does not become prompt bloat.
- Defaulted skill-pack install to a core profile with opt-in full, and added a reconcile path from full back to core.
- Defaulted all setup and CLI output to English; localization is explicit opt-in through `--language` or `OMH_LANG`.
- Retired OMH worktree creation in favor of native Hermes and Git tooling.

## 1.0.2 - 2026-07-01

- Added stronger Hermes chat routing, workflow picker, direct-answer, file-lookup, and operator fast paths for common English and Korean requests.
- Added localized chat-card framing and release gates for localized copy, router fast paths, Hermes UX quality, routing precision, context brief coverage, route-hint alignment, and release evidence bundles.
- Added richer plugin, MCP, menu bar, codegraph, workflow-learning, source-finder, paper-learning, and worktree/session observation surfaces while preserving metadata-only evidence boundaries.
- Modernized the public site, README workflow presentation, docs, generated skill guidance, role context, and release readiness instructions around the Hermes-native wrapper contract.

## 1.0.0 - 2026-06-09

- Added the initial `omh` installer and Hermes skill workflow pack.
- Added a direct `src/` package layout for future growth.
- Added generated routing catalog and rendered skill content.
- Added open-source project operations files and GitHub templates.
