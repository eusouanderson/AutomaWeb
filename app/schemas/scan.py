from pydantic import BaseModel, Field, HttpUrl


class ScanRequest(BaseModel):
    url: HttpUrl
    project_id: int | None = None


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


class FormContext(BaseModel):
    """Structural grouping of form-related elements — helps LLMs generate complete test flows."""

    form_selector: str | None = None
    inputs: list[str] = []
    submit: str | None = None


class ScanResult(BaseModel):
    url: str
    title: str
    total_elements: int
    summary: dict[str, int]
    elements: list[ScannedElement]
    form_contexts: list[FormContext] = []
