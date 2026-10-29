import json
import os
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from seabirds.app import create_app
from seabirds.backups import encrypt
from seabirds.config import Settings
from seabirds.models import DocumentInput
from seabirds.operations import Operations, progress
from seabirds.project_catalog import CatalogSource


@pytest.fixture
def environment(tmp_path):
    root = tmp_path / "site"
    for name in ["js", "paginas", "projetos/linux", "imagens"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text("<title>Home</title>", encoding="utf-8")
    (root / "paginas/projetos.html").write_text("<title>Projetos</title>", encoding="utf-8")
    (root / "js/projetos-conteudo.js").write_text(
        '// comentário\nconst dadosCategorias=[{categoria:"Linux",projetos:[]}];\n',
        encoding="utf-8",
    )
    (root / "template.html").write_text(
        "<html><head><title>Template</title></head><body><header>Preservar</header>{{content}}<footer>Rodapé</footer></body></html>",
        encoding="utf-8",
    )
    (root / "imagens/capa.png").write_bytes(b"imagem sintetica")
    data = tmp_path / "data"
    app = create_app(Settings(data))
    with TestClient(app) as client:
        hub = app.state.management
        hub.workspace.root(str(root), register=True)
        yield client, hub, root, data


def job(client, kind, payload, fail=False):
    response = client.post(
        "/api/operations", json={"kind": kind, "payload": payload, "request_id": uuid4().hex}
    )
    assert response.status_code == 200, response.text
    identifier = response.json()["id"]
    for _ in range(1000):
        state = client.get("/api/operations/" + identifier).json()
        if state["status"] not in {"queued", "running"}:
            if not fail:
                assert state["status"] == "succeeded", state.get("error")
            return state
        time.sleep(0.01)
    raise AssertionError("Operação de teste não terminou")


def prepared(client, root, **extra):
    payload = {
        "root": str(root),
        "title": "Guia de instalação",
        "category": "Linux",
        "description": "Um guia de teste.",
        "cover": "../imagens/capa.png",
        "template": str(root / "template.html"),
        **extra,
    }
    response = client.post("/api/site/documents/prepare", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_wizard_generation_source_reopens_and_updates_without_duplicate(environment):
    client, hub, root, _ = environment
    document = prepared(client, root)
    assert (
        document["generation"]["output_path"]
        .replace("\\", "/")
        .endswith("projetos/linux/guia-de-instalacao.html")
    )
    document["markdown"] += "Voce pode configurar a aplicacao.\n"
    generated = job(client, "document.generate", document)["result"]
    output = Path(generated["path"])
    assert "<header>Preservar</header>" in output.read_text(encoding="utf-8")
    assert "<footer>Rodapé</footer>" in output.read_text(encoding="utf-8")
    source = output.with_suffix(".documentacao.json")
    assert source.is_file() and generated["catalog_updated"]
    portable = json.loads(source.read_text(encoding="utf-8"))
    assert portable["document"]["generation"]["site_dir"] == "."
    assert (
        portable["document"]["generation"]["output_path"]
        == "projetos/linux/guia-de-instalacao.html"
    )
    assert "github_token" not in source.read_text()
    reopened = client.post(
        "/api/site/documents/source",
        json={"root": str(root), "path": output.relative_to(root).as_posix()},
    )
    assert reopened.status_code == 200, reopened.text
    changed = reopened.json()
    changed["markdown"] += "\nTexto editado."
    job(client, "document.generate", changed)
    entries = CatalogSource((root / "js/projetos-conteudo.js").read_text(encoding="utf-8")).entries
    assert len(entries) == 1 and next(iter(entries.values()))["titulo"] == "Guia de instalação"
    output.write_text("edição externa", encoding="utf-8")
    failed = job(client, "document.generate", changed, fail=True)
    assert failed["status"] == "failed" and "mudou" in failed["error"]
    assert output.read_text(encoding="utf-8") == "edição externa"
    assert any(page["has_source"] for page in hub.workspace.pages(str(root))["pages"])


def test_soft_trash_and_restore_html_source_and_card_together(environment):
    client, hub, root, _ = environment
    doc = prepared(client, root)
    generated = job(client, "document.generate", doc)["result"]
    output = Path(generated["path"])
    source = output.with_suffix(".documentacao.json")
    before = source.read_bytes()
    removed = hub.workspace.trash_pages(
        str(root),
        [
            SimpleNamespace(
                path=output.relative_to(root).as_posix(), version=hub.workspace.digest(output)
            )
        ],
    )
    identifier = removed["trash"][0]["id"]
    assert not output.exists() and not source.exists()
    assert not CatalogSource((root / "js/projetos-conteudo.js").read_text(encoding="utf-8")).entries
    assert (root / "imagens/capa.png").exists()
    hub.workspace.restore_page(identifier)
    assert output.exists() and source.read_bytes() == before
    assert (
        len(CatalogSource((root / "js/projetos-conteudo.js").read_text(encoding="utf-8")).entries)
        == 1
    )
    hub.workspace.trash_pages(
        str(root),
        [
            SimpleNamespace(
                path=output.relative_to(root).as_posix(), version=hub.workspace.digest(output)
            )
        ],
    )
    identifier = hub.workspace.trash_entries(root)[0]["id"]
    plan = hub.workspace.preview_delete_page(str(root), identifier)
    assert plan["sources"] == [source.relative_to(root).as_posix()]
    hub.workspace.delete_page(str(root), identifier, plan["token"])
    assert not hub.workspace.trash_entries(root)
    assert not list((hub.workspace.directory / "page-trash").iterdir())


def test_catalog_error_leaves_html_and_source_in_place(environment):
    client, hub, root, _ = environment
    generated = job(client, "document.generate", prepared(client, root))["result"]
    output = Path(generated["path"])
    (root / "js/projetos-conteudo.js").write_text("const dadosCategorias=executar();")
    with pytest.raises(ValueError):
        hub.workspace.trash_pages(
            str(root),
            [
                SimpleNamespace(
                    path=output.relative_to(root).as_posix(), version=hub.workspace.digest(output)
                )
            ],
        )
    assert output.exists() and output.with_suffix(".documentacao.json").exists()
    assert not hub.workspace.trash_entries(root)


def test_source_of_another_page_does_not_keep_image_with_same_name(environment):
    client, hub, root, _ = environment
    for name in ["a", "b"]:
        (root / ("imagens/" + name)).mkdir()
        (root / ("imagens/" + name + "/img-0.png")).write_bytes(name.encode())
        doc = prepared(
            client, root, title="Guia " + name, cover="../imagens/" + name + "/img-0.png"
        )
        doc["markdown"] += "\n![Imagem](../../imagens/" + name + "/img-0.png)\n"
        doc["generation"]["images"] = [
            hub.files.image_store.add(
                root / ("imagens/" + name + "/img-0.png"), "../../imagens/" + name + "/img-0.png"
            )
        ]
        doc["generation"]["images"] = [
            {
                key: value
                for key, value in item.items()
                if key in {"id", "path", "filename", "web_path"}
            }
            for item in doc["generation"]["images"]
        ]
        job(client, "document.generate", doc)
    page = root / "projetos/linux/guia-a.html"
    hub.workspace.trash_pages(
        str(root),
        [SimpleNamespace(path="projetos/linux/guia-a.html", version=hub.workspace.digest(page))],
    )
    identifier = hub.workspace.trash_entries(root)[0]["id"]
    plan = hub.workspace.preview_delete_page(str(root), identifier)
    assert plan["images"] == ["imagens/a/img-0.png"]
    hub.workspace.delete_page(str(root), identifier, plan["token"])
    assert (root / "imagens/b/img-0.png").exists()


def test_audit_reports_case_missing_catalog_and_orphans_without_changes(environment):
    client, _, root, _ = environment
    (root / "imagens/Logo.png").write_bytes(b"logo")
    (root / "projetos/linux/sem-card.html").write_text(
        '<img src="../../imagens/logo.png"><a href="/nao-existe.html">x</a><a href="https://example.invalid/">externo</a><img src="../../imagens/capa.png">',
        encoding="utf-8",
    )
    before = (root / "index.html").read_bytes()
    result = job(client, "site.audit", {"root": str(root)})["result"]
    assert result["errors"] == 2 and result["warnings"] == 1
    assert any("Maiúsculas" in item["message"] for item in result["issues"])
    assert any("sem cadastro" in item["message"] for item in result["issues"])
    assert (root / "index.html").read_bytes() == before


def test_diagnostics_is_readonly_and_does_not_return_secrets(environment):
    client, hub, root, _ = environment
    hub.publisher.configure("QA", "qa@example.invalid", "replace", "segredo-github-sintetico")
    result = job(client, "diagnostics", {"root": str(root)})["result"]
    assert any(
        item["name"] == "Banco de dados" and item["status"] == "ok" for item in result["checks"]
    )
    assert "segredo-github-sintetico" not in json.dumps(result)
    assert "acesso externo" in result["note"]


def test_backup_full_roundtrip_restores_data_sites_secrets_and_keeps_extra_files(environment):
    client, hub, root, data = environment
    doc = prepared(client, root)
    generated = job(client, "document.generate", doc)["result"]
    saved = hub.store.save(DocumentInput.model_validate(doc))
    hub.publisher.configure("Autor", "qa@example.invalid", "replace", "token-sintetico-backup")
    settings = client.post(
        "/api/maintenance/backups/settings",
        json={
            "password": "senha-de-backup-qa",
            "enabled": False,
            "interval_hours": 24,
            "retention": 2,
        },
    )
    assert settings.status_code == 200 and "senha-de-backup-qa" not in settings.text
    record = job(client, "backup.create", {})["result"]
    package = hub.backups.backup_file(record["id"])
    assert b"token-sintetico-backup" not in package.read_bytes()
    (root / "index.html").write_text("alterado", encoding="utf-8")
    (root / "extra.txt").write_text("preservar")
    (root / "imagens/capa.png").unlink()
    changed = DocumentInput.model_validate(
        {**doc, "version": saved["version"], "markdown": "modificado"}
    )
    hub.store.save(changed, saved["id"])
    failed = job(
        client,
        "backup.inspect",
        {"identifier": record["id"], "password": "senha-incorreta"},
        fail=True,
    )
    assert failed["status"] == "failed" and (root / "index.html").read_text() == "alterado"
    plan = job(
        client,
        "backup.preview",
        {"identifier": record["id"], "password": "senha-de-backup-qa", "targets": {"0": str(root)}},
    )["result"]
    restored = job(
        client,
        "backup.restore",
        {"token": plan["token"], "password": "senha-de-backup-qa", "confirm": True},
    )["result"]
    assert restored["restored"] and restored["recovery_backup"]
    assert (root / "index.html").read_text() == "<title>Home</title>"
    assert (root / "extra.txt").read_text() == "preservar"
    assert (root / "imagens/capa.png").is_file() and Path(generated["source"]).is_file()
    assert hub.store.get(saved["id"])["markdown"] == doc["markdown"]
    assert hub.publisher.token == "token-sintetico-backup"
    assert not hub.backups.config()["enabled"]
    assert hub.backups.backup_file(restored["recovery_backup"]).is_file()
    assert not list((data / "backups").glob("restore-*"))


def test_backup_migration_remaps_saved_document_and_workspace_paths(environment):
    client, hub, root, data = environment
    doc = prepared(client, root)
    saved = hub.store.save(DocumentInput.model_validate(doc))
    hub.backups.configure(False, 24, 2, "senha-de-backup-migracao")
    record = job(client, "backup.create", {})["result"]
    target = root.parent / "migrado"
    plan = job(
        client,
        "backup.preview",
        {
            "identifier": record["id"],
            "password": "senha-de-backup-migracao",
            "targets": {"0": str(target)},
        },
    )["result"]
    job(
        client,
        "backup.restore",
        {"token": plan["token"], "password": "senha-de-backup-migracao", "confirm": True},
    )
    assert (target / "index.html").is_file()
    assert hub.workspace.state["roots"][0]["path"].replace("\\", "/") == str(target).replace(
        "\\", "/"
    )
    assert (
        hub.store.get(saved["id"])["generation"]["output_path"]
        .replace("\\", "/")
        .startswith(str(target).replace("\\", "/") + "/")
    )
    assert (root / "index.html").is_file()


def test_backup_rejects_paths_outside_archive_and_wrong_password(environment, tmp_path):
    client, hub, root, _ = environment
    bad = tmp_path / "bad.zip"
    with ZipFile(bad, "w") as archive:
        archive.writestr("../externo.txt", "ataque")
        archive.writestr("manifest.json", "{}")
    identifier = uuid4().hex
    encrypt(bad, hub.backups.storage / (identifier + ".sbbak"), "senha-de-backup-teste")
    failed = job(
        client,
        "backup.inspect",
        {"identifier": identifier, "password": "senha-de-backup-teste"},
        fail=True,
    )
    assert failed["status"] == "failed"
    assert not (root.parent / "externo.txt").exists()
    assert client.get("/api/maintenance/backups/../download").status_code == 404


def test_backup_upload_streams_more_than_legacy_body_limit_and_is_listed(environment):
    client, hub, root, _ = environment
    (root / "large.bin").write_bytes(os.urandom(13 * 1024 * 1024))
    hub.backups.configure(False, 24, 1, "senha-backup-grande-teste")
    record = hub.backups.create()
    package = hub.backups.backup_file(record["id"])
    assert package.stat().st_size > 12 * 1024 * 1024
    response = client.post(
        "/api/maintenance/backups/upload",
        content=package.read_bytes(),
        headers={"content-type": "application/octet-stream"},
    )
    assert response.status_code == 200, response.text
    identifier = response.json()["identifier"]
    assert any(item["id"] == identifier and item.get("imported") for item in hub.backups.list())
    assert client.get("/api/maintenance/backups/" + identifier + "/download").status_code == 200
    bad = client.post("/api/maintenance/backups/upload", content=b"nao e backup")
    assert bad.status_code == 422


def test_backup_retention_only_removes_old_scheduled_files(environment):
    _, hub, _, _ = environment
    hub.backups.configure(False, 24, 1, "senha-de-backup-retencao")
    manual = hub.backups.create()
    first = hub.backups.create(scheduled=True)
    second = hub.backups.create(scheduled=True)
    assert hub.backups.backup_file(manual["id"]).is_file()
    with pytest.raises(ValueError):
        hub.backups.backup_file(first["id"])
    assert hub.backups.backup_file(second["id"]).is_file()


def test_restore_failure_recovers_previous_files_and_database(environment, monkeypatch):
    client, hub, root, _ = environment
    doc = prepared(client, root)
    saved = hub.store.save(DocumentInput.model_validate(doc))
    hub.backups.configure(False, 24, 2, "senha-para-recuperacao-qa")
    record = hub.backups.create()
    (root / "index.html").write_text("estado atual", encoding="utf-8")
    changed = DocumentInput.model_validate(
        {**doc, "version": saved["version"], "markdown": "estado atual"}
    )
    hub.store.save(changed, saved["id"])
    plan = hub.backups.preview(record["id"], "senha-para-recuperacao-qa", {"0": str(root)})
    original = hub.backups.reload_services
    calls = 0

    def fail_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("falha simulada")
        original()

    monkeypatch.setattr(hub.backups, "reload_services", fail_once)
    with pytest.raises(ValueError, match="simulada"):
        hub.backups.restore(plan["token"], "senha-para-recuperacao-qa")
    assert (root / "index.html").read_text(encoding="utf-8") == "estado atual"
    assert hub.store.get(saved["id"])["markdown"] == "estado atual"
    assert any(item["recovery"] for item in hub.backups.list())


def test_jobs_deduplicate_report_and_survive_restart(tmp_path):
    jobs = Operations(tmp_path)
    calls = []

    def handler(payload):
        calls.append(payload)
        progress("Etapa de teste", 40)
        time.sleep(0.1)
        return {"ok": True}

    jobs.register("test", handler)
    first = jobs.start("test", {"value": 1}, "same-request")
    second = jobs.start("test", {"value": 1}, "same-request")
    assert first["id"] == second["id"]
    with pytest.raises(ValueError):
        jobs.start("test", {"value": 2}, "same-request")
    jobs.close()
    assert len(calls) == 1 and jobs.get(first["id"])["result"] == {"ok": True}
    with sqlite3.connect(jobs.path) as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?", (first["id"],))
    restarted = Operations(tmp_path)
    assert restarted.get(first["id"])["status"] == "interrupted"
    restarted.close()


def test_new_endpoints_require_auth_confirmation_and_hide_invalid_secrets(tmp_path):
    app = create_app(Settings(tmp_path / "data", password="senha-do-aplicativo"))
    with TestClient(app) as client:
        for path in ["/api/operations", "/api/maintenance/backups", "/api/text-review/settings"]:
            assert client.get(path).status_code == 401
        client.auth = ("admin", "senha-do-aplicativo")
        secret = "nunca-retornar-este-segredo"
        response = client.post("/api/text-review/settings", json={"api_key": {"secret": secret}})
        assert response.status_code == 422 and secret not in response.text
        assert (
            client.post(
                "/api/operations",
                json={
                    "kind": "backup.restore",
                    "request_id": uuid4().hex,
                    "payload": {"token": "a" * 32, "password": secret},
                },
            ).status_code
            == 422
        )
        assert secret not in client.get("/api/operations").text
        assert (
            client.post(
                "/api/maintenance/backups/settings",
                headers={"origin": "https://externo.invalid"},
                json={"password": secret},
            ).status_code
            == 403
        )


def test_remote_request_cannot_bypass_auth_with_localhost_host_header(tmp_path):
    app = create_app(Settings(tmp_path / "data"))
    with TestClient(app, client=("203.0.113.10", 1234), base_url="http://localhost") as client:
        assert client.get("/api/operations").status_code == 403
        assert client.get("/api/maintenance/backups").status_code == 403
        assert client.get("/healthz").status_code == 200
