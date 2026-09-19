"""The release image's built frontend, served by the API when FRONTEND_DIST names a folder (spec §3, R1)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db import get_session
from app.main import create_app

pytestmark = pytest.mark.anyio

APP_HOST = "127.0.0.1:5190"


@pytest.fixture
def dist(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>PaperLab</title>")
    (tmp_path / "assets" / "a.js").write_text("export {}")
    monkeypatch.setattr(settings, "frontend_dist", str(tmp_path))
    return tmp_path


@pytest.fixture
def release_app(dist, session, arq, pdf_dir):
    """The app as the release image builds it, bound to the test session."""
    application = create_app()
    application.dependency_overrides[get_session] = lambda: session
    application.state.arq = arq
    return application


async def get(app, path: str, host: str = APP_HOST):
    async with AsyncClient(transport=ASGITransport(app=app), base_url=f"http://{APP_HOST}") as http:
        return await http.get(path, headers={"Host": host})


async def test_the_page_is_revalidated_on_every_load_and_its_hashed_files_are_not(release_app):
    page = await get(release_app, "/")
    asset = await get(release_app, "/assets/a.js")

    assert (page.status_code, page.headers["cache-control"]) == (200, "no-cache")
    assert "<title>PaperLab</title>" in page.text
    assert asset.status_code == 200
    assert "no-cache" not in asset.headers.get("cache-control", "")


async def test_the_api_wins_over_the_page(release_app):
    health = await get(release_app, "/api/health")
    missing = await get(release_app, "/api/no-such-route")

    assert (health.status_code, health.json()["orm_roundtrip"]) == (200, True)
    assert (missing.status_code, missing.json()) == (404, {"detail": "Not Found"})


async def test_only_this_computers_names_are_answered(release_app):
    """A web page that rebinds its own host name to 127.0.0.1 still sends its own name as Host (spec §3)."""
    assert (await get(release_app, "/", host="evil.example")).status_code == 400
    assert (await get(release_app, "/api/health", host="evil.example")).status_code == 400
    assert (await get(release_app, "/", host="localhost:5190")).status_code == 200


async def test_without_a_built_frontend_nothing_changes(client, tmp_path, monkeypatch):
    """The dev setup: FRONTEND_DIST empty (the `client` app), or naming a folder that isn't there."""
    assert (await client.get("/")).status_code == 404
    assert (await client.get("/api/health", headers={"Host": "evil.example"})).status_code == 200

    monkeypatch.setattr(settings, "frontend_dist", str(tmp_path / "missing"))
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as http:
        assert (await http.get("/", headers={"Host": "evil.example"})).status_code == 404
