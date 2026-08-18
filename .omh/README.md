# `.omh/` — oh-my-hermes repo-local artifact store

This directory is where **oh-my-hermes (OMH)** records durable, repo-scoped
artifacts when a command that produces one runs inside a repository. It is a
data store, not code: nothing in here executes.

## What lands here

| Path | Written by | Contents |
| --- | --- | --- |
| `plans/<slug>.md` | `omh hermes plan --record` | Recorded implementation plans (the `ralplan` / `ulw-plan` recording path) |
| `plan-variants/` | `omh hermes plan-variant` | Alternative plan drafts |
| `research/<slug>/` | research workflows | Research dossiers, syntheses, manifests |
| `coding/dynamic-workflows/` | `omh coding dynamic-workflow` | Prepared workflow contracts and charts |

Outside a repository the same commands write to the user-scope OMH home
(`~/.omh`) instead.

## Commit policy

Repo-local `.omh/` contents are **operational artifacts, ignored by
default** — in user projects OMH drops a `.omh/.gitignore` (`*`) so
`git add -A` never sweeps them in; in this repository the top-level
`.gitignore` lists `.omh/`. Committing an artifact (for example a reviewed
proposal worth keeping) is an explicit decision: `git add -f` it. Files that
are already tracked stay tracked — gitignore only hides untracked files.

## Do not confuse with the neighbouring roots

Several agent products keep look-alike dot-directories. They are different
products with different owners; never write one product's state into
another's root.

| Root | Product | Notes |
| --- | --- | --- |
| `.omh/` | **oh-my-hermes** (this product) | Repo-local artifacts, described above |
| `~/.omh/` | oh-my-hermes user scope | Skills, runtime state, HUD/todo stores |
| `~/.hermes/` | **Hermes Agent** (the host) | Hermes' own home: `config.yaml`, `state.db`, `plugins/`, `tui-widgets/`. The installed OMH **plugin** lives at `~/.hermes/plugins/omh/` and the OMH TUI widget at `~/.hermes/tui-widgets/omh-status.mjs` — both are OMH-managed installs *into* Hermes' home, refreshed only through `omh update`, never by hand-copying. OMH never patches Hermes itself (`~/.hermes/hermes-agent/`). |
| `.hermes/` (repo-local) | Hermes Agent | Rare repo-scoped Hermes state; not OMH's |
| `.omc/` | oh-my-claudecode | A different wrapper (Claude Code); OMH never writes here |
| `.omo/` | oh-my-opencode | A different wrapper (OpenCode). OMH only *reads* `~/.omo/omo.json[c]` to import category model preferences; it never writes `.omo/` |
| `.loop/` | loop runtimes | Not OMH's |

If an agent proposes writing a plan, todo, or any state into `.omc/`,
`.omo/`, or `~/.hermes/hermes-agent/`, that is state-root drift — the same
class of bug fixed in #1017 (plans written to `.omc/`) and #1021 (plans
committed under `.omo/`). The correct target is always this directory (via
the named `omh` commands) or the OMH home.
