"""Tests for the autobio CLI executor."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from fold_at_scripps.autobio_executor import AutobioExecutor, _gpu_spec
from fold_at_scripps.executor import ExecutionRequest


def test_gpu_spec_mapping() -> None:
    assert _gpu_spec([]) == "none"
    assert _gpu_spec([0]) == "0"
    assert _gpu_spec([0, 3]) == "0,3"


def _request(root: Path, gpu_ids: list[int]) -> ExecutionRequest:
    (root / "config").mkdir(parents=True)
    (root / "outputs").mkdir(parents=True)
    (root / "config" / "config.json").write_text("{}")
    return ExecutionRequest(
        tool_name="ablang2",
        tool_version="1.0.0",
        image_tag="ablang2:1.0.0",
        config_path=root / "config" / "config.json",
        outputs_dir=root / "outputs",
        gpu_ids=gpu_ids,
        timeout=300,
    )


def test_failure_from_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request(tmp_path, [0])

    def _fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = AutobioExecutor().execute(request)
    assert result.succeeded is False
    assert "boom" in (result.error or "")
    assert result.gpu_seconds is not None  # wall * 1 gpu


def test_success_moves_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request(tmp_path, [])

    def _fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        # emulate autobio writing a workspace with outputs/
        workspace = Path(cmd[cmd.index("--output-dir") + 1])
        (workspace / "outputs" / "raw").mkdir(parents=True)
        (workspace / "outputs" / "raw" / "emb.npy").write_text("data")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = AutobioExecutor().execute(request)
    assert result.succeeded is True
    assert (request.outputs_dir / "raw" / "emb.npy").read_text() == "data"
    assert result.gpu_seconds is None  # no gpus


def test_timeout_returns_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request(tmp_path, [0])

    def _fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd, timeout=1)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = AutobioExecutor().execute(request)
    assert result.succeeded is False
    assert "timed out" in (result.error or "").lower()
    assert result.gpu_seconds is not None  # wall x 1 gpu


@pytest.mark.skipif(shutil.which("autobio") is None, reason="autobio CLI not on PATH")
def test_real_ablang2_smoke(tmp_path: Path) -> None:
    from fold_at_scripps.storage import LocalStorage

    storage = LocalStorage(tmp_path)
    run_id = uuid.uuid4()
    storage.create_run_dir(run_id)
    storage.write_config(
        run_id,
        {
            "sequences": [
                {
                    "id": "ab1",
                    "heavy_chain": (
                        "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYAD"
                        "SVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAKDGYYYYGMDVWGQGTTVTVSS"
                    ),
                    "light_chain": (
                        "DIQMTQSPSSLSASVGDRVTITCRASQSISSYLNWYQQKPGKAPKLLIYAASSLQSGVPSR"
                        "FSGSGSGTDFTLTISSLQPEDFATYYCQQSYSTPLTFGGGTKVEIK"
                    ),
                }
            ]
        },
    )
    request = ExecutionRequest(
        tool_name="ablang2",
        tool_version="1.0.0",
        image_tag="ghcr.io/briney/autobio-ablang2:1.0.0",
        config_path=storage.config_path(run_id),
        outputs_dir=storage.outputs_dir(run_id),
        gpu_ids=[0],
        timeout=300,
    )
    result = AutobioExecutor().execute(request)
    assert result.succeeded is True, result.error
    assert any(storage.outputs_dir(run_id).rglob("*.npy"))
