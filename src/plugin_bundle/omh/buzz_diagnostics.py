from __future__ import annotations

from collections.abc import Callable, Mapping
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Protocol


BUZZ_PROBE_SCHEMA_VERSION = "omh_buzz_probe/v1"
_VERSION_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)")
_SECRET_KEYS = ("BUZZ_PRIVATE_KEY", "BUZZ_CREDENTIALS_FILE")


class _Paths(Protocol):
    hermes_home: Path
    hermes_config_path: Path


Runner = Callable[..., tuple[int, str, str]]


def probe_buzz(
    paths: _Paths,
    *,
    environ: Mapping[str, str] | None = None,
    runner: Runner | None = None,
) -> dict[str, object]:
    """Inspect local Buzz readiness without network access or state mutation."""

    source_env = os.environ if environ is None else environ
    config_text = _read_text(paths.hermes_config_path)
    dotenv_keys = _dotenv_keys(paths.hermes_home / ".env")
    configured = _buzz_enabled(config_text) or bool(source_env.get("BUZZ_RELAY_URL"))
    credential_present = any(bool(source_env.get(key)) or key in dotenv_keys for key in _SECRET_KEYS)
    executable = _resolve_cli(source_env, config_text, paths.hermes_home)

    if executable is None:
        return _payload(
            status="missing",
            reason_code="buzz_cli_missing",
            configured=configured,
            credential_present=credential_present,
            executable=None,
            version=None,
        )

    invoke = _subprocess_runner if runner is None else runner
    code, stdout, _stderr = invoke(
        (str(executable), "--version"),
        env=_minimal_env(source_env, paths.hermes_home),
        timeout=5,
    )
    version = _version(stdout) if code == 0 else None
    if code != 0:
        status = "unknown"
        reason_code = "buzz_cli_version_failed"
    elif version is None:
        status = "unknown"
        reason_code = "buzz_cli_version_unparseable"
    else:
        status = "available"
        reason_code = "buzz_cli_observed"
    return _payload(
        status=status,
        reason_code=reason_code,
        configured=configured,
        credential_present=credential_present,
        executable=str(executable),
        version=version,
    )


def _payload(
    *,
    status: str,
    reason_code: str,
    configured: bool,
    credential_present: bool,
    executable: str | None,
    version: str | None,
) -> dict[str, object]:
    return {
        "schema_version": BUZZ_PROBE_SCHEMA_VERSION,
        "status": status,
        "reason_code": reason_code,
        "configured": configured,
        "credential_present": credential_present,
        "executable": executable,
        "version": version,
        "observed": status == "available",
        "read_only": True,
        "claim_boundary": (
            "This probe observes local configuration presence and an exact Buzz CLI version command only. "
            "It does not prove relay authentication, membership, message delivery, media rendering, or restore readiness."
        ),
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _dotenv_keys(path: Path) -> frozenset[str]:
    keys: set[str] = set()
    for raw_line in _read_text(path).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() and value.strip():
            keys.add(key.strip())
    return frozenset(keys)


def _buzz_enabled(config_text: str) -> bool:
    lines = config_text.splitlines()
    buzz_indent: int | None = None
    for raw_line in lines:
        line = raw_line.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if stripped == "buzz:":
            buzz_indent = indent
            continue
        if buzz_indent is None:
            continue
        if indent <= buzz_indent:
            buzz_indent = None
            continue
        if stripped.casefold() == "enabled: true":
            return True
    return False


def _config_cli_path(config_text: str) -> str:
    buzz_indent: int | None = None
    extra_indent: int | None = None
    for raw_line in config_text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if stripped == "buzz:":
            buzz_indent = indent
            extra_indent = None
            continue
        if buzz_indent is None:
            continue
        if indent <= buzz_indent:
            buzz_indent = None
            extra_indent = None
            continue
        if stripped == "extra:":
            extra_indent = indent
            continue
        if extra_indent is not None and indent > extra_indent and stripped.startswith("cli_path:"):
            value = stripped.partition(":")[2].strip().strip("'\"")
            return value
    return ""


def _resolve_cli(environ: Mapping[str, str], config_text: str, hermes_home: Path) -> Path | None:
    configured = environ.get("BUZZ_CLI_PATH", "").strip() or _config_cli_path(config_text)
    if configured:
        path = Path(os.path.expandvars(configured)).expanduser()
        return path.resolve() if path.is_file() and os.access(path, os.X_OK) else None
    found = shutil.which("buzz", path=environ.get("PATH"))
    if found:
        return Path(found).resolve()
    fallback = hermes_home.parent / "bin" / "buzz"
    return fallback.resolve() if fallback.is_file() and os.access(fallback, os.X_OK) else None


def _minimal_env(environ: Mapping[str, str], hermes_home: Path) -> dict[str, str]:
    return {
        "HOME": str(hermes_home.parent),
        "LANG": environ.get("LANG", "C.UTF-8"),
        "LC_ALL": environ.get("LC_ALL", environ.get("LANG", "C.UTF-8")),
        "PATH": environ.get("PATH", os.defpath),
        "TMPDIR": environ.get("TMPDIR", tempfile.gettempdir()),
    }


def _subprocess_runner(
    argv: tuple[str, ...],
    *,
    env: dict[str, str],
    timeout: int,
) -> tuple[int, str, str]:
    try:
        process = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, "", ""
    return process.returncode, process.stdout[:512], process.stderr[:512]


def _version(output: str) -> str | None:
    match = _VERSION_PATTERN.search(output[:512])
    return match.group(1) if match is not None else None
