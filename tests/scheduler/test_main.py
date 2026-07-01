"""Tests for the scheduler entry point wiring."""

from __future__ import annotations

from fold_at_scripps.scheduler.main import build_scheduler
from fold_at_scripps.scheduler.service import Scheduler


def test_build_scheduler_uses_configured_gpu_count(monkeypatch) -> None:
    monkeypatch.setenv("FOLD_GPU_COUNT", "4")
    from fold_at_scripps.config import get_settings

    get_settings.cache_clear()
    scheduler = build_scheduler()
    assert isinstance(scheduler, Scheduler)
    assert scheduler._pool.available == 4
