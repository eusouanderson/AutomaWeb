import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tenacity import RetryError

from app.core.config import settings
from app.db.base import Base
from app.models.project import Project
from app.services.element_scanner import ElementScannerError
from app.services.test_service import LLMServiceUnavailableError, ScanUnavailableError, TestService


class DummyGroqClient:
    def generate_robot_test(
        self,
        prompt: str,
        context: str | None = None,
        page_structure: dict | None = None,
    ) -> str:
        return "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nExample\n    Log    Hello"


class FailingScanService:
    async def scan_url(self, _url: str):
        raise ElementScannerError("scan is down")


class ScanResultMock:
    def model_dump(self):
        return {"title": "Page"}


class SuccessfulScanService:
    async def scan_url(self, _url: str):
        return ScanResultMock()


class DummyProjectRepository:
    def __init__(self, project):
        self.project = project

    async def get(self, session, project_id):
        return self.project


class DummyTestRepository:
    def __init__(self):
        self.updated_statuses = []
        self.generated_to_return = None
        self.deleted_item = None

    async def create_test_request(self, session, test_request):
        test_request.id = 42
        return test_request

    async def update_test_request(self, session, test_request):
        self.updated_statuses.append(test_request.status)
        return test_request

    async def create_generated_test(self, session, generated_test):
        generated_test.id = 99
        return generated_test

    async def get_generated_test(self, session, test_id):
        return self.generated_to_return

    async def delete_generated_test(self, session, generated):
        self.deleted_item = generated

    async def list_generated_tests_by_project(self, session, project_id):
        return ["dummy"]


class DummyRetryError(RetryError):
    def __init__(self):
        Exception.__init__(self, "retry exhausted")


class RetryFailingGroqClient:
    def generate_robot_test(self, prompt, context=None, page_structure=None):
        raise DummyRetryError()


class APIConnectionError(Exception):
    pass


class APIConnectionFailingGroqClient:
    def generate_robot_test(self, prompt, context=None, page_structure=None):
        raise APIConnectionError("network")


@pytest_asyncio.fixture()
async def session(tmp_path) -> AsyncSession:
    settings.STATIC_DIR = str(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_generate_test(session: AsyncSession) -> None:
    project = Project(name="Projeto Teste", description="Desc")
    session.add(project)
    await session.commit()
    await session.refresh(project)

    service = TestService(groq_client=DummyGroqClient())
    generated = await service.generate_test(
        session=session,
        project_id=project.id,
        prompt="Gerar teste",
        context="Contexto",
    )

    assert generated.id is not None
    assert "*** Test Cases ***" in generated.content


@pytest.mark.asyncio
async def test_generate_test_raises_scan_unavailable_when_scan_fails(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url="https://example.com")
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(project),
        groq_client=DummyGroqClient(),
        element_scanner=FailingScanService(),
    )

    with pytest.raises(ScanUnavailableError, match="scan is down"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste")

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_raises_llm_unavailable_on_retry_error(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url=None)
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(project),
        groq_client=RetryFailingGroqClient(),
        element_scanner=SuccessfulScanService(),
    )

    with pytest.raises(LLMServiceUnavailableError, match="LLM provider connection failed"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste")

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_generate_test_raises_llm_unavailable_on_api_connection_error(tmp_path) -> None:
    settings.STATIC_DIR = str(tmp_path)
    project = Project(id=1, name="Projeto", description="Desc", test_directory=str(tmp_path), url=None)
    test_repo = DummyTestRepository()
    service = TestService(
        test_repository=test_repo,
        project_repository=DummyProjectRepository(project),
        groq_client=APIConnectionFailingGroqClient(),
        element_scanner=SuccessfulScanService(),
    )

    with pytest.raises(LLMServiceUnavailableError, match="LLM provider connection failed"):
        await service.generate_test(session=None, project_id=1, prompt="Gerar teste")

    assert test_repo.updated_statuses[-1] == "failed"


@pytest.mark.asyncio
async def test_list_generated_tests_by_project_raises_when_project_not_found() -> None:
    service = TestService(
        test_repository=DummyTestRepository(),
        project_repository=DummyProjectRepository(None),
        groq_client=DummyGroqClient(),
    )

    with pytest.raises(ValueError, match="Project not found"):
        await service.list_generated_tests_by_project(session=None, project_id=1)


@pytest.mark.asyncio
async def test_delete_generated_test_returns_false_when_not_found() -> None:
    test_repo = DummyTestRepository()
    service = TestService(test_repository=test_repo, project_repository=DummyProjectRepository(None), groq_client=DummyGroqClient())

    deleted = await service.delete_generated_test(session=None, test_id=1)

    assert deleted is False


@pytest.mark.asyncio
async def test_delete_generated_test_handles_unlink_error(tmp_path, monkeypatch) -> None:
    file_path = tmp_path / "generated_test_1.robot"
    file_path.write_text("*** Test Cases ***\nExample")
    generated = type("Generated", (), {"file_path": str(file_path)})()

    test_repo = DummyTestRepository()
    test_repo.generated_to_return = generated
    service = TestService(test_repository=test_repo, project_repository=DummyProjectRepository(None), groq_client=DummyGroqClient())

    def failing_unlink(self):
        raise OSError("cannot unlink")

    monkeypatch.setattr("pathlib.Path.unlink", failing_unlink)

    deleted = await service.delete_generated_test(session=None, test_id=1)

    assert deleted is True
    assert test_repo.deleted_item is generated


def test_sanitize_robot_output_filters_noise_and_normalizes_library() -> None:
    service = TestService(groq_client=DummyGroqClient())
    content = (
        "texto fora\n"
        "*** Settings ***\n"
        "Library    PlaywrightLibrary\n"
        "** nota\n"
        "Observação: remover\n"
        "*** Test Cases ***\n"
        "Caso\n"
        "    Log    Playwright\n"
    )

    cleaned = service._sanitize_robot_output(content)

    assert "PlaywrightLibrary" not in cleaned
    assert "Library    Browser" in cleaned
    assert "Observação" not in cleaned
    assert "** nota" not in cleaned
