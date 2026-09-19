"""The files a release is built from (spec §3, §4, §7): the build context, the compose file the desktop app writes out,
and the release workflow. Each test pins the spec's values; the builds themselves run in the plan and in CI."""

from pathlib import Path

import pytest

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
