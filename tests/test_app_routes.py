"""The React app is served at /app/* from static/app (built by `cd web && npm run build`)."""
import pytest
from fastapi.testclient import TestClient

import app as app_module
from core import webapp


@pytest.fixture()
def client(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>new app</html>")
    (tmp_path / "assets" / "x.js").write_text("console.log(1)")
    monkeypatch.setattr(webapp, "APP_DIR", tmp_path)
    return TestClient(app_module.app, follow_redirects=False)


def test_root_and_spa_routes_serve_index_no_cache(client):
    for url in ("/app/", "/app/backtest"):
        r = client.get(url)
        assert r.status_code == 200 and "new app" in r.text
        assert r.headers["cache-control"] == "no-cache"


def test_asset_is_immutable(client):
    r = client.get("/app/assets/x.js")
    assert r.status_code == 200 and r.text == "console.log(1)"
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_traversal_is_404(client):
    assert client.get("/app/../app.py").status_code == 404
    assert client.get("/app/%2e%2e/app.py").status_code != 200 or "FastAPI" not in client.get("/app/%2e%2e/app.py").text


def test_bare_app_redirects(client):
    r = client.get("/app")
    assert r.status_code == 307 and r.headers["location"].endswith("/app/")


def test_not_built_is_404(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "APP_DIR", tmp_path)
    r = TestClient(app_module.app).get("/app/")
    assert r.status_code == 404 and "not built yet" in r.text
