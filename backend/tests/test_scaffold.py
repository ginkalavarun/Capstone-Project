"""M2 scaffold & infrastructure tests (docs/test-plan.md §M2).

Covers: the D14 error format, OpenAPI docs, the D10 CORS allowlist,
health + database readiness, the D22 ``.gitignore``, the D7 secrets
scan, and (when Docker is available) container boot / volume
persistence. Container tests skip with a recorded reason when the
docker CLI is absent.
"""
import asyncio
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi import Request

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

# A safe, non-placeholder secret for throwaway test containers (D4).
# The compose file interpolates from the *process* environment, so the
# developer's local .env is never read or needed by these tests (D23).
DOCKER_TEST_JWT_SECRET = "docker-test-secret-not-a-placeholder-123456789"
DOCKER_TEST_PORT = "8017"  # off the usual 8000 dev port


def _run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
    )


def _docker_available() -> bool:
    return shutil.which("docker") is not None


# ---------------------------------------------------------------------------
# T-M2-01 — API error format: every error body is exactly {"detail", "code"}
# ---------------------------------------------------------------------------

def test_m2_01_error_format_http_error_shape(client):
    """Unknown route → 404 with the D14 body shape (real HTTP round-trip)."""
    response = client.get("/api/v1/definitely-not-a-route")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"detail", "code"}
    assert body["code"] == "HTTP_ERROR"
    assert isinstance(body["detail"], str) and body["detail"]


def test_m2_01_error_format_validation_handler(app):
    """The registered 422 handler produces {"detail", "code"}.

    Batch 1 has no body-accepting endpoints, so the handler registered by
    ``register_error_handlers`` is invoked directly with a crafted
    ``RequestValidationError`` (unit level, same code path the API uses).
    """
    from fastapi.exceptions import RequestValidationError

    handler = app.exception_handlers[RequestValidationError]
    request = Request(scope={"type": "http", "method": "POST", "path": "/x"})
    exc = RequestValidationError(
        [
            {
                "type": "int_parsing",
                "loc": ("body", "quantity"),
                "msg": "Input should be a valid integer, got a string",
                "input": "two",
            }
        ]
    )
    response = asyncio.run(handler(request, exc))
    assert response.status_code == 422
    body = json.loads(response.body)
    assert set(body) == {"detail", "code"}
    assert body["code"] == "VALIDATION_ERROR"
    assert "quantity" in body["detail"]


# ---------------------------------------------------------------------------
# T-M2-02 — OpenAPI docs reachable (API-02)
# ---------------------------------------------------------------------------

def test_m2_02_openapi_docs_reachable(client):
    docs = client.get("/api/v1/docs")
    assert docs.status_code == 200
    assert "swagger" in docs.text.lower()

    openapi = client.get("/api/v1/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/health/db" in paths


# ---------------------------------------------------------------------------
# T-M2-03 — CORS allowlist (API-04, D10): explicit origins, no wildcards
# ---------------------------------------------------------------------------

def test_m2_03_cors_allowlisted_origin_is_granted(client):
    response = client.get(
        "/api/v1/health", headers={"Origin": "http://localhost:5173"}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == (
        "http://localhost:5173"
    )


def test_m2_03_cors_non_allowlisted_origin_gets_nothing(client):
    response = client.get(
        "/api/v1/health", headers={"Origin": "http://evil.example"}
    )
    assert response.status_code == 200  # the API itself is fine
    assert "access-control-allow-origin" not in response.headers


# ---------------------------------------------------------------------------
# Health + database readiness (supports T-M2-04; D1 FK pragma proof)
# ---------------------------------------------------------------------------

def test_health_liveness_and_request_id(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # MW-03: every response carries a request id (full middleware test
    # arrives with batch 7, T-M8-10).
    assert response.headers.get("X-Request-Id")


def test_health_db_ready_and_fk_pragma_active(client):
    """The readiness endpoint must prove the D1 per-connection pragma."""
    response = client.get("/api/v1/health/db")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["foreign_keys_enabled"] is True


# ---------------------------------------------------------------------------
# T-M2-04 — container boot (DOCKER-01). Skips without a docker CLI.
# ---------------------------------------------------------------------------

def _compose_env() -> dict:
    env = os.environ.copy()
    env["JWT_SECRET"] = DOCKER_TEST_JWT_SECRET
    env["BACKEND_HOST_PORT"] = DOCKER_TEST_PORT
    return env


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker CLI not installed on this machine — run manually on a Docker machine",
)
def test_m2_04_container_boot():
    import httpx

    up = subprocess.run(
        ["docker", "compose", "up", "-d", "--wait", "--timeout", "180", "backend"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, env=_compose_env(),
    )
    try:
        ok = False
        for _ in range(30):
            try:
                r = httpx.get(
                    f"http://127.0.0.1:{DOCKER_TEST_PORT}/api/v1/health", timeout=3
                )
                ok = r.status_code == 200
            except httpx.HTTPError:
                ok = False
            if ok:
                break
            time.sleep(2)
        assert ok, "container did not serve /api/v1/health within 60s"
    finally:
        # NON-destructive: no `-v` (the named volume is user data).
        subprocess.run(
            ["docker", "compose", "down"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300, env=_compose_env(),
        )
    if up.returncode != 0:
        pytest.fail(f"docker compose up failed: {up.stderr[-500:]}")


# ---------------------------------------------------------------------------
# T-M2-05 — volume persistence across down/up (DOCKER-02, D1).
# Skips without a docker CLI.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _docker_available(),
    reason="docker CLI not installed on this machine — run manually on a Docker machine",
)
def test_m2_05_volume_persistence():
    def compose(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "compose", *args],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, env=_compose_env(),
        )

    compose("up", "-d", "--wait", "--timeout", "180", "backend")
    try:
        # Write data through the app's own seed (D21) into the /data volume.
        seeded = compose("exec", "-T", "backend", "python", "-m", "app.seed")
        assert seeded.returncode == 0, seeded.stderr[-500:]
        # Non-destructive restart: NO -v flag — the named volume survives.
        compose("down")
        compose("up", "-d", "--wait", "--timeout", "180", "backend")
        count = compose(
            "exec", "-T", "backend", "python", "-c",
            "import os; from sqlalchemy import create_engine, text; "
            "e = create_engine(os.environ['DATABASE_URL']); "
            "print(e.connect().execute(text('SELECT COUNT(*) FROM users')).scalar())",
        )
        users = int(count.stdout.strip().splitlines()[-1])
        assert users == 6, f"expected 6 persisted users, got {users}"
    finally:
        compose("down")  # still non-destructive (no -v)


# ---------------------------------------------------------------------------
# T-M2-06 — secrets out of repo and image (DOCKER-03, D7, D23)
# ---------------------------------------------------------------------------

def test_m2_06_no_secrets_or_artifacts_tracked():
    """The *tracked* file set must never contain secrets or local data."""
    tracked = _run_git("ls-files").stdout.splitlines()
    assert tracked, "git ls-files returned nothing — is this a git checkout?"
    for f in tracked:
        name = f.rsplit("/", 1)[-1]
        assert name != ".env", f"tracked env file: {f}"
        assert not (name.endswith(".env") and not name.endswith(".env.example")), f
        assert not f.endswith((".db", ".sqlite3")), f"tracked database: {f}"
        assert not (f.startswith("data/") or "/data/" in f), f"tracked data dir: {f}"
        assert "node_modules" not in f, f
        assert ".venv" not in f, f
        assert "__pycache__" not in f, f
        assert not f.startswith("dist/"), f


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker CLI not installed on this machine — run manually on a Docker machine",
)
def test_m2_06_no_secrets_in_image():
    tag = "campusbite-backend-secretscan"
    build = subprocess.run(
        ["docker", "build", "-q", "-t", tag, str(BACKEND_DIR)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
    )
    assert build.returncode == 0, build.stderr[-1000:]
    try:
        check = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "sh", tag, "-c",
             "test ! -e /app/.env && test ! -e /.env && "
             "! ls /app | grep -qE '\\.db$|node_modules|\\.venv'"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        assert check.returncode == 0, (
            f"image contains excluded artifacts: {check.stderr[-500:]}"
        )
    finally:
        subprocess.run(
            ["docker", "rmi", "-f", tag],
            cwd=REPO_ROOT, capture_output=True, timeout=60,
        )


# ---------------------------------------------------------------------------
# T-M2-07 — .gitignore is effective for local run artifacts (DOC-02, D22)
# ---------------------------------------------------------------------------

def test_m2_07_gitignore_patterns():
    cases = {
        # path (relative to repo root): expected `git check-ignore` result
        "backend/data/campusbite.db": True,
        "backend/data/campusbite.sqlite3": True,
        "backend/.env": True,
        "backend/.env.example": False,  # the documented exception
        "backend/.venv/bin/python": True,
        "backend/__pycache__/app.cpython-312.pyc": True,
        "backend/.pytest_cache/v/cache": True,
        "backend/campusbite.db": True,
        "frontend/.env": True,
        "frontend/node_modules/react/index.js": True,
        "frontend/dist/index.js": True,
        "data/anything": True,
        ".DS_Store": True,
    }
    for rel, should_ignore in cases.items():
        result = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=REPO_ROOT, capture_output=True, timeout=30,
        )
        assert (result.returncode == 0) is should_ignore, (
            f"{rel}: expected ignored={should_ignore}"
        )


def test_m2_07_git_status_has_no_secret_or_data_noise():
    """Untracked files visible to git must never be local artifacts."""
    status = _run_git("status", "--porcelain")
    for line in status.stdout.splitlines():
        path = line[3:].strip()
        bad = (
            path == ".env"
            or path.endswith(".env")
            and not path.endswith(".env.example")
            or path.endswith((".db", ".sqlite3"))
            or path.startswith(("data/", "node_modules", ".venv", "dist/"))
            or "__pycache__" in path
        )
        assert not bad, f"untracked local artifact visible to git: {line!r}"
