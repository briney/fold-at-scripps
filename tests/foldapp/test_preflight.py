from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.preflight import Status, check_autobio, check_uv, has_failures


def _paths(tmp_path: Path):
    return resolve_paths(app_dir=tmp_path, home=tmp_path, env={}, user="fold")


def test_check_uv_ok_when_present(tmp_path: Path):
    result = check_uv(_paths(tmp_path), which=lambda name: "/opt/uv/uv")
    assert result.status is Status.OK


def test_check_uv_fail_when_missing(tmp_path: Path):
    result = check_uv(_paths(tmp_path), which=lambda name: None)
    assert result.status is Status.FAIL
    assert result.fix


def test_check_autobio_warns_in_dev_context(tmp_path: Path):
    result = check_autobio(_paths(tmp_path), which=lambda name: None, context="dev")
    assert result.status is Status.WARN


def test_check_autobio_fails_in_deploy_context(tmp_path: Path):
    result = check_autobio(_paths(tmp_path), which=lambda name: None, context="deploy")
    assert result.status is Status.FAIL


def test_has_failures():
    from fold_at_scripps.foldapp.preflight import CheckResult

    ok = CheckResult("a", Status.OK, "", None)
    warn = CheckResult("b", Status.WARN, "", None)
    fail = CheckResult("c", Status.FAIL, "", None)
    assert has_failures([ok, warn]) is False
    assert has_failures([ok, fail]) is True
