"""Environment preflight checks powering ``foldapp doctor``."""

from __future__ import annotations

import shutil
import socket
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from fold_at_scripps.foldapp.context import FoldappPaths
from fold_at_scripps.foldapp.shell import run

Which = Callable[[str], str | None]


class Status(StrEnum):
    """Outcome of a single check."""

    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CheckResult:
    """One preflight check outcome."""

    name: str
    status: Status
    detail: str
    fix: str | None


def check_python(paths: FoldappPaths, *, which: Which = shutil.which) -> CheckResult:
    """Python must be >= 3.11."""
    ok = sys.version_info >= (3, 11)
    v = f"{sys.version_info.major}.{sys.version_info.minor}"
    return CheckResult(
        "python",
        Status.OK if ok else Status.FAIL,
        f"Python {v}",
        None if ok else "Use Python 3.11+",
    )


def check_uv(paths: FoldappPaths, *, which: Which = shutil.which) -> CheckResult:
    """uv must be on PATH."""
    found = which("uv")
    return CheckResult(
        "uv",
        Status.OK if found else Status.FAIL,
        found or "not found",
        None if found else "Install uv: https://docs.astral.sh/uv/",
    )


def check_docker(paths: FoldappPaths, *, which: Which = shutil.which, runner=run) -> CheckResult:
    """Docker daemon must be reachable."""
    if not which("docker"):
        return CheckResult("docker", Status.FAIL, "docker not found", "Install Docker")
    result = runner(["docker", "info"], check=False)
    ok = result.returncode == 0
    return CheckResult(
        "docker",
        Status.OK if ok else Status.FAIL,
        "daemon reachable" if ok else "daemon unreachable",
        None if ok else "Start Docker and ensure your user can reach the socket",
    )


def check_autobio(
    paths: FoldappPaths, *, which: Which = shutil.which, context: str = "deploy"
) -> CheckResult:
    """autobio CLI must be on PATH for the scheduler (WARN in dev)."""
    found = which("autobio")
    if found:
        return CheckResult("autobio", Status.OK, found, None)
    status = Status.WARN if context == "dev" else Status.FAIL
    return CheckResult("autobio", status, "not found", "Put the autobio CLI on PATH")


def check_gpu(paths: FoldappPaths, *, which: Which = shutil.which, runner=run) -> CheckResult:
    """GPU access via the NVIDIA container runtime (WARN if absent)."""
    if not which("docker"):
        return CheckResult("gpu", Status.WARN, "docker missing", "Install Docker + NVIDIA runtime")
    result = runner(
        [
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            "nvidia/cuda:12.4.0-base-ubuntu22.04",
            "nvidia-smi",
        ],
        check=False,
    )
    ok = result.returncode == 0
    return CheckResult(
        "gpu",
        Status.OK if ok else Status.WARN,
        "GPUs visible" if ok else "no GPU access",
        None if ok else "Install the NVIDIA container runtime (dev boxes can ignore)",
    )


def check_port_free(paths: FoldappPaths, port: int) -> CheckResult:
    """A required port must be bindable (or already ours)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        free = sock.connect_ex(("127.0.0.1", port)) != 0
    return CheckResult(
        f"port:{port}", Status.OK if free else Status.WARN,
        "free" if free else "in use", None if free else "Ensure it is our own service",
    )


def check_env(paths: FoldappPaths) -> CheckResult:
    """.env must exist with a non-default secret."""
    if not paths.env_file.is_file():
        return CheckResult("env", Status.FAIL, "no .env", "Run: foldapp config init")
    text = paths.env_file.read_text()
    bad = "dev-insecure-secret-change-me" in text or "CHANGE-ME" in text
    return CheckResult(
        "env", Status.FAIL if bad else Status.OK,
        "dev secret in use" if bad else "present",
        "Set a real FOLD_SECRET_KEY" if bad else None,
    )


def check_linger(paths: FoldappPaths, *, runner=run) -> CheckResult:
    """Lingering enables boot-start of user services (WARN if off)."""
    result = runner(["loginctl", "show-user", paths.user, "--property=Linger"], check=False)
    on = "Linger=yes" in result.stdout
    return CheckResult(
        "linger", Status.OK if on else Status.WARN, "enabled" if on else "disabled",
        None if on else f"Enable boot-start: sudo loginctl enable-linger {paths.user}",
    )


def run_checks(paths: FoldappPaths, *, context: str = "deploy") -> list[CheckResult]:
    """Run every check for the given context ('deploy' | 'dev')."""
    results = [
        check_python(paths),
        check_uv(paths),
        check_docker(paths),
        check_autobio(paths, context=context),
        check_gpu(paths),
        check_port_free(paths, 8000),
        check_port_free(paths, 5432),
        check_env(paths),
    ]
    if context == "deploy":
        results.append(check_linger(paths))
    return results


def has_failures(results: Sequence[CheckResult]) -> bool:
    """True if any result is FAIL."""
    return any(r.status is Status.FAIL for r in results)
