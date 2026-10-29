import os
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from seabirds import github
from seabirds.app import create_app
from seabirds.config import Settings
from seabirds.filesystem import ProjectFiles
from seabirds.project_catalog import CatalogSource
from seabirds.site_workspace import SiteWorkspace
from seabirds.storage import ConflictError


@pytest.fixture
def deletion(tmp_path):
    root = tmp_path / "site"
    for folder in ["js", "paginas", "projetos", "imagens/a", "imagens/b", "css"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text('<img src="imagens/shared.png"><h1>Site</h1>')
    (root / "paginas/projetos.html").write_text(
        '<script src="../js/projetos-conteudo.js"></script>'
    )
    (root / "projetos/a.html").write_text(
        '<img src="../imagens/a/foto.png"><img src="/imagens/shared.png"><img src="https://outro.invalid/x.png"><img src="../../externa.png">'
    )
    (root / "projetos/b.html").write_text("<h1>Outra documentação</h1>")
    for name in ["a/logo.png", "a/foto.png", "b/logo.png", "shared.png", "sem-referencia.png"]:
        (root / "imagens" / name).write_bytes(b"imagem sintetica:" + name.encode())
    (tmp_path / "externa.png").write_bytes(b"preservar externo")
    catalog = root / "js/projetos-conteudo.js"
    catalog.write_text(
        '// preservar comentario\r\nconst dadosCategorias = [{categoria:"Linux", projetos:[{titulo:"A",imagem:"../imagens/a/logo.png",descricao:"A",link:"../projetos/a.html"},{titulo:"B",imagem:"../imagens/b/logo.png",descricao:"B",link:"../projetos/b.html",extra:true}]}];\r\n// fim\r\n',
        encoding="utf-8-sig",
        newline="",
    )
    data = tmp_path / "data"
    workspace = SiteWorkspace(data, ProjectFiles(data))
    workspace.root(str(root), register=True)
    for name in ["a/foto.png", "shared.png"]:
        workspace.files.image_store.add(root / "imagens" / name, "../imagens/" + name)
    return workspace, root, catalog, data


def trash(workspace, root, relative="projetos/a.html"):
    page = root / relative
    workspace.trash_pages(
        str(root), [SimpleNamespace(path=relative, version=workspace.digest(page))]
    )
    return next(
        item["id"] for item in workspace.trash_entries(root) if item["relative"] == relative
    )


def test_purge_removes_catalog_html_exclusive_images_and_image_records_after_restart(deletion):
    workspace, root, catalog, data = deletion
    identifier = trash(workspace, root)
    workspace = SiteWorkspace(data, ProjectFiles(data))
    before = catalog.read_bytes()
    plan = workspace.preview_delete_page(str(root), identifier)
    assert plan["catalog_entries"] == 0 and plan["catalog_already_removed"] == 1
    assert plan["images"] == ["imagens/a/foto.png", "imagens/a/logo.png"]
    assert plan["preserved_images"] == ["imagens/shared.png"]
    assert catalog.read_bytes() == before and len(workspace.state["trash"]) == 1
    workspace.delete_page(str(root), identifier, plan["token"])
    assert not (root / "projetos/a.html").exists()
    assert not (root / "imagens/a/foto.png").exists() and not (root / "imagens/a/logo.png").exists()
    assert (root / "imagens/shared.png").is_file() and (root / "imagens/b/logo.png").is_file()
    assert (root / "imagens/sem-referencia.png").is_file()
    assert (root.parent / "externa.png").read_bytes() == b"preservar externo"
    text = catalog.read_bytes().decode("utf-8-sig")
    entries = CatalogSource(text).public()[0]["projetos"]
    assert len(entries) == 1 and entries[0]["titulo"] == "B"
    assert "extra:true" in text and "// preservar comentario\r\n" in text
    assert catalog.read_bytes().startswith(b"\xef\xbb\xbf")
    restarted = SiteWorkspace(data, ProjectFiles(data))
    assert restarted.trash_entries(root) == [] and not list((data / "page-trash").iterdir())
    assert len(restarted.files.image_store.entries) == 1
    with pytest.raises(ValueError, match="não encontrada"):
        restarted.restore_page(identifier)
    assert not list(data.glob(".page-delete-*"))


@pytest.mark.parametrize("change", ["catalog", "reference", "image", "new_page"])
def test_stale_review_keeps_every_file(deletion, change):
    workspace, root, catalog, _ = deletion
    identifier = trash(workspace, root)
    plan = workspace.preview_delete_page(str(root), identifier)
    if change == "catalog":
        catalog.write_bytes(catalog.read_bytes() + b"// edicao externa")
    elif change == "reference":
        (root / "index.html").write_text('<img src="imagens/a/foto.png">')
    elif change == "image":
        (root / "imagens/a/foto.png").write_bytes(b"foto alterada")
    else:
        (root / "projetos/a.html").write_text("nova pagina preservar")
    before = catalog.read_bytes()
    with pytest.raises(ConflictError, match="mudou|Existe uma página"):
        workspace.delete_page(str(root), identifier, plan["token"])
    assert catalog.read_bytes() == before and (root / "imagens/a/foto.png").is_file()
    assert workspace.trash_entries(root)


def test_shared_css_srcset_and_other_trashed_page_protect_images(deletion):
    workspace, root, _, _ = deletion
    (root / "css/site.css").write_text('body{background:url("../imagens/a/logo.png")}')
    (root / "projetos/b.html").write_text(
        '<source srcset="../imagens/a/foto.png 1x, ../imagens/b/logo.png 2x">'
    )
    trash(workspace, root, "projetos/b.html")
    identifier = trash(workspace, root)
    plan = workspace.preview_delete_page(str(root), identifier)
    assert not plan["images"]
    workspace.delete_page(str(root), identifier, plan["token"])
    assert (root / "imagens/a/logo.png").exists() and (root / "imagens/a/foto.png").exists()


@pytest.mark.parametrize("encoding", ["utf-16", "cp1252"])
def test_legacy_encoding_and_base_href_preserve_shared_unicode_image(deletion, encoding):
    workspace, root, _, _ = deletion
    image = root / "imagens/a/fótö.png"
    image.write_bytes(b"compartilhada")
    (root / "projetos/a.html").write_text(
        '<img src="../imagens/a/f%C3%B3t%C3%B6.png">', encoding="utf-8"
    )
    (root / "projetos/b.html").write_bytes(
        '<base href="../imagens/a/"><img src="fótö.png">'.encode(encoding)
    )
    identifier = trash(workspace, root)
    plan = workspace.preview_delete_page(str(root), identifier)
    assert "imagens/a/fótö.png" in plan["preserved_images"]
    workspace.delete_page(str(root), identifier, plan["token"])
    assert image.read_bytes() == b"compartilhada"


def test_catalog_duplicates_are_all_removed_and_other_card_cover_kept(deletion):
    workspace, root, catalog, _ = deletion
    catalog.write_text(
        'const dadosCategorias=[{categoria:"x", projetos:[{titulo:"A",imagem:"../imagens/a/logo.png",descricao:"A",link:"../projetos/a.html"},{titulo:"Duplicado",imagem:"../imagens/a/logo.png",descricao:"A",link:"../projetos/./a.html"},{titulo:"B",imagem:"../imagens/a/logo.png",descricao:"B",link:"../projetos/b.html"}]}];'
    )
    identifier = trash(workspace, root)
    plan = workspace.preview_delete_page(str(root), identifier)
    assert plan["catalog_entries"] == 0 and plan["catalog_already_removed"] == 2
    assert "imagens/a/logo.png" in plan["preserved_images"]
    workspace.delete_page(str(root), identifier, plan["token"])
    assert len(CatalogSource(catalog.read_text()).entries) == 1


def test_missing_catalog_and_index_trash_are_supported(deletion):
    workspace, root, catalog, _ = deletion
    catalog.unlink()
    identifier = trash(workspace, root, "index.html")
    plan = workspace.preview_delete_page(str(root), identifier)
    assert plan["catalog_entries"] == 0
    workspace.delete_page(str(root), identifier, plan["token"])
    assert not (root / "index.html").exists() and (root / "projetos/b.html").exists()


def test_invalid_catalog_and_tampered_trash_prevent_deletion(deletion):
    workspace, root, catalog, data = deletion
    identifier = trash(workspace, root)
    before = catalog.read_bytes()
    catalog.write_text("dadosCategorias = executarCodigo();")
    with pytest.raises(ValueError, match="declarar dadosCategorias"):
        workspace.preview_delete_page(str(root), identifier)
    catalog.write_bytes(before)
    (data / "page-trash" / (identifier + ".html")).write_text("alterado")
    with pytest.raises(ValueError, match="alterada"):
        workspace.preview_delete_page(str(root), identifier)
    assert catalog.read_bytes() == before and (root / "imagens/a/foto.png").exists()


def test_wrong_root_and_trash_path_are_rejected(deletion):
    workspace, root, _, data = deletion
    identifier = trash(workspace, root)
    other = root.parent / "other"
    other.mkdir()
    (other / "index.html").touch()
    with pytest.raises(ValueError, match="deste site"):
        workspace.preview_delete_page(str(other), identifier)
    entry = workspace.state["trash"][0]
    entry["trash_file"] = "../../externa.png"
    with pytest.raises(ValueError, match="fora da lixeira"):
        workspace.preview_delete_page(str(root), identifier)
    assert (root.parent / "externa.png").read_bytes() == b"preservar externo"
    assert list((data / "page-trash").iterdir())
    if os.name != "nt":
        entry["trash_file"] = identifier + ".html"
        moved = data / "outra-pasta"
        (data / "page-trash").rename(moved)
        (data / "page-trash").symlink_to(moved, target_is_directory=True)
        with pytest.raises(ValueError, match="fora da lixeira"):
            workspace.preview_delete_page(str(root), identifier)
        assert (moved / entry["trash_file"]).is_file()


@pytest.mark.skipif(os.name == "nt", reason="links simbolicos no Windows exigem privilegio")
def test_image_symlink_never_deletes_target(deletion):
    workspace, root, _, _ = deletion
    image = root / "imagens/a/foto.png"
    image.unlink()
    image.symlink_to(root.parent / "externa.png")
    identifier = trash(workspace, root)
    plan = workspace.preview_delete_page(str(root), identifier)
    assert "imagens/a/foto.png" not in plan["images"]
    workspace.delete_page(str(root), identifier, plan["token"])
    assert image.is_symlink() and (root.parent / "externa.png").read_bytes() == b"preservar externo"


def test_write_failure_rolls_back_catalog_images_and_trash(deletion, monkeypatch):
    workspace, root, catalog, data = deletion
    identifier = trash(workspace, root)
    plan = workspace.preview_delete_page(str(root), identifier)
    original = catalog.read_bytes()
    save = workspace.files.image_store.save
    calls = 0

    def fail_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("falha simulada de gravação")
        return save()

    monkeypatch.setattr(workspace.files.image_store, "save", fail_once)
    with pytest.raises(OSError, match="simulada"):
        workspace.delete_page(str(root), identifier, plan["token"])
    assert catalog.read_bytes() == original
    assert (root / "imagens/a/foto.png").exists() and (root / "imagens/a/logo.png").exists()
    restarted = SiteWorkspace(data, ProjectFiles(data))
    assert restarted.trash_entries(root)[0]["id"] == identifier
    restarted.restore_page(identifier)
    assert (root / "projetos/a.html").exists()


def test_delete_api_requires_review_confirmation_auth_and_same_origin(deletion):
    workspace, root, _, data = deletion
    identifier = trash(workspace, root)
    settings = Settings(data, password="senha-qa")
    url = f"/api/generator/site/pages/trash/{identifier}"
    with TestClient(create_app(settings)) as client:
        assert client.post(url + "/delete-preview", json={"root": str(root)}).status_code == 401
        client.auth = ("admin", "senha-qa")
        plan = client.post(url + "/delete-preview", json={"root": str(root)})
        assert plan.status_code == 200
        payload = {"root": str(root), "token": plan.json()["token"]}
        assert client.post(url + "/delete", json=payload).status_code == 422
        payload["confirm"] = True
        assert (
            client.post(
                url + "/delete", json=payload, headers={"origin": "https://externo.invalid"}
            ).status_code
            == 403
        )
        assert client.post(url + "/delete", json=payload).status_code == 200
        assert not client.post("/api/generator/site/pages", json={"root": str(root)}).json()[
            "trash"
        ]


def test_deletions_and_catalog_are_published_together_only_to_local_bare(deletion, monkeypatch):
    workspace, root, catalog, data = deletion
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def git(path, *args):
        return subprocess.check_output(
            ["git", "-C", str(path), *args],
            env=env,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        ).strip()

    remote = root.parent / "remote.git"
    git(root.parent, "init", "--bare", "--initial-branch=main", str(remote))
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "QA")
    git(root, "config", "user.email", "qa@example.invalid")
    git(root, "config", "core.autocrlf", "true")
    git(root, "add", ".")
    git(root, "commit", "-m", "site inicial")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "origin", "main")
    original = github.github_repository
    monkeypatch.setattr(
        github, "github_repository", lambda url: "qa/site" if url == str(remote) else original(url)
    )
    identifier = trash(workspace, root)
    plan = workspace.preview_delete_page(str(root), identifier)
    workspace.delete_page(str(root), identifier, plan["token"])
    with TestClient(create_app(Settings(data))) as client:
        review = client.post(
            "/api/generator/github/review-site", json={"directory": str(root)}
        ).json()
        expected = {
            "js/projetos-conteudo.js",
            "projetos/a.html",
            "imagens/a/foto.png",
            "imagens/a/logo.png",
        }
        assert {row["path"] for row in review["files"] if row["selected"]} == expected
        result = client.post(
            "/api/generator/github/publish",
            json={
                "token": review["token"],
                "selected": sorted(expected),
                "message": "docs: remove A",
            },
        )
        assert result.status_code == 200 and not result.json()["push_error"], result.text
    remote_names = git(remote, "ls-tree", "-r", "--name-only", "main")
    assert "projetos/a.html" not in remote_names and "imagens/a/foto.png" not in remote_names
    assert "imagens/shared.png" in remote_names
    assert (
        len(
            CatalogSource(
                git(remote, "show", "main:js/projetos-conteudo.js").lstrip("\ufeff")
            ).entries
        )
        == 1
    )
