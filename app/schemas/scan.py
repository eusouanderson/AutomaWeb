from pydantic import BaseModel, Field, HttpUrl


class ScanRequest(BaseModel):
    url: HttpUrl


class ScannedElement(BaseModel):
    type: str
    selector: str | None = None
    xpath: str | None = None
    text: str | None = None
    name: str | None = None
    element_id: str | None = Field(default=None, alias="id")
    placeholder: str | None = None
    required: bool | None = None
    classes: str | None = None
    href: str | None = None
    aria_label: str | None = None
    aria_role: str | None = None
    data_testid: str | None = None

    model_config = {
        "populate_by_name": True,
    }


class ScanResult(BaseModel):
    url: str
    title: str
    total_elements: int
    summary: dict[str, int]
    elements: list[ScannedElement]
