from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BuilderSession:
    session_id: str
    url: str
    created_at_epoch: float


class InMemoryEventStore:
    """Thread-safe in-memory storage for captured builder events."""

    def __init__(self) -> None:
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._sessions: dict[str, BuilderSession] = {}
        self._latest_session_id: str | None = None
        self._lock = asyncio.Lock()

    async def create_session(self, url: str) -> BuilderSession:
        async with self._lock:
            session = BuilderSession(
                session_id=str(uuid.uuid4()),
                url=url,
                created_at_epoch=time.time(),
            )
            self._sessions[session.session_id] = session
            self._events[session.session_id] = []
            self._latest_session_id = session.session_id
            return session

    async def add_event(self, session_id: str, event: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            if session_id not in self._sessions:
                raise ValueError(f"Builder session '{session_id}' not found")

            step_index = len(self._events[session_id]) + 1
            normalized = {
                "step": step_index,
                "session_id": session_id,
                "timestamp": time.time(),
                **event,
            }
            self._events[session_id].append(normalized)
            self._latest_session_id = session_id
            return normalized

    async def get_steps(self, session_id: str | None = None) -> list[dict[str, Any]]:
        async with self._lock:
            resolved_session = session_id or self._latest_session_id
            if not resolved_session:
                return []
            return list(self._events.get(resolved_session, []))

    async def get_session(self, session_id: str | None = None) -> BuilderSession | None:
        async with self._lock:
            resolved_session = session_id or self._latest_session_id
            if not resolved_session:
                return None
            return self._sessions.get(resolved_session)

    async def clear_session(self, session_id: str) -> None:
        async with self._lock:
            self._events.pop(session_id, None)
            self._sessions.pop(session_id, None)
            if self._latest_session_id == session_id:
                self._latest_session_id = next(iter(self._sessions), None)
