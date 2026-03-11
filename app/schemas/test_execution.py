"""Schema for test execution results"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TestExecutionRequest(BaseModel):
    project_id: int
    test_ids: list[int] | None = None  # se None, executa todos os testes do projeto
    ai_debug: bool = False
    headless: bool = True  # True = sem janela (CI), False = abre o navegador


class TestCaseResult(BaseModel):
    name: str
    status: str  # PASS, FAIL, SKIP, UNKNOWN
    message: str | None = None


class TestExecutionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    project_id: int
    total_tests: int
    passed: int
    failed: int
    skipped: int
    log_file: str
    report_file: str
    output_file: str
    status: str  
    created_at: datetime | None = None
    completed_at: datetime | None = None
    error_output: str | None = None
    mkdocs_index: str | None = None
    test_cases: list[TestCaseResult] = []
