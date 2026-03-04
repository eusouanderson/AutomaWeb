from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.generated_test import GeneratedTestOut
from app.schemas.project import ProjectCreate, ProjectOut
from app.schemas.test_request import TestGenerateRequest
from app.services.project_service import ProjectService
from app.services.test_service import TestService

router = APIRouter()


@router.post("/projects", response_model=ProjectOut)
async def create_project(payload: ProjectCreate, session: AsyncSession = Depends(get_db)) -> ProjectOut:
    service = ProjectService()
    project = await service.create_project(session, name=payload.name, description=payload.description)
    return ProjectOut.model_validate(project)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(session: AsyncSession = Depends(get_db)) -> list[ProjectOut]:
    service = ProjectService()
    projects = await service.list_projects(session)
    return [ProjectOut.model_validate(project) for project in projects]


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
