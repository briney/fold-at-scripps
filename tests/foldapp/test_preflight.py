from __future__ import annotations

from pathlib import Path

from fold_at_scripps.foldapp.context import resolve_paths
from fold_at_scripps.foldapp.preflight import (
    Status,
    check_autobio,
    check_session_cookie,
    check_uv,
    has_failures,
)


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


def test_session_cookie_warns_in_dev_when_https_only(tmp_path: Path):
    paths = _paths(tmp_path)
    paths.env_file.write_text("FOLD_SESSION_HTTPS_ONLY=true\n")
    result = check_session_cookie(paths, context="dev")
    assert result.status is Status.WARN
    assert result.fix


def test_session_cookie_ok_in_dev_when_http(tmp_path: Path):
    paths = _paths(tmp_path)
    paths.env_file.write_text("FOLD_SESSION_HTTPS_ONLY=false\n")
    result = check_session_cookie(paths, context="dev")
    assert result.status is Status.OK


def test_session_cookie_warns_in_deploy_when_not_secure(tmp_path: Path):
    paths = _paths(tmp_path)
    paths.env_file.write_text("FOLD_SESSION_HTTPS_ONLY=false\n")
    result = check_session_cookie(paths, context="deploy")
    assert result.status is Status.WARN
    assert result.fix


def test_session_cookie_ok_in_deploy_when_secure(tmp_path: Path):
    paths = _paths(tmp_path)
    paths.env_file.write_text("FOLD_SESSION_HTTPS_ONLY=true\n")
    result = check_session_cookie(paths, context="deploy")
    assert result.status is Status.OK


def test_session_cookie_absent_key_matches_config_default(tmp_path: Path):
    # No .env / key unset => config default is False (cookie not Secure).
    paths = _paths(tmp_path)
    assert check_session_cookie(paths, context="dev").status is Status.OK
    assert check_session_cookie(paths, context="deploy").status is Status.WARN


def test_has_failures():
    from fold_at_scripps.foldapp.preflight import CheckResult

    ok = CheckResult("a", Status.OK, "", None)
    warn = CheckResult("b", Status.WARN, "", None)
    fail = CheckResult("c", Status.FAIL, "", None)
    assert has_failures([ok, warn]) is False
    assert has_failures([ok, fail]) is True
