import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from app.api.deps import get_db
from app.ai_validation.metrics import AIMetricsRegistry
from app.schemas.generated_test import GeneratedTestOut, GeneratedTestSummaryOut
from app.schemas.project import ProjectCreate, ProjectOut
from app.schemas.scan import ScanRequest
from app.schemas.test_execution import TestExecutionRequest, TestExecutionResult
from app.schemas.test_request import TestGenerateRequest
from app.services.project_service import ProjectService
from app.services.test_execution_service import TestExecutionService
from app.services.element_scanner import ElementScannerError, ElementScannerService
from app.services.test_service import LLMServiceUnavailableError, ScanUnavailableError, TestService

router = APIRouter()


@router.post("/projects", response_model=ProjectOut)
async def create_project(payload: ProjectCreate, session: AsyncSession = Depends(get_db)) -> ProjectOut:
    service = ProjectService()
    try:
        project = await service.create_project(
            session,
            name=payload.name,
            description=payload.description,
            url=str(payload.url) if payload.url else None,
            test_directory=payload.test_directory,
        )
        return ProjectOut.model_validate(project)
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail=f"Projeto com nome '{payload.name}' já existe")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(session: AsyncSession = Depends(get_db)) -> list[ProjectOut]:
    service = ProjectService()
    projects = await service.list_projects(session)
    return [ProjectOut.model_validate(project) for project in projects]


@router.get("/projects/{project_id}/tests", response_model=list[GeneratedTestSummaryOut])
async def list_project_tests(project_id: int, session: AsyncSession = Depends(get_db)) -> list[GeneratedTestSummaryOut]:
    service = TestService()
    try:
        tests = await service.list_generated_tests_by_project(session, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        GeneratedTestSummaryOut(
            id=test.id,
            test_request_id=test.test_request_id,
            file_path=Path(test.file_path).name,
            created_at=test.created_at,
        )
        for test in tests
    ]


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    service = ProjectService()
    deleted = await service.delete_project(session, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return {"message": "Projeto deletado com sucesso"}


@router.post("/tests/generate", response_model=GeneratedTestOut)
async def generate_test(payload: TestGenerateRequest, session: AsyncSession = Depends(get_db)) -> GeneratedTestOut:
    service = TestService()
    try:
        generated = await service.generate_test(
            session=session,
            project_id=payload.project_id,
            prompt=payload.prompt,
            context=payload.context,
            ai_debug=payload.ai_debug,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LLMServiceUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível conectar ao provedor de IA (Groq). Verifique internet do container, DNS e GROQ_API_KEY.",
        ) from exc
    except ScanUnavailableError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Não foi possível escanear a página do projeto antes de gerar o teste: {exc}",
        ) from exc
    return GeneratedTestOut.model_validate(generated)


@router.post("/scan")
async def scan_page(payload: ScanRequest) -> StreamingResponse:
    scanner = ElementScannerService()

    async def event_stream():
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def on_progress(message: str) -> None:
            await queue.put({"type": "progress", "message": message})

        async def run_scan() -> None:
            try:
                result = await scanner.scan_url(str(payload.url), progress_callback=on_progress)
                await queue.put({"type": "result", "data": result.model_dump()})
            except ElementScannerError as exc:
                await queue.put({"type": "error", "message": str(exc)})
            finally:
                await queue.put({"type": "done"})

        task = asyncio.create_task(run_scan())

        try:
            while True:
                event = await queue.get()
                if event.get("type") == "done":
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/tests/{test_id}", response_model=GeneratedTestOut)
async def get_test(test_id: int, session: AsyncSession = Depends(get_db)) -> GeneratedTestOut:
    service = TestService()
    generated = await service.get_generated_test(session, test_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Test not found")
    return GeneratedTestOut.model_validate(generated)


@router.delete("/tests/{test_id}")
async def delete_test(test_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    service = TestService()
    deleted = await service.delete_generated_test(session, test_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Test not found")
    return {"message": "Teste deletado com sucesso"}


@router.get("/tests/{test_id}/download")
async def download_test(test_id: int, session: AsyncSession = Depends(get_db)) -> FileResponse:
    service = TestService()
    generated = await service.get_generated_test(session, test_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Test not found")
    return FileResponse(path=generated.file_path, filename=f"test_{test_id}.robot")


@router.get("/projects/{project_id}/executions", response_model=list[TestExecutionResult])
async def list_project_executions(project_id: int, session: AsyncSession = Depends(get_db)) -> list[TestExecutionResult]:
    """Return the execution history for a project."""
    service = TestExecutionService()
    executions = await service.list_executions_by_project(session, project_id)
    return [TestExecutionResult.model_validate(e) for e in executions]


@router.post("/executions/run", response_model=TestExecutionResult)
async def execute_tests(payload: TestExecutionRequest, session: AsyncSession = Depends(get_db)) -> TestExecutionResult:
    """Execute Robot Framework tests for a project and generate MkDocs report."""
    service = TestExecutionService()
    try:
        execution = await service.execute_tests(
            session=session,
            project_id=payload.project_id,
            test_ids=payload.test_ids,
            ai_debug=payload.ai_debug,
            headless=payload.headless,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TestExecutionResult.model_validate(execution)


@router.get("/executions/{execution_id}/report")
async def get_execution_report(execution_id: int) -> FileResponse:
    """Serve the MkDocs generated report."""
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/ai/metrics")
async def get_ai_metrics() -> dict[str, float | int]:
    """Return AI self-healing metrics."""
    return AIMetricsRegistry.instance().as_dict()


class RobotImproveRequest(BaseModel):
    content: str


class RobotImproveResponse(BaseModel):
    content: str


@router.post("/tests/{test_id}/improve", response_model=RobotImproveResponse)
async def improve_robot_test(
    test_id: int,
    payload: RobotImproveRequest,
    session: AsyncSession = Depends(get_db),
) -> RobotImproveResponse:
    """Send current .robot content to the AI (with page scan context) and return an improved version."""
    service = TestService()
    improved = await service.improve_robot_test(session=session, test_id=test_id, content=payload.content)
    if improved is None:
        raise HTTPException(status_code=404, detail="Test not found")
    return RobotImproveResponse(content=improved)


@router.put("/tests/{test_id}/content", response_model=GeneratedTestOut)
async def update_robot_test_content(
    test_id: int,
    payload: RobotImproveRequest,
    session: AsyncSession = Depends(get_db),
) -> GeneratedTestOut:
    """Persist edited .robot content back to disk and DB."""
    service = TestService()
    generated = await service.save_robot_test_content(session, test_id, payload.content)
    if not generated:
        raise HTTPException(status_code=404, detail="Test not found")
    return GeneratedTestOut.model_validate(generated)
