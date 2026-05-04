from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TestGenerateRequest(BaseModel):
    project_id: int
    prompt: str = Field(..., min_length=5)
    context: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=16384)
    ai_debug: bool = False
    force_rescan: bool = False


class TestRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    prompt: str
    context: str | None
    status: str
    created_at: datetime
