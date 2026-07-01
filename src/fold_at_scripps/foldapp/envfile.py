"""Scaffold and redact the ``.env`` (secrets/infra only)."""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping
from typing import Any

import rich

from fold_at_scripps.foldapp.context import FoldappPaths

_TEMPLATE = """\
# fold@Scripps environment — secrets/infra only. NEVER commit a real secret.
FOLD_SECRET_KEY={secret}
FOLD_DATABASE_URL=postgresql+asyncpg://fold:fold@localhost:5432/fold_at_scripps
FOLD_STORAGE_ROOT={data_dir}
FOLD_FRONTEND_DIST={app_dir}/frontend/dist
FOLD_SESSION_HTTPS_ONLY=true
FOLD_GPU_COUNT=8
FOLD_LOG_LEVEL=INFO
FOLD_MAX_UPLOAD_BYTES=104857600
"""


def generate_secret_key() -> str:
    """Return a fresh URL-safe secret suitable for ``FOLD_SECRET_KEY``."""
    return secrets.token_urlsafe(48)


def scaffold_env(paths: FoldappPaths, *, dry_run: bool = False) -> bool:
    """Create ``.env`` with a generated secret. Return False if it already exists."""
    if paths.env_file.exists():
        return False
    content = _TEMPLATE.format(
        secret=generate_secret_key(), data_dir=paths.data_dir, app_dir=paths.app_dir
    )
    if dry_run:
        rich.print(f"[dim]+ write {paths.env_file}[/dim]")
        return True
    paths.env_file.parent.mkdir(parents=True, exist_ok=True)
    paths.env_file.write_text(content)
    paths.env_file.chmod(0o600)
    return True


def redact_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with the secret key and any DB password masked."""
    out = dict(values)
    if "secret_key" in out:
        out["secret_key"] = "***"
    if "database_url" in out and isinstance(out["database_url"], str):
        out["database_url"] = re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", out["database_url"])
    return out
