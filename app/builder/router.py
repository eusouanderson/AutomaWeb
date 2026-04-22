from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, HttpUrl

from app.builder.service import BuilderService, get_builder_service

router = APIRouter(prefix="/builder", tags=["builder"])


class BuilderStartRequest(BaseModel):
    url: HttpUrl


class BuilderStartResponse(BaseModel):
    session_id: str
    url: str
    message: str


class BuilderEventRequest(BaseModel):
    session_id: str | None = None
    action: Literal["click", "input"] | None = None
    # Backward-compatible alias for previous payloads.
    type: Literal["click", "input", "select", "navigation"] | None = None
    selector: str | None = None
    value: str | None = None
    description: str | None = None

    # Legacy fields kept to avoid breaking older clients.
    url: str | None = None
    text: str | None = None


class BuilderEventResponse(BaseModel):
    message: str
    step: int
    session_id: str


class BuilderStepsResponse(BaseModel):
    session_id: str | None
    steps: list[dict[str, Any]]


class BuilderGenerateRequest(BaseModel):
    session_id: str | None = None
    prompt: str | None = None


class BuilderGenerateResponse(BaseModel):
    session_id: str
    steps_count: int
    code: str


@router.post("/start", response_model=BuilderStartResponse)
async def start_builder(
    payload: BuilderStartRequest,
    request: Request,
    service: BuilderService = Depends(get_builder_service),
) -> BuilderStartResponse:
    try:
        backend_base_url = str(request.base_url).rstrip("/")
        session_id = await service.start_builder(
            str(payload.url), backend_base_url=backend_base_url
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to start builder: {exc}"
        ) from exc

    return BuilderStartResponse(
        session_id=session_id,
        url=str(payload.url),
        message="Visual test builder started",
    )


@router.post("/event", response_model=BuilderEventResponse)
async def capture_builder_event(
    payload: BuilderEventRequest,
    service: BuilderService = Depends(get_builder_service),
) -> BuilderEventResponse:
    try:
        saved = await service.ingest_event(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BuilderEventResponse(
        message="Event captured",
        step=int(saved["step"]),
        session_id=str(saved["session_id"]),
    )


@router.get("/steps", response_model=BuilderStepsResponse)
async def get_builder_steps(
    session_id: str | None = None,
    service: BuilderService = Depends(get_builder_service),
) -> BuilderStepsResponse:
    steps = await service.list_steps(session_id)
    resolved_session_id = session_id or (steps[0]["session_id"] if steps else None)
    return BuilderStepsResponse(session_id=resolved_session_id, steps=steps)


@router.post("/generate", response_model=BuilderGenerateResponse)
async def generate_builder_code(
    payload: BuilderGenerateRequest,
    service: BuilderService = Depends(get_builder_service),
) -> BuilderGenerateResponse:
    try:
        generated = await service.generate_code_with_prompt(
            session_id=payload.session_id,
            prompt=payload.prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return BuilderGenerateResponse(**generated)
