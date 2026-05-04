from __future__ import annotations

from app.builder.event_store import InMemoryEventStore


async def test_should_create_session_and_return_it_as_latest() -> None:
    store = InMemoryEventStore()

    session = await store.create_session('https://example.com')

    assert session.url == 'https://example.com'
    assert await store.get_session() == session
    assert await store.get_steps() == []


async def test_should_add_events_with_incremental_steps() -> None:
    store = InMemoryEventStore()
    session = await store.create_session('https://example.com')

    first = await store.add_event(session.session_id, {'action': 'click'})
    second = await store.add_event(session.session_id, {'action': 'input', 'value': 'abc'})

    assert first['step'] == 1
    assert first['session_id'] == session.session_id
    assert 'timestamp' in first
    assert second['step'] == 2
    assert second['value'] == 'abc'
    assert await store.get_steps(session.session_id) == [first, second]


async def test_should_raise_for_unknown_session_on_add_event() -> None:
    store = InMemoryEventStore()

    try:
        await store.add_event('missing', {'action': 'click'})
    except ValueError as exc:
        assert "Builder session 'missing' not found" in str(exc)
    else:
        raise AssertionError('ValueError not raised for unknown session')


async def test_should_resolve_latest_session_when_id_is_omitted() -> None:
    store = InMemoryEventStore()
    first = await store.create_session('https://one.example.com')
    second = await store.create_session('https://two.example.com')

    await store.add_event(first.session_id, {'action': 'click', 'selector': '#first'})
    latest_event = await store.add_event(
        second.session_id,
        {'action': 'click', 'selector': '#second'},
    )

    assert await store.get_session() == second
    assert await store.get_steps() == [latest_event]


async def test_should_clear_session_and_fall_back_to_remaining_latest() -> None:
    store = InMemoryEventStore()
    first = await store.create_session('https://one.example.com')
    second = await store.create_session('https://two.example.com')

    await store.add_event(first.session_id, {'action': 'click', 'selector': '#first'})
    await store.add_event(second.session_id, {'action': 'click', 'selector': '#second'})

    await store.clear_session(second.session_id)

    assert await store.get_session(second.session_id) is None
    assert await store.get_session() == first
    assert len(await store.get_steps()) == 1


async def test_should_handle_clear_and_reads_without_any_session() -> None:
    store = InMemoryEventStore()

    await store.clear_session('missing')

    assert await store.get_session() is None
    assert await store.get_steps() == []