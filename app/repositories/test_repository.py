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
