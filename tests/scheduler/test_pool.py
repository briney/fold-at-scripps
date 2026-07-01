"""Tests for the in-memory GPU pool."""

from __future__ import annotations

from fold_at_scripps.scheduler.pool import GpuPool


def test_allocate_and_release() -> None:
    pool = GpuPool([0, 1, 2, 3])
    ids = pool.try_allocate(2)
    assert ids == [0, 1]
    assert pool.available == 2
    pool.release(ids)
    assert pool.available == 4


def test_allocation_is_exclusive() -> None:
    pool = GpuPool([0, 1])
    first = pool.try_allocate(1)
    second = pool.try_allocate(1)
    assert first == [0]
    assert second == [1]
    assert set(first).isdisjoint(second)


def test_try_allocate_returns_none_when_insufficient() -> None:
    pool = GpuPool([0])
    assert pool.try_allocate(2) is None
    assert pool.available == 1


def test_allocate_zero_gpus() -> None:
    pool = GpuPool([0, 1])
    assert pool.try_allocate(0) == []
    assert pool.available == 2
