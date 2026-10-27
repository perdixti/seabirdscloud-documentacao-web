import io
import sqlite3
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from seabirds.app import create_app
from seabirds.config import Settings


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as client:
        yield client


def test_document_round_trip_conflict_and_history(client):
    result = client.post("/api/documents", json={"title": "Projeto", "markdown": "# Um"})
    assert result.status_code == 201
    doc = result.json()
    url = f"/api/documents/{doc['id']}"
    assert client.get(url).json()["markdown"] == "# Um"
    assert (
        client.put(url, json={"title": "Projeto", "markdown": "# Dois", "version": 1}).json()[
            "version"
        ]
        == 2
    )
    assert client.put(url, json={"title": "Antigo", "version": 1}).status_code == 409
    history = client.get(url + "/history").json()
    old = client.get(url + f"/history/{history[-1]['id']}").json()
    assert old["markdown"] == "# Um"
    assert client.get("/api/documents/missing").status_code == 404


def test_validation(client):
    assert client.post("/api/documents", json={"template": "sem marcador"}).status_code == 422
    assert client.post("/api/documents", json={"title": "x" * 201}).status_code == 422
    assert client.post("/api/documents", json={"unknown": 42}).status_code == 422


def test_images_and_portable_export(client):
    image = io.BytesIO()
    Image.new("RGB", (3, 3), "red").save(image, "PNG")
    result = client.post(
        "/api/assets", files={"file": ("../../test.png", image.getvalue(), "image/png")}
    )
    assert result.status_code == 201
    asset = result.json()
    assert client.get("/" + asset["path"]).status_code == 200
    doc = client.post(
        "/api/documents", json={"title": "Imagens", "markdown": asset["markdown"]}
    ).json()
    exported = client.get(f"/api/documents/{doc['id']}/export")
    with ZipFile(io.BytesIO(exported.content)) as archive:
        assert {"index.html", "documento.md", asset["path"]} <= set(archive.namelist())
        assert asset["path"] in archive.read("index.html").decode()
    assert (
        client.post(
            "/api/assets", files={"file": ("x.png", b"not an image", "image/png")}
        ).status_code
        == 422
    )
    assert client.get("/assets/not-an-asset.png").status_code == 404


def test_backup_is_consistent_sqlite(client, tmp_path):
    client.post("/api/documents", json={"title": "Persistente"})
    with ZipFile(io.BytesIO(client.get("/api/backup").content)) as archive:
        database = tmp_path / "restored.sqlite3"
        database.write_bytes(archive.read("seabirds.sqlite3"))
    with sqlite3.connect(database) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT title FROM documents").fetchone()[0] == "Persistente"


def test_auth_covers_static_api_assets_and_backup(tmp_path):
    with TestClient(create_app(Settings(tmp_path, password="segredo"))) as client:
        assert client.get("/healthz").status_code == 200
        for url in ["/", "/static/app.js", "/api/documents", "/api/backup", "/assets/no.png"]:
            assert client.get(url).status_code == 401
        assert client.get("/", auth=("admin", "errado")).status_code == 401
        assert client.get("/api/documents", auth=("admin", "segredo")).status_code == 200
        assert client.get("/", headers={"Authorization": "Basic !!!"}).status_code == 401


def test_cross_origin_mutations_rejected(client):
    assert (
        client.post(
            "/api/documents", json={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post("/api/documents", json={}, headers={"Origin": "http://testserver"}).status_code
        == 201
    )


def test_batch_does_not_accept_server_paths(client):
    response = client.post(
        "/api/tools/batch",
        data={"operation": "replace", "old": "antes", "new": "depois"},
        files=[("files", ("../../documento.md", b"antes", "text/plain"))],
    )
    assert response.status_code == 200
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["001-documento.md"]
        assert archive.read("001-documento.md") == b"depois"


def test_chunked_body_limit(client):
    body = (b"a" * 1024 * 1024 for _ in range(13))
    assert (
        client.post(
            "/api/preview", content=body, headers={"content-type": "application/json"}
        ).status_code
        == 413
    )
