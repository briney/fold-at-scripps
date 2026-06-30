"""Tests for application lifespan and engine disposal."""

from __future__ import annotations

import fold_at_scripps.db as db
from fold_at_scripps.db import dispose_engine, get_engine


async def test_dispose_engine_is_idempotent() -> None:
    # No engine created yet: dispose is a no-op and must not raise.
    db._engine = None
    db._sessionmaker = None
    await dispose_engine()
    assert db._engine is None

    # After creating one, dispose clears the singletons.
    engine = get_engine()
    assert engine is not None
    await dispose_engine()
    assert db._engine is None
    assert db._sessionmaker is None
