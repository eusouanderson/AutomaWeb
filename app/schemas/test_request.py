from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TestGenerateRequest(BaseModel):
    project_id: int
    prompt: str = Field(..., min_length=5)
    context: str | None = None
    ai_debug: bool = False


class TestRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    prompt: str
    context: str | None
    status: str
    created_at: datetime
