# Final Review Fixes Report

**Branch:** `feature/foundation-scaffold`
**Commit:** `55d9084` — fix: pin CI python, 503 readiness on DB failure, pristine test output
**Date:** 2026-06-30

---

# Plan 6 Scheduler — Final Review Fixes Report

**Branch:** `feature/scheduler`
**Date:** 2026-06-30

---

## Fix 1 — GPU leak when commit fails (`src/fold_at_scripps/scheduler/claim.py`)

**Covering test:** `tests/scheduler/test_claim.py` — `test_claim_releases_gpus_when_commit_fails`

### RED (before fix)

```
uv run pytest tests/scheduler/test_claim.py::test_claim_releases_gpus_when_commit_fails -v
```

```
FAILED tests/scheduler/test_claim.py::test_claim_releases_gpus_when_commit_fails
    assert pool.available == original_available
E   assert 1 == 2
1 failed in 0.14s
```

### GREEN (after fix)

```
uv run pytest tests/scheduler/test_claim.py::test_claim_releases_gpus_when_commit_fails -v
```

```
tests/scheduler/test_claim.py::test_claim_releases_gpus_when_commit_fails PASSED
1 passed in 0.14s
```

**Fix:** Wrapped the mutate→commit→refresh block in `try/except Exception`; on failure
`pool.release(gpu_ids)` is called, `session.rollback()` is awaited, and the exception is
re-raised. The `except Exception` boundary is documented in a comment (per the brief).

---

## Fix 2 — `run_forever` has no error guard (`src/fold_at_scripps/scheduler/service.py`)

**Covering test:** `tests/scheduler/test_service.py` —
`test_run_forever_survives_transient_error_then_stops_on_cancel`

### RED (before fix)

```
uv run pytest "tests/scheduler/test_service.py::test_run_forever_survives_transient_error_then_stops_on_cancel" -v
```

```
FAILED tests/scheduler/test_service.py::test_run_forever_survives_transient_error_then_stops_on_cancel
    RuntimeError: boom  (propagated instead of being swallowed)
1 failed in 0.18s
```

### GREEN (after fix)

```
uv run pytest "tests/scheduler/test_service.py::test_run_forever_survives_transient_error_then_stops_on_cancel" -v
```

```
tests/scheduler/test_service.py::test_run_forever_survives_transient_error_then_stops_on_cancel PASSED
1 passed in 0.14s
```

**Fix:** Wrapped `await self.run_once()` in `try/except`; `asyncio.CancelledError` is
re-raised immediately, all other `Exception` subclasses are caught and logged via
`logger.exception(...)`, and the loop continues.

---

## Fix 3 — Directory mutated while iterating (`src/fold_at_scripps/autobio_executor.py`)

**Covering test:** `tests/test_autobio_executor.py` — `test_success_moves_multiple_outputs`

### Note

The spec notes this bug may not reproduce on the test filesystem (Linux ext4/tmpfs). The test
passed before the fix was applied (regression guard behavior), and continues to pass after.

```
uv run pytest tests/test_autobio_executor.py::test_success_moves_multiple_outputs -v
```

```
tests/test_autobio_executor.py::test_success_moves_multiple_outputs PASSED
1 passed in 0.04s
```

**Fix:** Materialized `autobio_outputs.iterdir()` with `list(...)` before the `shutil.move`
loop, so the generator is exhausted before any entries are removed from the directory.

---

## Fix 4 — Single-process GPU-owner invariant (`src/fold_at_scripps/scheduler/main.py`)

No behavior change; no test required per the spec.

**Fix:** Added a docstring paragraph to `build_scheduler()` and a cross-reference sentence
in `run_scheduler()` documenting the single-process invariant: GPU allocation lives entirely
in the per-process in-memory `GpuPool`; exactly one `fold-scheduler` process must run per
node; advisory-lock / leader-election enforcement is deferred to the deployment plan.

---

## Final Combined Test Run

```
uv run pytest tests/scheduler/test_claim.py tests/scheduler/test_service.py tests/test_autobio_executor.py -v
```

```
============================= test session starts ==============================
platform linux -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
plugins: anyio-4.14.1, asyncio-1.4.0
asyncio: mode=Mode.AUTO

tests/scheduler/test_claim.py::test_claim_transitions_oldest_fitting_run PASSED
tests/scheduler/test_claim.py::test_claim_returns_none_when_nothing_fits PASSED
tests/scheduler/test_claim.py::test_claim_returns_none_when_no_queued PASSED
tests/scheduler/test_claim.py::test_claim_releases_gpus_when_commit_fails PASSED
tests/scheduler/test_service.py::test_run_once_dispatches_up_to_capacity PASSED
tests/scheduler/test_service.py::test_run_once_respects_maintenance_mode PASSED
tests/scheduler/test_service.py::test_run_forever_survives_transient_error_then_stops_on_cancel PASSED
tests/test_autobio_executor.py::test_gpu_spec_mapping PASSED
tests/test_autobio_executor.py::test_failure_from_nonzero_exit PASSED
tests/test_autobio_executor.py::test_success_moves_outputs PASSED
tests/test_autobio_executor.py::test_timeout_returns_failure PASSED
tests/test_autobio_executor.py::test_success_moves_multiple_outputs PASSED
tests/test_autobio_executor.py::test_real_ablang2_smoke PASSED

============================== 13 passed in 3.48s ==============================
```

## Ruff Results

```
uv run ruff check .        →  All checks passed!
uv run ruff format --check .  →  93 files already formatted
```

---

## Changes Applied

### Fix 1 — Pin CI Python version

**File:** `.github/workflows/ci.yml`

Added `with: python-version: "3.11"` to the `astral-sh/setup-uv@v5` step, ensuring CI
uses the same Python version as the Dockerfile (`python:3.11-slim`) and `pyproject.toml`
(`requires-python = ">=3.11"`).

```yaml
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"
```

### Fix 2 — Readiness endpoint returns 503 (not 500) when the DB is unreachable

**File:** `src/fold_at_scripps/api/health.py`

Added `HTTPException` import and `SQLAlchemyError` import. Wrapped the `SELECT 1` call in
a try/except so a DB failure raises `HTTPException(status_code=503, ...)` rather than
propagating as an unhandled 500.

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
...
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
```

### Fix 3 — Pristine test output + 503 contract test

**File:** `tests/api/test_health.py`

- Converted `test_liveness` from `fastapi.testclient.TestClient` (which was emitting
  `StarletteDeprecationWarning`) to `httpx.AsyncClient` + `ASGITransport`, matching the
  pattern already used by `test_readiness`.
- Added `test_readiness_db_unavailable`: injects a `_FailingSession` via
  `app.dependency_overrides[get_session]` that raises `SQLAlchemyError`, then asserts the
  response is HTTP 503 with `{"detail": "database unavailable"}`. This test runs without a
  real database and is NOT marked `integration`.

---

## Verification Commands and Output

### `uv run ruff check .`

```
All checks passed!
```

### `uv run ruff format --check .`

```
12 files already formatted
```

### `uv run pytest -v`

```
============================= test session starts ==============================
platform linux -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0 -- /home/briney/git/fold-at-scripps/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/briney/git/fold-at-scripps
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.14.1, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 6 items

tests/api/test_health.py::test_liveness PASSED                           [ 16%]
tests/api/test_health.py::test_readiness PASSED                          [ 33%]
tests/api/test_health.py::test_readiness_db_unavailable PASSED           [ 50%]
tests/test_config.py::test_settings_defaults PASSED                      [ 66%]
tests/test_config.py::test_settings_read_from_env PASSED                 [ 83%]
tests/test_db.py::test_engine_connects PASSED                            [100%]

============================== 6 passed in 0.20s ===============================
```

**Test output is pristine.** The `StarletteDeprecationWarning` is completely absent — no
warnings of any kind appear in the output.
