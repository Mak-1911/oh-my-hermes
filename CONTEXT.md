# oh-my-hermes

Shared language for the boundary between OMH and Hermes Agent. Agents keep
confusing which product owns which surface; these terms pin the identity down.
Product direction lives in `docs/DIRECTION.md`; the operating contract lives in
`AGENTS.md`. This file is a glossary only.

## Language

### Products

**OMH (oh-my-hermes)**:
This repo — a deterministic wrapper orchestration layer installed next to
Hermes Agent: skill catalog, router, prepared-handoff generator, and
metadata-only status surfaces. Makes no LLM, API, or network calls.
_Avoid_: Hermes plugin (that is one distribution surface, not the product),
coding executor, Hermes patch

**Hermes Agent**:
Nous Research's agent product that OMH integrates with — a separate codebase
installed on the user's machine (typically under `~/.hermes/hermes-agent`).
OMH never modifies its code and does not vendor it.
_Avoid_: Hermes runtime (that names an OMH executor path), our agent

### State roots

**Hermes home**:
`$HERMES_HOME`, default `~/.hermes` — Hermes Agent's own state root. OMH only
adds managed, explicitly installed artifacts under it (`plugins/omh`,
`tui-widgets/`).
_Avoid_: using it for OMH runtime state

**OMH home**:
`$OMH_HOME`, default `~/.omh` — OMH's state root; the runtime metadata the HUD
reads lives here.
_Avoid_: `.omh` inside a repo (that is not a thing), Hermes home

### Hermes terminal surfaces

**Classic TUI**:
Hermes Agent's Python prompt_toolkit terminal UI — what plain `hermes` runs.
It does not load user widget files; its extension point is wrapper-CLI method
hooks.
_Avoid_: treating it as the surface OMH widgets render in

**Modern TUI**:
Hermes Agent's TypeScript terminal UI — what `hermes --tui` runs. Loads user
widget apps from `$HERMES_HOME/tui-widgets/*.mjs`. The only Hermes surface
that renders OMH's status widget.
_Avoid_: ui-tui (internal directory name), dashboard TUI

**Widget zone**:
A named slot in the Modern TUI layout where an ambient widget app renders.
`dock-top` sits above the prompt input (below the top status rule);
`dock-bottom` sits below the prompt input (above the bottom status rule).
_Avoid_: assuming dock-bottom means above the input

### OMH surfaces inside Hermes

**OMH plugin**:
The Python bundle OMH distributes into `$HERMES_HOME/plugins/omh` — Hermes
tools, hooks, and the runtime reader. A managed copy of `src/plugin_bundle/omh`,
never a symlink.
_Avoid_: equating it with OMH itself

**OMH status widget**:
`omh-status.mjs`, the managed Modern-TUI widget app OMH installs into
`$HERMES_HOME/tui-widgets/`. Renders the HUD payload in the `dock-bottom`
zone — below the prompt input.
_Avoid_: statusline (that is a different, host-owned surface), HUD (the widget
renders the HUD payload; it is not the payload)

**HUD payload**:
The metadata-only JSON projection built by `read_omh_hud()` from OMH home and
Hermes home. Status narration, never execution, review, CI, merge, or
token-usage evidence.
_Avoid_: runtime state (the payload is a read-only projection of it)

**Prepared handoff**:
OMH's output contract for coding work — a payload a coding owner may execute
later. Preparing one is not dispatch, execution, review, CI, or merge
evidence.
_Avoid_: run, execution, delegation result
