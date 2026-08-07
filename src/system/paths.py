from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .local_store import atomic_write_text


@dataclass(frozen=True)
class OmhPaths:
    omh_home: Path
    hermes_home: Path
    # Whether the caller named `omh_home` rather than accepting the default.
    # True by default: constructing OmhPaths directly always names one.
    omh_home_named: bool = True

    @property
    def skills_dir(self) -> Path:
        return self.omh_home / "skills"

    @property
    def manifest_path(self) -> Path:
        return self.omh_home / "manifest.json"

    @property
    def runtime_dir(self) -> Path:
        return self.omh_home / "runtime"

    @property
    def runtime_state_path(self) -> Path:
        return self.runtime_dir / "state.json"

    @property
    def runtime_runs_dir(self) -> Path:
        return self.runtime_dir / "runs"

    @property
    def runtime_efficiency_reports_dir(self) -> Path:
        return self.runtime_dir / "efficiency-reports"

    @property
    def runtime_wrapper_sessions_dir(self) -> Path:
        return self.runtime_dir / "wrapper_sessions"

    @property
    def runtime_mcp_host_sessions_path(self) -> Path:
        return self.runtime_dir / "mcp_host_sessions.jsonl"

    @property
    def runtime_plugin_host_observations_path(self) -> Path:
        return self.runtime_dir / "plugin_host_observations.jsonl"

    @property
    def runtime_worktrees_path(self) -> Path:
        return self.runtime_dir / "worktrees.jsonl"

    @property
    def runtime_journal_dir(self) -> Path:
        return self.runtime_dir / "journal"

    @property
    def runtime_journal_events_path(self) -> Path:
        return self.runtime_journal_dir / "events.jsonl"

    @property
    def runtime_external_effect_receipts_path(self) -> Path:
        # Runtime-wide, next to the observation journal, not per run: an
        # external effect belongs to the surface that acted, and adapter
        # deliveries have a session but no run.
        return self.runtime_journal_dir / "external_effect_receipts.jsonl"

    @property
    def runtime_approval_receipts_path(self) -> Path:
        # Runtime-wide, beside the external effect receipts, never inside a run
        # directory: an approval is answered by a different actor at a different
        # time from the delegation it approves, and it has to survive that
        # delegation being rebuilt.
        return self.runtime_journal_dir / "approval_receipts.jsonl"

    @property
    def runtime_blocked_work_records_path(self) -> Path:
        # Runtime-wide, beside the other two stores, and emphatically not inside
        # a run directory: the records this store exists for are minted when a
        # gate denies *before* a delegation exists, so there is no run directory
        # to hold them. Per-run storage would lose exactly the decisions that
        # have no run, which are the ones #806 asks to be explainable later.
        return self.runtime_journal_dir / "blocked_work_records.jsonl"

    @property
    def runtime_plan_context_dir(self) -> Path:
        return self.runtime_dir / "plan-context"

    @property
    def release_evidence_dir(self) -> Path:
        return self.runtime_dir / "release-evidence"

    @property
    def release_evidence_index_path(self) -> Path:
        return self.release_evidence_dir / "index.json"

    @property
    def operations_dir(self) -> Path:
        return self.omh_home / "operations"

    @property
    def provider_profile_postures_dir(self) -> Path:
        return self.operations_dir / "provider-profile-postures"

    @property
    def operations_index_path(self) -> Path:
        return self.operations_dir / "index.json"

    @property
    def hermes_ops_dir(self) -> Path:
        return self.omh_home / "hermes-ops"

    @property
    def hermes_ops_blueprints_dir(self) -> Path:
        return self.hermes_ops_dir / "blueprints"

    @property
    def hermes_ops_index_path(self) -> Path:
        return self.hermes_ops_dir / "index.json"

    @property
    def research_department_dir(self) -> Path:
        return self.omh_home / "research-department"

    @property
    def research_department_plans_dir(self) -> Path:
        return self.research_department_dir / "plans"

    @property
    def research_department_index_path(self) -> Path:
        return self.research_department_dir / "index.json"

    @property
    def agent_operator_productivity_dir(self) -> Path:
        return self.omh_home / "agent-ops"

    @property
    def agent_operator_productivity_cards_dir(self) -> Path:
        return self.agent_operator_productivity_dir / "reviews"

    @property
    def agent_operator_productivity_index_path(self) -> Path:
        return self.agent_operator_productivity_dir / "index.json"

    @property
    def materials_dir(self) -> Path:
        return self.omh_home / "materials"

    @property
    def materials_index_path(self) -> Path:
        return self.materials_dir / "index.json"

    @property
    def visual_dir(self) -> Path:
        return self.omh_home / "visual"

    @property
    def visual_observations_dir(self) -> Path:
        return self.visual_dir / "observations"

    @property
    def visual_observations_index_path(self) -> Path:
        return self.visual_observations_dir / "index.json"

    @property
    def web_visual_qa_dir(self) -> Path:
        return self.omh_home / "web-visual-qa"

    @property
    def web_visual_qa_packages_dir(self) -> Path:
        return self.web_visual_qa_dir / "packages"

    @property
    def web_visual_qa_packages_index_path(self) -> Path:
        return self.web_visual_qa_packages_dir / "index.json"

    @property
    def memory_dir(self) -> Path:
        return self.omh_home / "memory"

    @property
    def memory_index_path(self) -> Path:
        return self.memory_dir / "index.json"

    @property
    def memory_operations_dir(self) -> Path:
        return self.memory_dir / "operations"

    @property
    def memory_tombstones_dir(self) -> Path:
        return self.memory_dir / "tombstones"

    @property
    def memory_migrations_dir(self) -> Path:
        return self.memory_dir / "migrations"

    @property
    def memory_history_dir(self) -> Path:
        return self.memory_dir / "history"

    @property
    def memory_archive_dir(self) -> Path:
        return self.memory_dir / "archive"

    @property
    def goals_dir(self) -> Path:
        return self.omh_home / "goals"

    @property
    def loops_dir(self) -> Path:
        return self.omh_home / "loops"

    @property
    def setup_profile_path(self) -> Path:
        return self.omh_home / "setup-profile.json"

    @property
    def executor_readiness_path(self) -> Path:
        return self.runtime_dir / "executor-readiness.json"

    @property
    def executor_limit_signals_path(self) -> Path:
        return self.runtime_dir / "executor-limit-signals.json"

    @property
    def dynamic_coding_workflows_dir(self) -> Path:
        return self.omh_home / "coding" / "dynamic-workflows"

    @property
    def fanout_contracts_dir(self) -> Path:
        return self.omh_home / "coding" / "fanout"

    @property
    def target_registry_path(self) -> Path:
        return self.omh_home / "targets.json"

    @property
    def workflow_state_dir(self) -> Path:
        return self.omh_home / "state"

    @property
    def learning_dir(self) -> Path:
        return self.omh_home / "learning"

    @property
    def learning_traces_dir(self) -> Path:
        return self.learning_dir / "traces"

    @property
    def learning_evals_dir(self) -> Path:
        return self.learning_dir / "evals"

    @property
    def learning_candidates_dir(self) -> Path:
        return self.learning_dir / "candidates"

    @property
    def learning_store_routes_dir(self) -> Path:
        return self.learning_dir / "store-routes"

    @property
    def learning_patch_proposals_dir(self) -> Path:
        return self.learning_dir / "patch-proposals"

    @property
    def learning_regressions_dir(self) -> Path:
        return self.learning_dir / "regressions"

    @property
    def learning_exports_dir(self) -> Path:
        return self.learning_dir / "exports"

    @property
    def learning_index_path(self) -> Path:
        return self.learning_dir / "index.json"

    @property
    def use_cases_dir(self) -> Path:
        return self.omh_home / "use-cases"

    @property
    def use_case_artifacts_dir(self) -> Path:
        return self.use_cases_dir / "artifacts"

    @property
    def use_case_artifacts_index_path(self) -> Path:
        return self.use_cases_dir / "index.json"

    @property
    def hermes_config_path(self) -> Path:
        return self.hermes_home / "config.yaml"

    @property
    def hermes_plugins_dir(self) -> Path:
        return self.hermes_home / "plugins"

    @property
    def hermes_plugin_dir(self) -> Path:
        return self.hermes_plugins_dir / "omh"

    @property
    def hermes_achievements_plugin_dir(self) -> Path:
        return self.hermes_plugins_dir / "hermes-achievements"

    @property
    def hermes_achievements_snapshot_path(self) -> Path:
        return self.hermes_achievements_plugin_dir / "scan_snapshot.json"

    @property
    def hermes_achievements_state_path(self) -> Path:
        return self.hermes_achievements_plugin_dir / "state.json"

    @property
    def hermes_achievements_agent_summary_path(self) -> Path:
        return self.hermes_achievements_plugin_dir / "agent_summary.json"

    @property
    def hermes_agents_dir(self) -> Path:
        return self.hermes_home / "agents"

    @property
    def team_profile_manifest_dir(self) -> Path:
        return self.omh_home / "team-profile-packs"


def expand_path(value: str | Path) -> Path:
    return Path(os.path.expandvars(str(value))).expanduser().resolve()


def default_omh_home() -> Path:
    return expand_path(os.environ.get("OMH_HOME", "~/.omh"))


def default_hermes_home() -> Path:
    return expand_path(os.environ.get("HERMES_HOME", "~/.hermes"))


def user_home() -> Path | None:
    """The home directory the `~/.omh` and `~/.hermes` defaults actually expand to.

    Deliberately not `os.environ["HOME"]` everywhere: on native Windows,
    `ntpath.expanduser` reads `%USERPROFILE%` and ignores `HOME`, so a caller
    that trusted HOME would look for managed state somewhere `~` never points
    at -- and a Windows user with HOME set out of WSL habit would get two
    different answers from `expand_path` and from that caller.
    """
    variable = "USERPROFILE" if os.name == "nt" else "HOME"
    value = os.environ.get(variable)
    return Path(value) if value else None


def managed_command_venv_dir() -> Path | None:
    """Where the installers put the isolated OMH venv, or None if unlocatable.

    Mirrors the default resolution in `install.sh` and `install.ps1`; the two
    installers and this reader have to agree or `omh update` and `omh remove`
    cannot find what the installer just wrote.
    """
    explicit = os.environ.get("OMH_VENV_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return (Path(xdg_data_home).expanduser() / "omh" / "venv").resolve()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return (Path(local_app_data).expanduser() / "omh" / "venv").resolve()
    home = user_home()
    if home:
        return (home.expanduser() / ".local" / "share" / "omh" / "venv").resolve()
    return None


def managed_command_bin_dir() -> Path | None:
    """Where the installers expose the `omh` command, or None if unlocatable."""
    explicit = os.environ.get("OMH_BIN_DIR")
    if explicit:
        return Path(explicit).expanduser()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data).expanduser() / "omh" / "bin"
    home = user_home()
    if home:
        return home.expanduser() / ".local" / "bin"
    return None


def managed_command_filenames() -> tuple[str, ...]:
    """Filenames an installer-exposed `omh` command can carry.

    POSIX installs create a symlink named `omh`. Windows installs create an
    `omh.cmd` shim, because a symlink there needs Developer Mode or elevation
    and an installer must not require either. Windows keeps `omh` in the list
    so an install made where symlinks *are* permitted is still recognized.
    """
    return ("omh.cmd", "omh") if os.name == "nt" else ("omh",)


def managed_command_venv_scripts_dir(venv_dir: Path) -> Path:
    """The venv subdirectory holding executables: `Scripts` on Windows, `bin` elsewhere."""
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def command_entry_belongs_to_venv(path: Path, venv_dir: Path) -> bool:
    """Was this `omh` entry created by an installer for `venv_dir`?

    Two shapes, because the two installers create two different things: a
    symlink resolving into the venv, or a `.cmd` shim naming the venv
    executable by absolute path. Anything else -- a pip-installed console
    script, a user's own wrapper -- is not ours to touch.
    """
    try:
        if path.is_symlink():
            return _is_relative_to(path.resolve(), venv_dir)
        if path.suffix.lower() != ".cmd" or not path.is_file():
            return False
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    # Matching on the `Scripts` directory rather than the venv root is what
    # keeps a sibling venv out: `...\venv2\Scripts` does not contain
    # `...\venv\Scripts`. Case-folded because Windows paths are
    # case-insensitive and `resolve()` may hand back different casing than the
    # installer wrote; both separator forms because a shim may carry either.
    scripts_dir = managed_command_venv_scripts_dir(venv_dir)
    haystack = body.casefold()
    return str(scripts_dir).casefold() in haystack or scripts_dir.as_posix().casefold() in haystack


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def project_omh_home(cwd: str | Path | None = None) -> Path:
    return _project_anchor(cwd) / ".omh"


def project_hermes_home(cwd: str | Path | None = None) -> Path:
    return _project_anchor(cwd) / ".hermes"


def _project_anchor(cwd: str | Path | None = None) -> Path:
    """Where `--scope project` puts a store: the repository, not the shell's cwd."""
    # These used the literal cwd, so running from a subdirectory scattered a
    # store into `src/whatever/.omh` while repository-scoped artifacts resolved
    # to the root -- one `--scope project` run, two homes.
    root = find_project_root(cwd)
    return root if root is not None else expand_path(cwd or Path.cwd())


def find_project_root(cwd: str | Path | None = None) -> Path | None:
    """Nearest ancestor holding a `.git` entry, or None outside a repository."""
    # Filesystem-only: `git rev-parse` would be a subprocess in a core that makes
    # no external calls. `.git` is a directory in a checkout and a file in a
    # linked worktree, so both shapes count.
    start = expand_path(cwd or Path.cwd())
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def project_artifact_dir(paths: OmhPaths, *segments: str, cwd: str | Path | None = None) -> Path:
    """Repo-local `.omh/<segments>` inside a project, user-scope store outside one."""
    # A named home wins over the inferred repository: `--omh-home` exists to say
    # where the store is, and writing elsewhere would make the flag a lie.
    if paths.omh_home_named:
        return paths.omh_home.joinpath(*segments)
    root = find_project_root(cwd)
    base = root / ".omh" if root is not None else paths.omh_home
    return base.joinpath(*segments)


def ensure_project_store_ignored(directory: Path) -> None:
    """Give a repo-local OMH store a `.gitignore` so it stays out of `git status`."""
    # Only this repository's own .gitignore lists `.omh/`; a user's project has
    # no such rule, so a recorded plan would be untracked and `git add -A` would
    # commit it. Skipped outside a repository, where there is nothing to ignore
    # against. An existing file is left alone in case the user wrote their own.
    store = next((parent for parent in (directory, *directory.parents) if parent.name == ".omh"), None)
    if store is None or find_project_root(store.parent) is None:
        return
    marker = store / ".gitignore"
    if marker.exists():
        return
    try:
        atomic_write_text(marker, "*\n")
    except OSError:
        return  # losing the ignore file is not worth failing the artifact over


def project_identity(cwd: str | Path | None = None) -> str:
    """Repository directory name, or "default" outside one."""
    # A name rather than a hash: people read this in `scope.ref` next to values
    # like `document-harness`. Same-named checkouts share a label.
    root = find_project_root(cwd)
    return root.name if root is not None and root.name else "default"


def resolve_paths(
    omh_home: str | Path | None = None,
    hermes_home: str | Path | None = None,
    *,
    scope: str | None = None,
) -> OmhPaths:
    normalized_scope = str(scope or "user").strip().lower()
    if normalized_scope not in {"user", "project"}:
        normalized_scope = "user"
    default_omh = project_omh_home() if normalized_scope == "project" else default_omh_home()
    default_hermes = project_hermes_home() if normalized_scope == "project" else default_hermes_home()
    return OmhPaths(
        omh_home=expand_path(omh_home) if omh_home else default_omh,
        hermes_home=expand_path(hermes_home) if hermes_home else default_hermes,
        # Recorded here, while the caller's intent is still known: comparing the
        # resolved home against the default later cannot tell a named home from
        # an unnamed one that happens to match it.
        omh_home_named=omh_home is not None,
    )
