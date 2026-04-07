import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_root_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")


async def test_app_title() -> None:
    assert app.title is not None


async def test_static_mounts() -> None:
    assert any(route.path == "/static/frontend/node_modules" for route in app.routes) # type: ignore[arg-type]
    assert any(route.path == "/static/frontend" for route in app.routes) # type: ignore[arg-type]
    assert any(route.path == "/static" for route in app.routes) # type: ignore[arg-type]
