"""The files a release is built from (spec §3, §4, §7): the build context, the compose file the desktop app writes out,
and the release workflow. Each test pins the spec's values; the builds themselves run in the plan and in CI."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

# The api image holds only backend/, so there is no checkout around this file there.
pytestmark = pytest.mark.skipif(not (ROOT / "docker-compose.yml").exists(), reason="needs the repository checkout")


def test_the_build_context_leaves_out_every_env_file_and_every_local_folder():
    """Docker reads these patterns from the context root: a bare `.env` or `node_modules` would still let
    frontend/.env* and frontend/node_modules into the image (spec §3)."""
    patterns = set((ROOT / ".dockerignore").read_text().split())
    required = {"**/.env", "**/.env.*", "**/node_modules", "**/.venv", ".git", "docs", "desktop", "frontend/dist"}

    assert required <= patterns
    assert {".env", "node_modules", ".venv"} & patterns == set()


def test_the_image_builds_the_frontend_from_the_committed_api_types_and_serves_it():
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "RUN npx tsc -b && npx vite build" in dockerfile
    assert "npm run build" not in dockerfile  # its prebuild regenerates the types from a running API
    assert "FRONTEND_DIST=/app/web" in dockerfile
    assert dockerfile.index("COPY --from=deps /venv /venv") < dockerfile.index("COPY backend/ ./")  # venv, then code


APP_IMAGE = "ghcr.io/khannoussi-malek/paperlab:${PAPERLAB_VERSION:-dev}"
OPTIONAL_ENV = [{"path": ".env", "required": False}]


def compose(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text())


def test_the_release_stack_runs_the_published_image_and_pinned_databases():
    release = compose("desktop/docker-compose.yml")
    services = release["services"]

    assert release["name"] == "paperlab-app"
    assert set(services) == {"db", "redis", "migrate", "api", "worker"}
    assert services["db"]["image"] == "pgvector/pgvector:0.8.6-pg16"
    assert services["redis"]["image"] == "redis:7.4.11-alpine"
    assert [services[name]["image"] for name in ("migrate", "api", "worker")] == [APP_IMAGE] * 3
    assert "latest" not in (ROOT / "desktop/docker-compose.yml").read_text()
    for name, service in services.items():
        assert {"build", "restart"} & set(service) == set(), name  # nothing starts with the computer
        assert all(volume.split(":")[0] in release["volumes"] for volume in service.get("volumes", [])), name


def test_migrate_runs_once_before_the_api_and_the_worker_which_run_as_pid_1():
    services = compose("desktop/docker-compose.yml")["services"]

    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["migrate"]["depends_on"] == {"db": {"condition": "service_healthy"}}
    assert services["api"]["command"] == ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    assert services["worker"]["command"] == ["arq", "app.workers.settings.WorkerSettings"]
    for name in ("api", "worker"):
        assert services[name]["depends_on"]["migrate"] == {"condition": "service_completed_successfully"}
        assert services[name]["extra_hosts"] == ["host.docker.internal:host-gateway"]
        assert services[name]["environment"]["LLM_PROVIDER"] == "${LLM_PROVIDER:-ollama}"
        assert services[name]["environment"]["DISCOVERY_PROVIDER"] == "${DISCOVERY_PROVIDER:-live}"
    assert services["api"]["environment"]["PAPERLAB_DIR"] == "${PAPERLAB_DIR:-${PWD:-}}"


def test_only_the_api_is_published_and_only_on_this_computer():
    services = compose("desktop/docker-compose.yml")["services"]

    published = {name: service["ports"] for name, service in services.items() if "ports" in service}
    assert published == {"api": ["127.0.0.1:${PAPERLAB_PORT:-5190}:8000"]}


def test_the_library_lives_in_named_volumes_and_redis_keeps_its_queue():
    release = compose("desktop/docker-compose.yml")
    services = release["services"]

    assert set(release["volumes"]) == {"pgdata", "pdfs", "redisdata", "models"}
    assert services["redis"]["command"] == ["redis-server", "--appendonly", "yes"]
    assert services["redis"]["volumes"] == ["redisdata:/data"]
    for name in ("api", "worker"):
        assert "models:/models" in services[name]["volumes"]


def test_no_env_file_is_needed_in_either_stack():
    """Every setting has a default in config.py, so `cp .env.example .env` left the Quick start."""
    release = compose("desktop/docker-compose.yml")["services"]

    assert [release[name]["env_file"] for name in ("migrate", "api", "worker")] == [OPTIONAL_ENV] * 3
    assert compose("docker-compose.yml")["x-backend"]["env_file"] == OPTIONAL_ENV
