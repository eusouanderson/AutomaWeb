from app.schemas.project import ProjectCreate, ProjectOut
from datetime import datetime


def test_project_create_schema() -> None:
    project = ProjectCreate(name="Test Project", description="Test Description")
    assert project.name == "Test Project"
    assert project.description == "Test Description"


def test_project_create_schema_no_description() -> None:
    project = ProjectCreate(name="Test Project")
    assert project.name == "Test Project"
    assert project.description is None


def test_project_out_schema() -> None:
    now = datetime.utcnow()
    project = ProjectOut(
        id=1,
        name="Test Project",
        description="Test Description",
        created_at=now
    )
    assert project.id == 1
    assert project.name == "Test Project"
    assert project.description == "Test Description"
    assert project.created_at == now
