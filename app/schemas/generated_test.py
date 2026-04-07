from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GeneratedChunkPartOut(BaseModel):
    index: int
    approx_chars: int
    keys: list[str]


class GeneratedTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_request_id: int
    content: str
    file_path: str
    created_at: datetime
    generation_strategy: str | None = None
    chunk_target_chars: int | None = None
    chunk_count: int | None = None
    chunk_parts: list[GeneratedChunkPartOut] | None = None


class GeneratedTestSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_request_id: int
    file_path: str
    created_at: datetime
