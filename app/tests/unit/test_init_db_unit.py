from sqlalchemy import create_engine, inspect, text

from app.db.init_db import _ensure_project_test_directory_column, _ensure_project_url_column


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
