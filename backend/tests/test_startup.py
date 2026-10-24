"""Exercise shipped startup commands without binding sockets or calling providers."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from app.core.config import Settings


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def startup_command(target):
    if target == "render":
        blueprint = (REPO_ROOT / "render.yaml").read_text()
        return next(line.split(":", 1)[1].strip() for line in blueprint.splitlines() if line.strip().startswith("startCommand:"))
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text()
    command = json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")))
    assert command[:2] == ["sh", "-c"]
    return command[2]


@pytest.fixture
def startup_environment(tmp_path):
    if os.name != "posix":
        pytest.skip("Render and Docker startup commands use a POSIX shell.")
    # Run real local migrations/seeding. Only replace the final listening process
    # with an argv recorder, so no port is ever opened by these tests.
    shim = tmp_path / "python"
    shim.write_text(f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
with Path(os.environ["STARTUP_CALLS"]).open("a") as output:
    output.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:3] != ["-m", "uvicorn"]:
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
""")
    shim.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "DATABASE_URL": f"sqlite+pysqlite:///{tmp_path / 'startup.db'}",
        "DEBUG": "false",
        "PORT": "9187",
        "FORWARDED_ALLOW_IPS": "198.51.100.0/24",
        "STARTUP_CALLS": str(tmp_path / "calls.jsonl"),
    }


@pytest.mark.parametrize("target", ["render", "docker"])
def test_startup_migrates_and_seeds_before_binding_host_port(target, startup_environment):
    result = subprocess.run(
        ["sh", "-c", startup_command(target)],
        cwd=BACKEND_ROOT,
        env=startup_environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in Path(startup_environment["STARTUP_CALLS"]).read_text().splitlines()]
    assert calls[:2] == [["-m", "alembic", "upgrade", "head"], ["-m", "app.db.seed"]]
    assert calls[2] == [
        "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9187",
        "--proxy-headers", "--forwarded-allow-ips", "198.51.100.0/24",
    ]


@pytest.mark.parametrize("target", ["render", "docker"])
def test_migration_connection_failure_stops_startup_loudly(target, startup_environment, tmp_path):
    # A missing SQLite directory simulates a connection error without networking.
    startup_environment["DATABASE_URL"] = f"sqlite+pysqlite:///{tmp_path / 'missing' / 'database.db'}"
    result = subprocess.run(
        ["sh", "-c", startup_command(target)],
        cwd=BACKEND_ROOT,
        env=startup_environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "OperationalError" in result.stderr
    calls = [json.loads(line) for line in Path(startup_environment["STARTUP_CALLS"]).read_text().splitlines()]
    assert calls == [["-m", "alembic", "upgrade", "head"]]


def test_render_requires_proxy_trust_configuration(startup_environment):
    startup_environment.pop("FORWARDED_ALLOW_IPS")
    result = subprocess.run(
        ["sh", "-c", startup_command("render")],
        cwd=BACKEND_ROOT,
        env=startup_environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Configure trusted proxy IPs or CIDRs" in result.stderr
    calls = [json.loads(line) for line in Path(startup_environment["STARTUP_CALLS"]).read_text().splitlines()]
    assert not any(call[:2] == ["-m", "uvicorn"] for call in calls)


def test_deploy_guide_and_template_cover_all_app_settings():
    documented = set(re.findall(r"`([A-Z_]+)`", (REPO_ROOT / "DEPLOY.md").read_text()))
    example = {
        line.split("=", 1)[0]
        for line in (BACKEND_ROOT / ".env.example").read_text().splitlines()
        if line and not line.startswith("#")
    }
    app_variables = {name.upper() for name in Settings.model_fields}

    assert app_variables <= example
    assert example | app_variables | {"PYTHON_VERSION"} <= documented
    blueprint = (REPO_ROOT / "render.yaml").read_text()
    declared = set(re.findall(r"- key: ([A-Z_]+)", blueprint))
    assert example - {"PORT"} <= declared  # PORT is supplied by Render itself.
