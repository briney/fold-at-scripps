from __future__ import annotations

from unittest import mock

from fold_at_scripps.foldapp import run as run_module


def test_serve_calls_uvicorn_with_app_and_port():
    with mock.patch("uvicorn.run") as uv:
        run_module.serve(port=9001)
    args, kwargs = uv.call_args
    assert args[0] == "fold_at_scripps.main:app"
    assert kwargs["port"] == 9001


def test_scheduler_delegates_to_scheduler_main():
    with mock.patch("fold_at_scripps.scheduler.main.main") as m:
        run_module.scheduler()
    m.assert_called_once()
