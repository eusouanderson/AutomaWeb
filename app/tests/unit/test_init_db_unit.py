from sqlalchemy import create_engine, inspect, text
import pytest

from app.db.init_db import (
    init_db,
    _ensure_project_test_directory_column,
    _ensure_project_url_column,
    _ensure_test_execution_columns,
)


def test_ensure_project_test_directory_column_adds_column() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR(150), description TEXT, created_at DATETIME)"
            )
        )
        _ensure_project_test_directory_column(conn)
        columns = {col["name"] for col in inspect(conn).get_columns("projects")}
        assert "test_directory" in columns


def test_ensure_project_test_directory_column_noop_when_exists() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR(150), description TEXT, test_directory VARCHAR(500), created_at DATETIME)"
            )
        )
        _ensure_project_test_directory_column(conn)
        columns = {col["name"] for col in inspect(conn).get_columns("projects")}
        assert "test_directory" in columns


def test_ensure_project_url_column_adds_column() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR(150), description TEXT, created_at DATETIME)"
            )
        )
        _ensure_project_url_column(conn)
        columns = {col["name"] for col in inspect(conn).get_columns("projects")}
        assert "url" in columns


def test_ensure_project_url_column_noop_when_exists() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE projects (id INTEGER PRIMARY KEY, name VARCHAR(150), description TEXT, url VARCHAR(1000), created_at DATETIME)"
            )
        )
        _ensure_project_url_column(conn)
        columns = {col["name"] for col in inspect(conn).get_columns("projects")}
        assert "url" in columns


def test_ensure_test_execution_columns_adds_missing_columns() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE test_executions (id INTEGER PRIMARY KEY, project_id INTEGER, status VARCHAR(20))"
            )
        )
        _ensure_test_execution_columns(conn)
        columns = {col["name"] for col in inspect(conn).get_columns("test_executions")}
        assert "error_output" in columns
        assert "mkdocs_index" in columns


def test_ensure_test_execution_columns_noop_when_columns_exist() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE test_executions ("
                "id INTEGER PRIMARY KEY, "
                "project_id INTEGER, "
                "status VARCHAR(20), "
                "error_output TEXT, "
                "mkdocs_index VARCHAR(500)"
                ")"
            )
        )
        _ensure_test_execution_columns(conn)
        columns = {col["name"] for col in inspect(conn).get_columns("test_executions")}
        assert "error_output" in columns
        assert "mkdocs_index" in columns


@pytest.mark.asyncio
async def test_init_db_runs_all_sync_steps() -> None:
    calls = []

    class FakeConn:
        async def run_sync(self, fn):
            calls.append(fn.__name__)

    class FakeBeginCtx:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBeginCtx()

    await init_db(FakeEngine())

    assert calls == [
        "create_all",
        "_ensure_project_test_directory_column",
        "_ensure_project_url_column",
        "_ensure_test_execution_columns",
    ]
