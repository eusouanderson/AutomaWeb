import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.builder.event_store import InMemoryEventStore
from app.db.init_db import init_db


async def _make_store() -> InMemoryEventStore:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool
    )
    await init_db(engine)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    return InMemoryEventStore(session_factory=session_factory)


@pytest.mark.asyncio
async def test_add_event_raises_for_unknown_session() -> None:
    store = await _make_store()

    with pytest.raises(ValueError, match="not found"):
        await store.add_event("missing-session", {"action": "click"})


@pytest.mark.asyncio
async def test_get_steps_returns_empty_when_no_session_exists() -> None:
    store = await _make_store()
    assert await store.get_steps() == []


@pytest.mark.asyncio
async def test_get_session_returns_none_when_no_session_exists() -> None:
    store = await _make_store()
    assert await store.get_session() is None


@pytest.mark.asyncio
async def test_clear_session_removes_and_repoints_latest_session() -> None:
    store = await _make_store()

    first = await store.create_session("https://example.com/first")
    second = await store.create_session("https://example.com/second")

    await store.add_event(first.session_id, {"action": "click", "selector": "#a"})
    await store.add_event(second.session_id, {"action": "click", "selector": "#b"})

    # latest points to second before clear
    assert (await store.get_session()).session_id == second.session_id

    await store.clear_session(second.session_id)

    # latest should fallback to the remaining session
    assert (await store.get_session()).session_id == first.session_id
    remaining_steps = await store.get_steps()
    assert len(remaining_steps) == 1
    assert remaining_steps[0]["selector"] == "#a"


@pytest.mark.asyncio
async def test_clear_session_noop_for_unknown_session() -> None:
    store = await _make_store()
    session = await store.create_session("https://example.com")

    await store.clear_session("does-not-exist")

    assert (await store.get_session()).session_id == session.session_id


@pytest.mark.asyncio
async def test_update_step_persists_new_name() -> None:
    store = await _make_store()
    session = await store.create_session("https://example.com", project_id=7)

    saved = await store.add_event(
        session.session_id,
        {
            "action": "click",
            "selector": "#login",
            "step_name": "Abrir login",
            "page_url": "https://example.com/login",
        },
    )

    updated = await store.update_step(saved["id"], {"step_name": "Clicar em login"})

    assert updated["step_name"] == "Clicar em login"
    assert updated["page_url"] == "https://example.com/login"
    assert (await store.get_session(session.session_id)).project_id == 7
