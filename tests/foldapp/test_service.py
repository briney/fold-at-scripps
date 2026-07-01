from __future__ import annotations

import pytest

from fold_at_scripps.foldapp.service import is_active, resolve_units
from fold_at_scripps.foldapp.shell import CommandResult


def test_resolve_units_all():
    assert resolve_units("all") == ["fold-api", "fold-scheduler"]


def test_resolve_units_single():
    assert resolve_units("scheduler") == ["fold-scheduler"]


def test_resolve_units_invalid():
    with pytest.raises(ValueError):
        resolve_units("bogus")


def test_is_active_true():
    def fake_runner(args, **kw):
        return CommandResult(args=args, returncode=0, stdout="active\n", stderr="")

    assert is_active("fold-api", runner=fake_runner) is True


def test_is_active_false():
    def fake_runner(args, **kw):
        return CommandResult(args=args, returncode=3, stdout="inactive\n", stderr="")

    assert is_active("fold-api", runner=fake_runner) is False
