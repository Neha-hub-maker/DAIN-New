"""Deployment checks use SQLite or offline SQL; no hosted services are contacted."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import httpx
import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.config import Settings
from app.main import app


BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_hosted_postgresql_urls_use_psycopg_3(scheme):
    # Synthetic credentials exercise percent encoding and TLS parameters.
    suffix = "test_user:test%40password@database.example.test/dain?sslmode=require"
    config = Settings(_env_file=None, database_url=f"{scheme}://{suffix}")

    assert config.database_url == f"postgresql+psycopg://{suffix}"
    engine = create_engine(config.database_url)
    assert engine.dialect.driver == "psycopg"
    engine.dispose()


def test_local_sqlite_url_is_preserved():
    config = Settings(_env_file=None, database_url="sqlite+pysqlite:///:memory:")

    assert config.database_url == "sqlite+pysqlite:///:memory:"


@pytest.mark.parametrize("raw,expected", [
    ("", []),
    (" , , /// , ", []),
    (" https://dain.example.test/// ", ["https://dain.example.test"]),
    (" https://dain.example.test/ , ,https://studio.example.test:8443///, ",
     ["https://dain.example.test", "https://studio.example.test:8443"]),
])
def test_comma_separated_production_cors_from_environment(monkeypatch, raw, expected):
    monkeypatch.setenv("CORS_ORIGINS", raw)
    config = Settings(_env_file=None)

    assert config.cors_origin_list == expected


def test_production_cors_preflight_allows_only_configured_origins():
    # Import a fresh app with dashboard-style env vars, independently of conftest.
    script = """
import json
import socket
from fastapi.testclient import TestClient
from app.main import app

def no_network(*args, **kwargs):
    raise AssertionError("CORS must not open a network connection")

socket.create_connection = no_network
client = TestClient(app)
results = []
for origin in ["https://dain.example.test", "https://studio.example.test:8443", "https://unlisted.example.test"]:
    response = client.options("/submissions/verify", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization, Content-Type",
    })
    if response.status_code == 200:
        assert {"POST", "OPTIONS"} <= set(response.headers["access-control-allow-methods"].split(", "))
        assert {"authorization", "content-type"} <= set(response.headers["access-control-allow-headers"].lower().split(", "))
    results.append([response.status_code, response.headers.get("access-control-allow-origin")])
response = client.post("/submissions/verify", json={}, headers={"Origin": "https://dain.example.test"})
assert response.status_code == 401
assert response.headers["access-control-allow-origin"] == "https://dain.example.test"
print(json.dumps(results))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_ROOT,
        env={
            **os.environ,
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "DEBUG": "false",
            "CORS_ORIGINS": " https://dain.example.test///, ,https://studio.example.test:8443/, ",
        },
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == [
        [200, "https://dain.example.test"],
        [200, "https://studio.example.test:8443"],
        [400, None],
    ]


def test_health_does_not_touch_database_or_providers(client, monkeypatch):
    def no_dependencies(*args, **kwargs):
        pytest.fail("The health probe must not contact the database or providers.")

    monkeypatch.setattr(socket, "create_connection", no_dependencies)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_dependencies)
    monkeypatch.setattr("app.db.session.engine.connect", no_dependencies)
    monkeypatch.setattr("app.db.session.check_database_connection", no_dependencies)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}


def test_migrations_and_seed_are_repeatable_from_repo_root(tmp_path):
    # A literal percent sign catches Alembic/ConfigParser interpolation regressions.
    database_url = f"sqlite+pysqlite:///{tmp_path / 'migration%40test.db'}"
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "DEBUG": "false",
        "PYTHONPATH": str(BACKEND_ROOT),
    }
    for _ in range(2):
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(BACKEND_ROOT / "alembic.ini"), "upgrade", "head"],
            cwd=BACKEND_ROOT.parent,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [sys.executable, "-m", "app.db.seed"],
            cwd=BACKEND_ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    engine = create_engine(database_url)
    try:
        assert {"users", "auth_sessions", "submissions"} <= set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260826_01"
            assert connection.scalar(text("SELECT count(*) FROM achievement_categories")) == 3
    finally:
        engine.dispose()


def test_postgresql_migration_with_encoded_credentials_offline():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND_ROOT,
        env={
            **os.environ,
            "DATABASE_URL": "postgres://test_user:test%40password@database.example.test/dain?sslmode=require",
            "DEBUG": "false",
        },
        check=True,
        capture_output=True,
        text=True,
    )

    assert "CREATE TABLE users" in result.stdout
    assert "CREATE TABLE submissions" in result.stdout
