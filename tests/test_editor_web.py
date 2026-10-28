import json
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from seabirds.app import create_app
from seabirds.config import Settings


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site com espaços"
    root.mkdir()
    (root / "index.html").write_text("<title>Site</title>", encoding="utf-8")
    return root


def test_server_connection_replaces_old_loopback_without_changing_saved_preferences(tmp_path, site):
    data = tmp_path / "data"
    data.mkdir()
    catalog = data / "site-workspace.json"
    original = {
        "roots": [],
        "trash": [],
        "editor_url": "http://127.0.0.1",
        "editor_kind": "code-server",
    }
    catalog.write_text(json.dumps(original), encoding="utf-8")
    with TestClient(create_app(Settings(data, editor_url="/editor/"))) as client:
        settings = client.get("/api/generator/site/settings").json()
        assert settings["editor_managed"] and settings["editor_url"] == "/editor/"
        link = client.post("/api/generator/site/editor-link", json={"root": str(site)}).json()
        parsed = urlsplit(link["url"])
        assert parsed.path == "/editor/" and not parsed.netloc
        assert parse_qs(parsed.query)["folder"] == [str(site)]
        assert (
            client.post(
                "/api/generator/site/settings/editor", json={"url": "http://127.0.0.1:8765"}
            ).status_code
            == 422
        )
    assert json.loads(catalog.read_text(encoding="utf-8")) == original
    with TestClient(create_app(Settings(data))) as client:
        assert (
            client.get("/api/generator/site/settings").json()["editor_url"]
            == original["editor_url"]
        )


def test_public_editor_keeps_origin_and_selected_folder_after_restart(tmp_path, site):
    settings = Settings(tmp_path / "data")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/generator/site/settings/editor", json={"url": "https://docs.example.com/editor/"}
        )
        assert response.status_code == 200
    with TestClient(create_app(settings)) as client:
        link = client.post("/api/generator/site/editor-link", json={"root": str(site)}).json()[
            "url"
        ]
        parsed = urlsplit(link)
        assert parsed.scheme == "https" and parsed.netloc == "docs.example.com"
        assert parsed.path == "/editor/" and parse_qs(parsed.query)["folder"] == [str(site)]


@pytest.mark.parametrize(
    "url",
    [
        "//evil.example/editor",
        "///evil.example",
        "/\\evil.example",
        "/editor/\nextra",
        "/editor/?password=secret",
        "http://example.com:wrong/editor",
        "javascript:alert(1)",
    ],
)
def test_editor_rejects_ambiguous_or_credential_urls(tmp_path, url):
    with TestClient(create_app(Settings(tmp_path / "data"))) as client:
        assert (
            client.post("/api/generator/site/settings/editor", json={"url": url}).status_code == 422
        )


def test_editor_connection_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SEABIRDS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SEABIRDS_EDITOR_URL", "/editor/")
    assert Settings.from_env().editor_url == "/editor/"
