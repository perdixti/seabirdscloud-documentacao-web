import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from seabirds.app import create_app
from seabirds.config import Settings
from seabirds.image_store import ImageStore


@pytest.fixture
def images(tmp_path):
    data = tmp_path / "data"
    generation = {
        "images_dir": str(tmp_path / "imagens"),
        "image_web_path": "imagens",
        "image_index": 0,
    }
    buffer = io.BytesIO()
    Image.new("RGB", (5, 4), "teal").save(buffer, "PNG")
    with TestClient(create_app(Settings(data))) as client:
        response = client.post(
            "/api/generator/image",
            data={"generation": json.dumps(generation)},
            files={"file": ("clipboard.png", buffer.getvalue(), "image/png")},
        )
        assert response.status_code == 201
        yield client, data, generation, response.json(), buffer.getvalue()


def test_images_can_move_to_correct_folder_without_overwriting(images, tmp_path):
    client, _, _, uploaded, _ = images
    record = uploaded["attachment"]
    original = Path(record["path"])
    content = original.read_bytes()
    target = tmp_path / "correta"
    target.mkdir()
    (target / "img-0.png").write_bytes(b"arquivo existente")
    moved = client.post(
        f"/api/generator/images/{record['id']}/move",
        json={"directory": str(target), "web_path": "../../imagens/correta"},
    )
    assert moved.status_code == 200
    result = moved.json()
    assert result["filename"] == "img-1.png"
    assert result["web_path"] == "../../imagens/correta/img-1.png"
    assert not original.exists()
    assert Path(result["path"]).read_bytes() == content
    assert (target / "img-0.png").read_bytes() == b"arquivo existente"


def test_trash_and_restore_survive_server_restart(images):
    client, data, generation, uploaded, _ = images
    record = uploaded["attachment"]
    path = Path(record["path"])
    content = path.read_bytes()
    result = client.post(f"/api/generator/images/{record['id']}/trash")
    assert result.status_code == 200 and result.json()["trashed"]
    assert not path.exists()
    assert client.get(record["thumbnail"]).content == content
    with TestClient(create_app(Settings(data))) as restarted:
        synced = restarted.post(
            "/api/generator/images/sync", json={"generation": {**generation, "images": [record]}}
        )
        assert synced.status_code == 200 and synced.json()[0]["trashed"]
        restored = restarted.post(f"/api/generator/images/{record['id']}/restore")
        assert restored.status_code == 200 and not restored.json()["trashed"]
        assert path.read_bytes() == content


def test_restore_uses_free_name_if_original_path_was_reused(images):
    client, _, _, uploaded, _ = images
    record = uploaded["attachment"]
    path = Path(record["path"])
    content = path.read_bytes()
    assert client.post(f"/api/generator/images/{record['id']}/trash").status_code == 200
    path.write_bytes(b"outro arquivo")
    restored = client.post(f"/api/generator/images/{record['id']}/restore").json()
    assert path.read_bytes() == b"outro arquivo"
    assert restored["filename"] == "img-1.png"
    assert Path(restored["path"]).read_bytes() == content


def test_external_changes_and_unknown_ids_cannot_delete_files(images):
    client, _, _, uploaded, _ = images
    record = uploaded["attachment"]
    path = Path(record["path"])
    path.write_bytes(b"alterado fora do aplicativo")
    assert client.post(f"/api/generator/images/{record['id']}/trash").status_code == 422
    assert path.read_bytes() == b"alterado fora do aplicativo"
    assert client.post("/api/generator/images/unknown/trash").status_code == 422
    assert path.exists()


def test_numbering_also_avoids_duplicate_markdown_urls(images, tmp_path):
    client, _, generation, first, raw = images
    generation = {
        **generation,
        "images_dir": str(tmp_path / "outra"),
        "images": [first["attachment"]],
    }
    second = client.post(
        "/api/generator/image",
        data={"generation": json.dumps(generation)},
        files={"file": ("clipboard.png", raw, "image/png")},
    )
    assert second.status_code == 201
    assert second.json()["filename"] == "img-1.png"
    assert Path(first["path"]).exists()


def test_existing_markdown_images_are_discovered_and_can_be_restored(images):
    client, _, generation, uploaded, _ = images
    result = client.post(
        "/api/generator/images/sync",
        json={"markdown": uploaded["markdown"], "generation": generation},
    )
    assert result.status_code == 200 and result.json()[0]["id"] == uploaded["attachment"]["id"]
    imported = client.post(
        "/api/generator/images/import-folder",
        json={"directory": generation["images_dir"], "web_path": "imagens"},
    ).json()
    assert imported[0]["id"] == uploaded["attachment"]["id"]


def test_import_never_traverses_outside_selected_folder(tmp_path):
    directory = tmp_path / "selecionada"
    directory.mkdir()
    external = tmp_path / "externa.png"
    Image.new("RGB", (2, 2)).save(external)
    store = ImageStore(tmp_path / "data")
    assert store.import_folder(directory, "imagens", names=["../externa.png"]) == []
    assert external.exists()


def test_moved_image_does_not_change_other_image_folders_in_export(images):
    from seabirds.models import DocumentInput
    from seabirds.renderer import render_document

    _, _, generation, uploaded, _ = images
    first = uploaded["attachment"]
    second = {**first, "id": "f" * 32, "filename": "img-1.png", "web_path": "outra-pasta/img-1.png"}
    document = DocumentInput(
        markdown="![original](imagens/img-0.png)\n\n![outra](outra-pasta/img-1.png)",
        generation={**generation, "image_web_path": "proximas-colagens", "images": [first, second]},
    )
    html = render_document(document)
    assert 'src="imagens/img-0.png"' in html
    assert 'src="outra-pasta/img-1.png"' in html


def test_permanent_delete_requires_confirmation_and_trashed_image(images):
    client, _, _, uploaded, _ = images
    record = uploaded["attachment"]
    url = f"/api/generator/images/{record['id']}"
    assert client.request("DELETE", url).status_code == 422
    assert client.request("DELETE", url, json={"confirm": False}).status_code == 422
    assert client.request("DELETE", url, json={"confirm": True}).status_code == 422
    assert Path(record["path"]).is_file()


def test_permanent_delete_removes_only_trash_and_survives_restart(images):
    client, data, generation, uploaded, _ = images
    record = uploaded["attachment"]
    assert client.post(f"/api/generator/images/{record['id']}/trash").status_code == 200
    trash_path = ImageStore(data).image_path(record["id"])
    original = Path(record["path"])
    original.write_bytes(b"novo arquivo no caminho original")
    result = client.request(
        "DELETE", f"/api/generator/images/{record['id']}", json={"confirm": True}
    )
    assert result.status_code == 200 and result.json() == {"id": record["id"], "deleted": True}
    assert not trash_path.exists()
    assert original.read_bytes() == b"novo arquivo no caminho original"
    assert client.get(record["thumbnail"]).status_code == 404
    assert client.post(f"/api/generator/images/{record['id']}/restore").status_code == 422
    with TestClient(create_app(Settings(data))) as restarted:
        result = restarted.post(
            "/api/generator/images/sync", json={"generation": {**generation, "images": [record]}}
        )
        assert result.status_code == 200 and result.json() == []
    assert record["id"] not in ImageStore(data).entries


def test_permanent_delete_rejects_path_outside_trash(images, tmp_path):
    client, data, _, uploaded, _ = images
    record = uploaded["attachment"]
    assert client.post(f"/api/generator/images/{record['id']}/trash").status_code == 200
    store = ImageStore(data)
    trash_path = store.image_path(record["id"])
    outside = tmp_path / (record["id"] + "-externa.png")
    outside.write_bytes(trash_path.read_bytes())
    store.get(record["id"])["trash_path"] = str(outside)
    with pytest.raises(ValueError, match="não pertence"):
        store.delete(record["id"])
    assert outside.exists() and trash_path.exists()


def test_permanent_delete_preserves_changed_trash_file(images):
    client, data, _, uploaded, _ = images
    record = uploaded["attachment"]
    assert client.post(f"/api/generator/images/{record['id']}/trash").status_code == 200
    trash_path = ImageStore(data).image_path(record["id"])
    trash_path.write_bytes(b"outro arquivo")
    assert (
        client.request(
            "DELETE", f"/api/generator/images/{record['id']}", json={"confirm": True}
        ).status_code
        == 422
    )
    assert trash_path.read_bytes() == b"outro arquivo"


def test_permanent_delete_cleans_missing_trash_file(images):
    client, data, _, uploaded, _ = images
    record = uploaded["attachment"]
    assert client.post(f"/api/generator/images/{record['id']}/trash").status_code == 200
    ImageStore(data).image_path(record["id"]).unlink()
    assert (
        client.request(
            "DELETE", f"/api/generator/images/{record['id']}", json={"confirm": True}
        ).status_code
        == 200
    )
    assert record["id"] not in ImageStore(data).entries


def test_permanent_delete_rejects_cross_site_requests_and_unknown_ids(images):
    client, data, _, uploaded, _ = images
    record = uploaded["attachment"]
    assert client.post(f"/api/generator/images/{record['id']}/trash").status_code == 200
    response = client.request(
        "DELETE",
        f"/api/generator/images/{record['id']}",
        json={"confirm": True},
        headers={"Origin": "https://outro-site.example"},
    )
    assert response.status_code == 403
    assert ImageStore(data).image_path(record["id"]).exists()
    assert (
        client.request(
            "DELETE", "/api/generator/images/unknown", json={"confirm": True}
        ).status_code
        == 422
    )
