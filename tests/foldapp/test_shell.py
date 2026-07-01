from __future__ import annotations

import sys

import pytest

from fold_at_scripps.foldapp.shell import CommandError, run


def test_run_captures_stdout():
    result = run([sys.executable, "-c", "print('hi')"])
    assert result.returncode == 0
    assert result.stdout.strip() == "hi"


def test_run_dry_run_does_not_execute():
    result = run([sys.executable, "-c", "raise SystemExit(3)"], dry_run=True)
    assert result.returncode == 0
    assert result.stdout == ""


def test_run_raises_on_failure_with_stderr_tail():
    with pytest.raises(CommandError) as exc:
        run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('boom'); raise SystemExit(1)",
            ]
        )
    assert "boom" in str(exc.value)


def test_run_check_false_returns_nonzero():
    result = run([sys.executable, "-c", "raise SystemExit(2)"], check=False)
    assert result.returncode == 2
