import json
import os
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from seabirds import github, local_editor, site_workspace
from seabirds.app import create_app
from seabirds.config import Settings
from seabirds.filesystem import ProjectFiles
from seabirds.local_editor import LocalEditor
from seabirds.site_workspace import SiteWorkspace


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text(
        "<html><head><title>Início</title></head><body>Home</body></html>", encoding="utf-8"
    )
    page = root / "projetos/outros/guia.html"
    page.parent.mkdir(parents=True)
    page.write_text(
        '<!doctype html><html><head><title>Guia local</title><link rel="stylesheet" href="../../css/site.css"></head><body><h1>Guia</h1><script>window.exemplo=1</script></body></html>',
        encoding="utf-8",
    )
    (root / "css").mkdir()
    (root / "css/site.css").write_text("h1{color:teal}", encoding="utf-8")
    data = tmp_path / "data"
    with TestClient(create_app(Settings(data))) as client:
        yield client, root, page, data


def pages(client, root):
    result = client.post("/api/generator/site/pages", json={"root": str(root)})
    assert result.status_code == 200
    return result.json()["pages"]


def test_pages_are_recursive_with_titles_and_versions(site):
    client, root, _, _ = site
    result = pages(client, root)
    assert [row["path"] for row in result] == ["index.html", "projetos/outros/guia.html"]
    assert result[1]["title"] == "Guia local" and len(result[1]["version"]) == 64
    settings = client.get("/api/generator/site/settings").json()
    assert settings["selected_root"] == str(root)


def test_html_editor_preserves_code_and_backs_up_previous_file(site):
    client, root, page, _ = site
    original = page.read_bytes()
    read = client.post(
        "/api/generator/site/pages/read",
        json={"root": str(root), "path": "projetos/outros/guia.html"},
    ).json()
    changed = read["html"].replace("<h1>Guia</h1>", "<h1>Editado localmente</h1>")
    saved = client.post(
        "/api/generator/site/pages/save",
        json={"root": str(root), "path": read["path"], "version": read["version"], "html": changed},
    )
    assert saved.status_code == 200
    assert page.read_text(encoding="utf-8") == changed
    assert "<script>window.exemplo=1</script>" in changed
    assert Path(saved.json()["backup"]).read_bytes() == original


def test_html_editor_detects_external_changes(site):
    client, root, page, _ = site
    read = client.post(
        "/api/generator/site/pages/read",
        json={"root": str(root), "path": "projetos/outros/guia.html"},
    ).json()
    page.write_text("edição pelo VS Code", encoding="utf-8")
    result = client.post(
        "/api/generator/site/pages/save",
        json={
            "root": str(root),
            "path": read["path"],
            "version": read["version"],
            "html": "rascunho antigo",
        },
    )
    assert result.status_code == 409
    assert page.read_text(encoding="utf-8") == "edição pelo VS Code"


def test_page_deletion_requires_confirmation_and_restores_after_restart(site):
    client, root, page, data = site
    original = page.read_bytes()
    selected = [
        {key: row[key] for key in ("path", "version")}
        for row in pages(client, root)
        if row["path"] != "index.html"
    ]
    url = "/api/generator/site/pages/trash"
    assert client.post(url, json={"root": str(root), "pages": selected}).status_code == 422
    deleted = client.post(url, json={"root": str(root), "pages": selected, "confirm": True})
    assert deleted.status_code == 200 and not page.exists()
    identifier = deleted.json()["trash"][0]["id"]
    with TestClient(create_app(Settings(data))) as restarted:
        restored = restarted.post(f"/api/generator/site/pages/trash/{identifier}/restore")
        assert restored.status_code == 200 and page.read_bytes() == original


def test_batch_delete_preflight_preserves_every_page_when_one_changed(site):
    client, root, page, _ = site
    selected = [{key: row[key] for key in ("path", "version")} for row in pages(client, root)]
    page.write_text("alterado fora da aplicação", encoding="utf-8")
    result = client.post(
        "/api/generator/site/pages/trash",
        json={"root": str(root), "pages": selected, "confirm": True},
    )
    assert result.status_code == 409
    assert page.exists() and (root / "index.html").exists()


def test_restore_does_not_overwrite_new_page(site):
    client, root, page, _ = site
    selected = [row for row in pages(client, root) if row["path"] != "index.html"]
    deleted = client.post(
        "/api/generator/site/pages/trash",
        json={"root": str(root), "pages": selected, "confirm": True},
    ).json()
    page.write_text("nova página no mesmo caminho", encoding="utf-8")
    response = client.post(f"/api/generator/site/pages/trash/{deleted['trash'][0]['id']}/restore")
    assert response.status_code == 422
    assert page.read_text(encoding="utf-8") == "nova página no mesmo caminho"


def test_index_can_be_restored_even_while_root_has_no_index(site):
    client, root, _, _ = site
    selected = [row for row in pages(client, root) if row["path"] == "index.html"]
    deleted = client.post(
        "/api/generator/site/pages/trash",
        json={"root": str(root), "pages": selected, "confirm": True},
    ).json()
    assert not (root / "index.html").exists()
    assert len(pages(client, root)) == 1
    assert (
        client.post(
            f"/api/generator/site/pages/trash/{deleted['trash'][0]['id']}/restore"
        ).status_code
        == 200
    )
    assert (root / "index.html").exists()


def test_paths_outside_site_and_hidden_git_files_are_rejected(site, tmp_path):
    client, root, _, _ = site
    outside = tmp_path / "externa.html"
    outside.write_text("preservar", encoding="utf-8")
    for path in [
        "../externa.html",
        str(outside),
        ".git/config.html",
        "projetos\\outros\\guia.html",
    ]:
        assert (
            client.post(
                "/api/generator/site/pages/read", json={"root": str(root), "path": path}
            ).status_code
            == 422
        )
    assert outside.read_text(encoding="utf-8") == "preservar"


def test_page_preview_uses_local_css_and_is_sandboxed(site):
    client, root, _, _ = site
    preview = client.post(
        "/api/generator/site/pages/view",
        json={"root": str(root), "path": "projetos/outros/guia.html"},
    )
    assert preview.status_code == 200
    view = client.get(preview.json()["url"])
    assert view.status_code == 200 and "sandbox" in view.headers["content-security-policy"]
    base = preview.json()["url"].rsplit("/projetos/", 1)[0]
    assert client.get(base + "/css/site.css").status_code == 200


def test_local_editor_links_point_to_same_folder_and_reject_credentials(site):
    client, root, _, _ = site
    assert (
        client.post(
            "/api/generator/site/settings/editor",
            json={"url": "http://127.0.0.1:8765", "kind": "code-server"},
        ).status_code
        == 200
    )
    link = client.post("/api/generator/site/editor-link", json={"root": str(root)}).json()["url"]
    assert parse_qs(urlsplit(link).query)["folder"] == [str(root)]
    client.post(
        "/api/generator/site/settings/editor",
        json={"url": "http://127.0.0.1:8765", "kind": "vscode-serve-web"},
    )
    link = client.post("/api/generator/site/editor-link", json={"root": str(root)}).json()["url"]
    assert parse_qs(urlsplit(link).query)["folder"] == [root.as_uri()]
    for url in [
        "javascript:alert(1)",
        "https://user:password@editor.example",
        "http://127.0.0.1:8765?tkn=segredo",
    ]:
        assert (
            client.post("/api/generator/site/settings/editor", json={"url": url}).status_code == 422
        )


def git(root, *args):
    return (
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        .stdout.decode("utf-8")
        .strip()
    )


@pytest.fixture
def git_site(site, tmp_path, monkeypatch):
    client, root, page, data = site
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=main")
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Teste")
    git(root, "config", "user.email", "teste@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-m", "site inicial")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "origin", "main")
    parser = github.github_repository

    def allowed(url):
        return "teste/site" if url == str(remote) else parser(url)

    monkeypatch.setattr(github, "github_repository", allowed)
    monkeypatch.setattr(site_workspace, "github_repository", allowed)
    return client, root, page, data, remote


def test_clone_creates_independent_local_checkout(git_site, tmp_path):
    client, root, page, _, remote = git_site
    destination = tmp_path / "clones/cópia local"
    old = git(root, "rev-parse", "HEAD")
    result = client.post(
        "/api/generator/site/clone",
        json={
            "url": str(remote),
            "destination": str(destination),
            "author_name": "Editor local",
            "author_email": "editor@example.invalid",
        },
    )
    assert result.status_code == 200
    assert (destination / "projetos/outros/guia.html").read_bytes() == page.read_bytes()
    assert git(destination, "config", "user.name") == "Editor local"
    assert git(root, "rev-parse", "HEAD") == old
    (destination / "index.html").write_text("edição na cópia", encoding="utf-8")
    assert (root / "index.html").read_text(encoding="utf-8") != "edição na cópia"


def test_clone_refuses_existing_destination(git_site):
    client, root, page, _, remote = git_site
    before = page.read_bytes()
    result = client.post(
        "/api/generator/site/clone", json={"url": str(remote), "destination": str(root)}
    )
    assert result.status_code == 422 and page.read_bytes() == before


def test_clone_failure_only_cleans_its_own_temporary_folder(site, tmp_path, monkeypatch):
    _, _, _, data = site
    workspace = SiteWorkspace(data, ProjectFiles(data))
    sentinel = tmp_path / "preservar.txt"
    sentinel.write_text("meus arquivos", encoding="utf-8")

    def fail(root, *args, **kwargs):
        checkout = Path(args[-1])
        checkout.mkdir()
        (checkout / "parcial.html").write_text("parcial")
        raise ValueError("falha de teste")

    monkeypatch.setattr(workspace.publisher, "git", fail)
    with pytest.raises(ValueError, match="falha de teste"):
        workspace.clone("https://github.com/teste/site.git", str(tmp_path / "novo-site"))
    assert not (tmp_path / "novo-site").exists()
    assert not list(tmp_path.glob(".seabirds-clone-*"))
    assert sentinel.read_text() == "meus arquivos"


def test_site_review_publishes_deletion_without_regenerating_html(git_site):
    client, root, page, _, remote = git_site
    selected = [row for row in pages(client, root) if row["path"] != "index.html"]
    assert (
        client.post(
            "/api/generator/site/pages/trash",
            json={"root": str(root), "pages": selected, "confirm": True},
        ).status_code
        == 200
    )
    review = client.post("/api/generator/github/review-site", json={"directory": str(root)})
    assert review.status_code == 200
    result = review.json()
    assert (
        result["site_only"]
        and result["files"][0]["status"] == "deleted"
        and result["files"][0]["selected"]
    )
    published = client.post(
        "/api/generator/github/publish",
        json={
            "token": result["token"],
            "selected": ["projetos/outros/guia.html"],
            "message": "docs: remove página indesejada",
        },
    )
    assert published.status_code == 200 and not published.json()["push_error"]
    assert not page.exists()
    assert "guia.html" not in git(remote, "ls-tree", "-r", "--name-only", "main")


def test_native_editor_requires_license_and_is_local_only(site):
    client, root, _, data = site
    assert (
        client.post("/api/generator/site/editor/local/start", json={"root": str(root)}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/generator/site/editor/local/start",
            json={"root": str(root), "confirm_license": True},
        ).status_code
        == 403
    )
    editor = LocalEditor(data, {}, lambda: None)
    with pytest.raises(ValueError, match="termos"):
        editor.start(root, False)


def test_native_editor_launcher_is_authenticated_and_uses_local_folder(site, monkeypatch):
    _, root, _, data = site
    state = {}
    saved = []
    editor = LocalEditor(data, state, lambda: saved.append(True))
    monkeypatch.setattr(editor, "executable", lambda: data / "code-tunnel.exe")

    def free(*args, **kwargs):
        raise OSError("porta livre")

    monkeypatch.setattr(local_editor.socket, "create_connection", free)
    monkeypatch.setattr(
        local_editor.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, b"1.142.0", b""),
    )
    captures = []

    class Process:
        pid = 123

        def __init__(self, args, **kwargs):
            captures.append(args)

        def poll(self):
            return None

        def terminate(self):
            pass

    monkeypatch.setattr(local_editor.subprocess, "Popen", Process)
    result = editor.start(root, True)
    args = captures[0]
    assert result["started"] and args[args.index("--host") + 1] == "127.0.0.1"
    assert args[args.index("--default-folder") + 1] == str(root)
    assert "--connection-token-file" in args and "--without-connection-token" not in args
    token = (data / "vscode-web.token").read_text()
    assert token not in " ".join(args) and token not in json.dumps(state)
    assert saved and editor.auth_query(urlsplit(state["editor_url"]))["tkn"] == token
