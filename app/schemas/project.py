from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    description: str | None = None
    url: HttpUrl | None = None
    test_directory: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    url: str | None
    test_directory: str | None
    test_count: int = 0
    scan_cached_at: datetime | None = None
    created_at: datetime
