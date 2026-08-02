from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from threading import Thread
from typing import BinaryIO, Final

from .cross_harness_benchmark_values import JsonValue


MAX_OUTPUT_BYTES: Final = 1_048_576
_CREDENTIAL_KEY: Final = (
    "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL", "API_KEY",
    "AWS_", "AZURE_", "GOOGLE_", "OPENAI_", "ANTHROPIC_", "GITHUB_",
    "CODEX_", "CLAUDE_", "HERMES_",
)
_SENSITIVE_PARTS: Final = {
    ".ssh", ".aws", ".config", ".codex", ".claude", ".hermes", ".omh",
    "keychains", "credentials",
}
_MACOS_RUNTIME_ROOTS: Final = tuple(
    Path(item) for item in (
        "/usr/lib", "/System/Library", "/Library/Apple/System/Library",
        "/private/var/db/dyld",
    )
)
PopenFactory = Callable[..., subprocess.Popen[bytes]]


@dataclass(frozen=True, slots=True)
class ChildContext:
    root: Path
    home: Path
    work: Path
    temporary: Path
    output: Path
    request_path: Path
    artifact_path: Path
    spawn_digest: str


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    status: str
    exit_code: int | None
    process_group_terminated: bool
    stdout_hash: str
    stdout_bytes: int
    stderr_hash: str
    stderr_bytes: int
    stdout_sample: bytes
    stderr_sample: bytes
    overflow: bool


@dataclass(frozen=True, slots=True)
class InventoryEntry:
    path: str
    sha256: str


def allocate_child(
    root: Path,
    request_payload: Mapping[str, JsonValue],
    request_digest: str,
    repetition: int,
) -> ChildContext:
    root = root.resolve()
    home, work, temporary, output = (root / name for name in ("home", "work", "tmp", "output"))
    root.chmod(0o700)
    for directory in (home, work, temporary, output):
        directory.mkdir(mode=0o700)
    request_path = root / "request.json"
    request_path.write_text(json.dumps(request_payload, sort_keys=True), encoding="utf-8")
    request_path.chmod(0o600)
    spawn_digest = hashlib.sha256(os.urandom(32)).hexdigest()
    artifact_path = output / f"result-{repetition}-{spawn_digest}.json"
    return ChildContext(root, home, work, temporary, output, request_path, artifact_path, spawn_digest)


def observe_process(
    argv: tuple[str, ...],
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    popen_factory: PopenFactory,
) -> ProcessObservation:
    process = popen_factory(
        argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
        start_new_session=True,
    )
    outputs: list[tuple[str, int, bytes, bool] | None] = [None, None]
    assert process.stdout is not None and process.stderr is not None

    def consume(position: int, stream: BinaryIO) -> None:
        digest, count, sample, overflow = hashlib.sha256(), 0, bytearray(), False
        while chunk := stream.read(8192):
            count += len(chunk)
            overflow = overflow or count > MAX_OUTPUT_BYTES
            digest.update(chunk)
            if len(sample) < 512:
                sample.extend(chunk[: 512 - len(sample)])
        outputs[position] = (digest.hexdigest(), count, bytes(sample), overflow)

    threads = (
        Thread(target=consume, args=(0, process.stdout), daemon=True),
        Thread(target=consume, args=(1, process.stderr), daemon=True),
    )
    for thread in threads:
        thread.start()
    try:
        exit_code = process.wait(timeout=timeout)
        status = "crash" if exit_code < 0 else "exit"
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        status, exit_code = "timeout", None
    terminated = process_group_absent(process.pid)
    for thread in threads:
        thread.join()
    process.stdout.close()
    process.stderr.close()
    stdout, stderr = outputs
    assert stdout is not None and stderr is not None
    return ProcessObservation(
        status, exit_code, terminated, stdout[0], stdout[1], stderr[0],
        stderr[1], stdout[2], stderr[2], stdout[3] or stderr[3],
    )


def process_group_absent(process_id: int) -> bool:
    try:
        os.killpg(process_id, 0)
    except ProcessLookupError:
        return True
    return False


def backend(selected: str) -> str:
    if selected != "auto":
        return selected
    if sys.platform == "darwin":
        return "sandbox-exec"
    return "bwrap" if sys.platform.startswith("linux") else "unsupported"


def backend_available(selected: str) -> bool:
    return selected in {"sandbox-exec", "bwrap"} and (
        (selected == "sandbox-exec" and sys.platform == "darwin")
        or (selected == "bwrap" and sys.platform.startswith("linux"))
    )


def environment_is_safe(environment: Sequence[tuple[str, str]]) -> bool:
    return not any(
        not key.startswith("OMH_")
        or any(marker in key.upper() for marker in _CREDENTIAL_KEY)
        or any(marker in value.casefold() for marker in ("sk-", "ignore previous", "private key", "bearer "))
        for key, value in environment
    )


def read_roots_are_safe(read_roots: Sequence[Path]) -> bool:
    home = Path.home().resolve()
    for root in read_roots:
        resolved = root.resolve()
        if resolved == Path("/") or resolved == home:
            return False
        if _SENSITIVE_PARTS.intersection(part.casefold() for part in resolved.parts):
            return False
    return True


def runtime_roots(selected: str) -> tuple[Path, ...]:
    return _MACOS_RUNTIME_ROOTS if selected == "sandbox-exec" else ()


def preflight(
    selected: str,
    roots: tuple[Path, ...],
    child: ChildContext,
    allow_network: bool,
    environment: Mapping[str, str],
) -> tuple[bool, str]:
    tool = "/usr/bin/sandbox-exec" if selected == "sandbox-exec" else shutil.which("bwrap")
    if tool is None or not Path(tool).is_file():
        return False, "unavailable"
    version = hashlib.sha256(Path(tool).read_bytes()).hexdigest()
    try:
        completed = subprocess.run(
            sandbox_command(("/usr/bin/true",), selected, roots, child, allow_network, environment),
            cwd=child.work, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
            timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, version
    return completed.returncode == 0, version


def sandbox_command(
    argv: tuple[str, ...],
    selected: str,
    roots: Sequence[Path],
    child: ChildContext,
    allow_network: bool,
    environment: Mapping[str, str],
) -> tuple[str, ...]:
    if selected == "sandbox-exec":
        literals = " ".join(f'(literal {json.dumps(str(Path(item).resolve()))})' for item in (argv[0], "/usr/bin/true"))
        subpaths = " ".join(f'(subpath {json.dumps(str(root))})' for root in unique_roots((*roots, child.root)))
        network = "(allow network*)" if allow_network else ""
        policy = f'(version 1)(deny default)(allow process-fork)(allow process-exec {literals})(allow sysctl-read)(allow file-read* (literal "/") {literals} {subpaths})(allow file-write* (subpath {json.dumps(str(child.root))})){network}'
        return ("/usr/bin/sandbox-exec", "-p", policy, *argv)
    tool = shutil.which("bwrap") or "bwrap"
    flags = ["--unshare-user", "--unshare-ipc", "--unshare-pid", "--unshare-uts", "--disable-userns", "--new-session", "--die-with-parent", "--clearenv"]
    if not allow_network:
        flags.insert(3, "--unshare-net")
    bind_roots = unique_roots((*roots, Path(argv[0]).resolve().parent))
    binds = [part for root in bind_roots for part in ("--ro-bind", str(root), str(root))]
    env_flags = [part for key, value in sorted(environment.items()) for part in ("--setenv", key, value)]
    return (tool, *flags, "--tmpfs", "/", *binds, "--bind", str(child.root), str(child.root), "--chdir", str(child.work), *env_flags, "--", *argv)


def inventory(root: Path, excluded: set[str]) -> tuple[InventoryEntry, ...]:
    entries: list[InventoryEntry] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative not in excluded:
            entries.append(InventoryEntry(relative, hashlib.sha256(path.read_bytes()).hexdigest()))
    return tuple(entries)


def unique_roots(roots: Sequence[Path]) -> tuple[Path, ...]:
    return tuple(dict.fromkeys(root.resolve() for root in roots))
