from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generated_test import GeneratedTest
from app.models.test_request import TestRequest


class TestRepository:
    """Test request and generated test data access layer."""

    async def create_test_request(self, session: AsyncSession, test_request: TestRequest) -> TestRequest:
        session.add(test_request)
        await session.commit()
        await session.refresh(test_request)
        return test_request

    async def update_test_request(self, session: AsyncSession, test_request: TestRequest) -> TestRequest:
        session.add(test_request)
        await session.commit()
        await session.refresh(test_request)
        return test_request

    async def create_generated_test(self, session: AsyncSession, generated_test: GeneratedTest) -> GeneratedTest:
        session.add(generated_test)
        await session.commit()
        await session.refresh(generated_test)
        return generated_test

    async def get_generated_test(self, session: AsyncSession, test_id: int) -> GeneratedTest | None:
        result = await session.execute(select(GeneratedTest).where(GeneratedTest.id == test_id))
        return result.scalar_one_or_none()

    async def delete_generated_test(self, session: AsyncSession, generated_test: GeneratedTest) -> None:
        await session.delete(generated_test)
        await session.commit()

    async def list_generated_tests_by_project(self, session: AsyncSession, project_id: int) -> list[GeneratedTest]:
        result = await session.execute(
            select(GeneratedTest)
            .join(TestRequest, GeneratedTest.test_request_id == TestRequest.id)
            .where(TestRequest.project_id == project_id)
            .order_by(GeneratedTest.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_generated_tests_by_ids_for_project(
        self,
        session: AsyncSession,
        project_id: int,
        test_ids: list[int],
    ) -> list[GeneratedTest]:
        if not test_ids:
            return []
        result = await session.execute(
            select(GeneratedTest)
            .join(TestRequest, GeneratedTest.test_request_id == TestRequest.id)
            .where(TestRequest.project_id == project_id, GeneratedTest.id.in_(test_ids))
        )
        return list(result.scalars().all())
