from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.generated_test import GeneratedTestOut
from app.schemas.project import ProjectCreate, ProjectOut
from app.schemas.test_execution import TestExecutionRequest, TestExecutionResult
from app.schemas.test_request import TestGenerateRequest
from app.services.project_service import ProjectService
from app.services.test_execution_service import TestExecutionService
from app.services.test_service import TestService

router = APIRouter()


@router.post("/projects", response_model=ProjectOut)
async def create_project(payload: ProjectCreate, session: AsyncSession = Depends(get_db)) -> ProjectOut:
    service = ProjectService()
    try:
        project = await service.create_project(
            session, name=payload.name, description=payload.description, test_directory=payload.test_directory
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GeneratedTestOut.model_validate(generated)


@router.get("/tests/{test_id}", response_model=GeneratedTestOut)
async def get_test(test_id: int, session: AsyncSession = Depends(get_db)) -> GeneratedTestOut:
    service = TestService()
    generated = await service.get_generated_test(session, test_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Test not found")
    return GeneratedTestOut.model_validate(generated)


@router.get("/tests/{test_id}/download")
async def download_test(test_id: int, session: AsyncSession = Depends(get_db)) -> FileResponse:
    service = TestService()
    generated = await service.get_generated_test(session, test_id)
    if not generated:
        raise HTTPException(status_code=404, detail="Test not found")
    return FileResponse(path=generated.file_path, filename=f"test_{test_id}.robot")


@router.post("/executions/run", response_model=TestExecutionResult)
async def execute_tests(payload: TestExecutionRequest, session: AsyncSession = Depends(get_db)) -> TestExecutionResult:
    """Execute Robot Framework tests for a project and generate MkDocs report."""
    service = TestExecutionService()
    try:
        execution = await service.execute_tests(
            session=session,
            project_id=payload.project_id,
            test_ids=payload.test_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TestExecutionResult.model_validate(execution)


@router.get("/executions/{execution_id}/report")
async def get_execution_report(execution_id: int) -> FileResponse:
    """Serve the MkDocs generated report."""
    # This would need to fetch the execution from database and return the report
    raise HTTPException(status_code=501, detail="Not implemented yet")
