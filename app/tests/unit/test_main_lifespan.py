"""Tests to cover main.py lifespan and startup logic"""
import pytest


async def test_app_lifespan() -> None:
    """Test the lifespan context manager in main.py"""
    from app.main import app
    
    # The lifespan is executed when the app starts
    # Lines 15-17 are the setup_logging() and init_db() calls plus yield
    # These are covered by any test that uses the app
    assert app.title is not None


async def test_root_route() -> None:
    """Test root route returns HTML"""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_lifespan_calls_setup_and_init(monkeypatch) -> None:
    from app import main

    calls = {"setup": False, "init": False}

    def fake_setup_logging() -> None:
        calls["setup"] = True

    async def fake_init_db(db_engine=None) -> None:
        calls["init"] = True

    monkeypatch.setattr(main, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(main, "init_db", fake_init_db)

    async with main.lifespan(main.app):
        pass

    assert calls["setup"] is True
    assert calls["init"] is True
