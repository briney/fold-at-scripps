"""User-facing run endpoints: submit, list, inspect, cancel, delete, download."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.dependencies import get_current_user
from fold_at_scripps.catalog.service import get_enabled_tool
from fold_at_scripps.db import get_session
from fold_at_scripps.models import User
from fold_at_scripps.runs.quota import QuotaExceeded
from fold_at_scripps.runs.service import InputFile, get_run, submit_run
from fold_at_scripps.runs.validation import InvalidParams
from fold_at_scripps.schemas.runs import RunRead
from fold_at_scripps.storage import Storage, get_storage

router = APIRouter(prefix="/runs", tags=["runs"])


def _parse_params(raw: str) -> dict[str, Any]:
    """Parse the ``params`` form field as a JSON object, or raise 422."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"params is not valid JSON: {exc.msg}",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="params must be a JSON object",
        )
    return parsed


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def submit(
    tool_id: uuid.UUID = Form(...),
    params: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> Any:
    """Submit a run: validate, enforce quota, stage inputs, and queue it."""
    parsed = _parse_params(params)
    tool = await get_enabled_tool(session, tool_id)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    inputs = [InputFile(filename=f.filename, content=await f.read()) for f in files if f.filename]
    try:
        run = await submit_run(
            session, user=user, tool=tool, params=parsed, storage=storage, inputs=inputs
        )
    except InvalidParams as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except QuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return await get_run(session, user, run.id)
