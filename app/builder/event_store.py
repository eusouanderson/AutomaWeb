from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.session import AsyncSessionLocal
from app.models.builder import BuilderSession as BuilderSessionModel
from app.models.builder import BuilderStep


@dataclass(slots=True)
class BuilderSession:
    session_id: str
    url: str
    created_at_epoch: float
    project_id: int | None = None


class InMemoryEventStore:
    """Thread-safe persistent storage for captured builder events."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker | None = None,
    ) -> None:
        self._session_factory = session_factory or AsyncSessionLocal
        self._latest_session_id: str | None = None
        self._lock = asyncio.Lock()

    async def create_session(
        self, url: str, project_id: int | None = None
    ) -> BuilderSession:
        async with self._lock:
            session = BuilderSessionModel(
                session_id=str(uuid.uuid4()),
                url=url,
                project_id=project_id,
            )
            async with self._session_factory() as db_session:
                db_session.add(session)
                await db_session.commit()
            self._latest_session_id = session.session_id
            return self._serialize_session(session)

    async def add_event(self, session_id: str, event: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            async with self._session_factory() as db_session:
                session = await db_session.get(BuilderSessionModel, session_id)
                if not session:
                    raise ValueError(f"Builder session '{session_id}' not found")

                step_index = (
                    await db_session.scalar(
                        select(func.max(BuilderStep.step)).where(
                            BuilderStep.session_id == session_id
                        )
                    )
                    or 0
                ) + 1
                normalized = BuilderStep(
                    session_id=session_id,
                    step=step_index,
                    action=str(event.get("action", "")),
                    selector=str(event.get("selector", "")),
                    value=self._none_if_blank(event.get("value")),
                    description=self._none_if_blank(event.get("description")),
                    step_name=self._none_if_blank(event.get("step_name")),
                    page_url=self._none_if_blank(event.get("page_url")),
                    page_title=self._none_if_blank(event.get("page_title")),
                    element_tag=self._none_if_blank(event.get("element_tag")),
                    element_text=self._none_if_blank(event.get("element_text")),
                    input_type=self._none_if_blank(event.get("input_type")),
                    href=self._none_if_blank(event.get("href")),
                )
                db_session.add(normalized)
                await db_session.commit()
                await db_session.refresh(normalized)

            self._latest_session_id = session_id
            return self._serialize_step(normalized)

    async def update_step(
        self, step_id: int, updates: dict[str, Any]
    ) -> dict[str, Any]:
        async with self._lock:
            async with self._session_factory() as db_session:
                step = await db_session.get(BuilderStep, step_id)
                if not step:
                    raise ValueError(f"Builder step '{step_id}' not found")

                if "step_name" in updates:
                    step.step_name = self._none_if_blank(updates.get("step_name"))
                if "description" in updates:
                    step.description = self._none_if_blank(updates.get("description"))

                await db_session.commit()
                await db_session.refresh(step)
                self._latest_session_id = step.session_id
                return self._serialize_step(step)

    async def get_steps(self, session_id: str | None = None) -> list[dict[str, Any]]:
        resolved_session = session_id or self._latest_session_id
        if not resolved_session:
            session = await self.get_session()
            resolved_session = session.session_id if session else None
        if not resolved_session:
            return []

        async with self._session_factory() as db_session:
            result = await db_session.execute(
                select(BuilderStep)
                .where(BuilderStep.session_id == resolved_session)
                .order_by(BuilderStep.step.asc(), BuilderStep.id.asc())
            )
            return [self._serialize_step(step) for step in result.scalars().all()]

    async def get_session(self, session_id: str | None = None) -> BuilderSession | None:
        resolved_session = session_id or self._latest_session_id

        async with self._session_factory() as db_session:
            if resolved_session:
                session = await db_session.get(BuilderSessionModel, resolved_session)
                if session:
                    self._latest_session_id = session.session_id
                    return self._serialize_session(session)

            result = await db_session.execute(
                select(BuilderSessionModel).order_by(BuilderSessionModel.created_at.desc())
            )
            session = result.scalars().first()
            if not session:
                return None

            self._latest_session_id = session.session_id
            return self._serialize_session(session)

    async def clear_session(self, session_id: str) -> None:
        async with self._lock:
            async with self._session_factory() as db_session:
                await db_session.execute(
                    delete(BuilderStep).where(BuilderStep.session_id == session_id)
                )
                await db_session.execute(
                    delete(BuilderSessionModel).where(
                        BuilderSessionModel.session_id == session_id
                    )
                )
                await db_session.commit()
            if self._latest_session_id == session_id:
                self._latest_session_id = None

    @staticmethod
    def _none_if_blank(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _serialize_session(session: BuilderSessionModel) -> BuilderSession:
        created_at = session.created_at or None
        return BuilderSession(
            session_id=session.session_id,
            url=session.url,
            created_at_epoch=created_at.timestamp() if created_at else time.time(),
            project_id=session.project_id,
        )

    @staticmethod
    def _serialize_step(step: BuilderStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "step": step.step,
            "session_id": step.session_id,
            "timestamp": step.created_at.timestamp() if step.created_at else time.time(),
            "action": step.action,
            "type": step.action,
            "selector": step.selector,
            "value": step.value,
            "description": step.description,
            "step_name": step.step_name,
            "page_url": step.page_url,
            "page_title": step.page_title,
            "element_tag": step.element_tag,
            "element_text": step.element_text,
            "input_type": step.input_type,
            "href": step.href,
        }
