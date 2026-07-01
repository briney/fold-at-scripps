"""User-facing run endpoints: submit, list, inspect, cancel, delete, download."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from fold_at_scripps.auth.dependencies import get_current_user
from fold_at_scripps.catalog.service import get_enabled_tool
from fold_at_scripps.db import get_session
from fold_at_scripps.models import User
from fold_at_scripps.runs.quota import QuotaExceeded
from fold_at_scripps.runs.service import (
    InputFile,
    RunNotCancelable,
    RunNotFound,
    cancel_run,
    get_run,
    list_runs,
    soft_delete_run,
    submit_run,
)
from fold_at_scripps.runs.validation import InvalidParams
from fold_at_scripps.schemas.runs import RunRead, RunSummary
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


@router.get("", response_model=list[RunSummary])
async def list_user_runs(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Any:
    """List the current user's non-hidden runs, newest first."""
    return await list_runs(session, user)


@router.get("/{run_id}", response_model=RunRead)
async def get_user_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Any:
    """Return one of the current user's runs, with artifacts."""
    run = await get_run(session, user, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/{run_id}/cancel", response_model=RunRead)
async def cancel_user_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Any:
    """Cancel a queued run."""
    try:
        return await cancel_run(session, user, run_id)
    except RunNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RunNotCancelable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    """Soft-delete (hide) a run from the user's history."""
    run = await soft_delete_run(session, user, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")


@router.get("/{run_id}/artifacts/{artifact_path:path}")
async def download_artifact(
    run_id: uuid.UUID,
    artifact_path: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> FileResponse:
    """Stream one of the run's output files (ownership-checked, traversal-guarded)."""
    run = await get_run(session, user, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    artifact = next((a for a in run.artifacts if a.path == artifact_path), None)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    outputs = storage.outputs_dir(run_id).resolve()
    target = (outputs / artifact_path).resolve()
    if not target.is_relative_to(outputs) or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    media_type = artifact.content_type or "application/octet-stream"
    return FileResponse(target, filename=artifact.name, media_type=media_type)
