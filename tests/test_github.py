import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from seabirds import github
from seabirds.app import create_app
from seabirds.config import Settings
from seabirds.github import GitHubPublisher, github_repository
from seabirds.models import DocumentInput

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="Git não instalado")


def git(root, *args):
    return (
        subprocess.run(
            ["git", "-c", "core.quotepath=false", "-C", str(root), *args],
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .strip()
    )


@pytest.fixture
def repository(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("SEABIRDS_GITHUB_TOKEN", raising=False)
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=main")
    root = tmp_path / "site"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Teste")
    git(root, "config", "user.email", "teste@example.invalid")
    (root / "index.html").write_text("inicial\n", encoding="utf-8")
    (root / "README.md").write_text("original\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "inicial")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "origin", "main")
    original_parser = github.github_repository
    monkeypatch.setattr(
        github,
        "github_repository",
        lambda url: "teste/site" if url == str(remote) else original_parser(url),
    )
    output = root / "projetos" / "guia á.html"
    output.parent.mkdir()
    output.write_text("<h1>Guia revisado</h1>\n", encoding="utf-8")
    document = DocumentInput(title="Guia", generation={"output_path": str(output)})
    service = GitHubPublisher(tmp_path / "data")
    return service, root, remote, document


def test_review_is_read_only_and_recommends_current_document(repository):
    service, root, remote, document = repository
    old = git(root, "rev-parse", "HEAD")
    (root / "outra.html").write_text("outra", encoding="utf-8")
    review = service.inspect("", document)
    assert review["repository"] == "teste/site" and review["branch"] == "main"
    assert review["ahead"] == review["behind"] == 0
    files = {row["path"]: row for row in review["files"]}
    assert files["projetos/guia á.html"]["selected"]
    assert not files["outra.html"]["selected"]
    assert "Guia revisado" in files["projetos/guia á.html"]["diff"]
    assert git(root, "rev-parse", "HEAD") == git(remote, "rev-parse", "main") == old
    assert not git(root, "diff", "--cached", "--name-only")


def test_web_author_unblocks_same_review_without_touching_head_or_stage(repository):
    service, root, remote, document = repository
    git(root, "config", "--unset", "user.name")
    git(root, "config", "--unset", "user.email")
    review = service.inspect(str(root), document)
    head = git(root, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="Configure o nome"):
        service.publish(review["token"], ["projetos/guia á.html"], "docs")
    assert git(root, "rev-parse", "HEAD") == head
    assert not git(root, "diff", "--cached", "--name-only")
    status = service.configure("Autor da web", "web@example.invalid", directory=str(root))
    assert status["repository_author"] == {"name": "Autor da web", "email": "web@example.invalid"}
    assert git(root, "rev-parse", "HEAD") == head
    result = service.publish(review["token"], ["projetos/guia á.html"], "docs")
    assert result["publication"]["status"] == "pushed"
    assert (
        git(remote, "show", "-s", "--format=%an <%ae>", "main")
        == "Autor da web <web@example.invalid>"
    )


def test_web_settings_are_shared_by_clone_and_publication_without_restart(
    repository, monkeypatch, tmp_path
):
    _, _, remote, _ = repository
    data = tmp_path / "web-data"
    token = "synthetic-private-token-for-shared-service"
    original = GitHubPublisher.git
    captured = []

    def local_clone(self, root, *args, **kwargs):
        if args and args[0] == "clone":
            captured.append(self.environment()["SEABIRDS_GITHUB_TOKEN"])
            args = (*args[:2], str(remote), *args[3:])
        return original(self, root, *args, **kwargs)

    monkeypatch.setattr(GitHubPublisher, "git", local_clone)
    destination = tmp_path / "clone-web"
    with TestClient(create_app(Settings(data))) as client:
        saved = client.post(
            "/api/generator/github/settings",
            json={
                "name": "Autor central",
                "email": "central@example.invalid",
                "token_action": "replace",
                "token": token,
            },
        )
        assert saved.status_code == 200 and token not in saved.text
        cloned = client.post(
            "/api/generator/site/clone",
            json={"url": "https://github.com/teste/site.git", "destination": str(destination)},
        )
        assert cloned.status_code == 200 and captured == [token]
        assert git(destination, "config", "--get", "user.name") == "Autor central"
        assert git(destination, "config", "--get", "user.email") == "central@example.invalid"
        (destination / "index.html").write_text("edicao pela web\n", encoding="utf-8")
        review = client.post(
            "/api/generator/github/review-site", json={"directory": str(destination)}
        ).json()
        published = client.post(
            "/api/generator/github/publish",
            json={"token": review["token"], "selected": ["index.html"], "message": "docs: web"},
        )
        assert (
            published.status_code == 200 and published.json()["publication"]["status"] == "pushed"
        )
        assert token not in published.text
        assert git(remote, "show", "main:index.html") == "edicao pela web"


def test_publish_commits_only_selected_paths_preserving_unrelated_stage(repository):
    service, root, remote, document = repository
    (root / "README.md").write_text("alteração preparada pelo usuário\n", encoding="utf-8")
    git(root, "add", "README.md")
    review = service.inspect(str(root), document)
    result = service.publish(review["token"], ["projetos/guia á.html"], "docs: guia")
    item = result["publication"]
    assert not result["push_error"] and item["status"] == "pushed"
    assert git(remote, "show", "main:projetos/guia á.html") == "<h1>Guia revisado</h1>"
    assert git(remote, "show", "main:README.md") == "original"
    assert git(root, "diff", "--cached", "--name-only") == "README.md"
    assert (
        git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", item["sha"])
        == "projetos/guia á.html"
    )
    again = service.publish(review["token"], ["projetos/guia á.html"], "docs: guia")
    assert again["publication"]["sha"] == item["sha"]


def test_catalog_html_and_cover_are_reviewed_and_pushed_together(repository):
    from seabirds.filesystem import ProjectFiles
    from seabirds.site_workspace import SiteWorkspace

    service, root, remote, document = repository
    (root / "js").mkdir()
    (root / "paginas").mkdir()
    (root / "imagens").mkdir()
    (root / "paginas/projetos.html").write_text("<title>Catálogo</title>", encoding="utf-8")
    catalog = root / "js/projetos-conteudo.js"
    catalog.write_text("const dadosCategorias = [];\n", encoding="utf-8")
    git(root, "add", "js/projetos-conteudo.js", "paginas/projetos.html")
    git(root, "commit", "-m", "catalogo inicial")
    git(root, "push", "origin", "main")
    (root / "imagens/capa.png").write_bytes(b"capa-qa")
    (root / "js/outro.js").write_text("window.naoPublicar = true;", encoding="utf-8")
    (root / "README.md").write_text("preservar no stage", encoding="utf-8")
    git(root, "add", "README.md")
    workspace = SiteWorkspace(service.directory, ProjectFiles(service.directory), publisher=service)
    current = workspace.read_catalog(str(root))
    workspace.save_catalog(
        str(root),
        current["path"],
        current["page"],
        current["version"],
        {
            "categoria": "Linux",
            "titulo": "Guia publicado",
            "imagem": str(root / "imagens/capa.png"),
            "descricao": "Descrição da documentação",
            "link": document.generation.output_path,
        },
    )
    review = service.inspect(str(root), document)
    selected = [file["path"] for file in review["files"] if file["selected"]]
    assert set(selected) == {"projetos/guia á.html", "imagens/capa.png", "js/projetos-conteudo.js"}
    assert "Guia publicado" in next(
        file["diff"] for file in review["files"] if file["path"].endswith(".js")
    )
    assert not service.allowed("js/outro.js") and not service.allowed(
        ".github/projetos-conteudo.js"
    )
    published = service.publish(review["token"], selected, "docs: html, capa e catalogo")
    assert published["publication"]["status"] == "pushed"
    assert "Guia publicado" in git(remote, "show", "main:js/projetos-conteudo.js")
    assert git(remote, "show", "main:projetos/guia á.html") == "<h1>Guia revisado</h1>"
    assert git(root, "diff", "--cached", "--name-only") == "README.md"
    assert git(remote, "show", "main:README.md") == "original"


def test_changed_file_or_arbitrary_selection_requires_new_review(repository):
    service, root, remote, document = repository
    review = service.inspect(str(root), document)
    with pytest.raises(ValueError, match="arquivos da revisão"):
        service.publish(review["token"], ["../segredo.html"], "docs")
    Path(document.generation.output_path).write_text("mudou", encoding="utf-8")
    with pytest.raises(ValueError, match="mudou após a revisão"):
        service.publish(review["token"], ["projetos/guia á.html"], "docs")
    assert git(root, "rev-parse", "HEAD") == git(remote, "rev-parse", "main")


def test_changed_local_head_invalidates_review(repository):
    service, root, _, document = repository
    review = service.inspect(str(root), document)
    (root / "index.html").write_text("commit manual", encoding="utf-8")
    git(root, "add", "index.html")
    git(root, "commit", "-m", "manual")
    with pytest.raises(ValueError, match="main local mudou"):
        service.publish(review["token"], ["projetos/guia á.html"], "docs")


def advance_remote(root, remote, tmp_path):
    peer = tmp_path / "peer"
    git(tmp_path, "clone", str(remote), str(peer))
    git(peer, "config", "user.name", "Outro")
    git(peer, "config", "user.email", "outro@example.invalid")
    (peer / "index.html").write_text("nova versão remota", encoding="utf-8")
    git(peer, "add", "index.html")
    git(peer, "commit", "-m", "remoto avançou")
    git(peer, "push", "origin", "main")
    return peer


def test_remote_advance_prevents_commit_and_push(repository, tmp_path):
    service, root, remote, document = repository
    review = service.inspect(str(root), document)
    original_head = git(root, "rev-parse", "HEAD")
    advance_remote(root, remote, tmp_path)
    with pytest.raises(ValueError, match="mesma revisão"):
        service.publish(review["token"], ["projetos/guia á.html"], "docs")
    assert git(root, "rev-parse", "HEAD") == original_head
    assert git(remote, "show", "main:index.html") == "nova versão remota"


def test_fast_forward_sync_preserves_untracked_document(repository, tmp_path):
    service, root, remote, document = repository
    advance_remote(root, remote, tmp_path)
    review = service.inspect(str(root), document)
    assert review["behind"] == 1 and review["ahead"] == 0
    service.sync(review["token"])
    assert git(root, "rev-parse", "HEAD") == git(remote, "rev-parse", "main")
    assert (
        Path(document.generation.output_path).read_text(encoding="utf-8")
        == "<h1>Guia revisado</h1>\n"
    )


def test_sync_preserves_conflicting_local_edit(repository, tmp_path):
    service, root, remote, document = repository
    advance_remote(root, remote, tmp_path)
    (root / "index.html").write_text("edição local", encoding="utf-8")
    review = service.inspect(str(root), document)
    old = git(root, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="Falha no Git"):
        service.sync(review["token"])
    assert git(root, "rev-parse", "HEAD") == old
    assert (root / "index.html").read_text(encoding="utf-8") == "edição local"


def test_push_failure_can_retry_after_restart_without_duplicate_commit(repository, monkeypatch):
    service, root, remote, document = repository
    original_git = service.git

    def failing_git(root, *args, **kwargs):
        if args[0] == "push":
            raise ValueError("Falha de conexão simulada")
        return original_git(root, *args, **kwargs)

    review = service.inspect(str(root), document)
    monkeypatch.setattr(service, "git", failing_git)
    result = service.publish(review["token"], ["projetos/guia á.html"], "docs: guia")
    item = result["publication"]
    assert result["push_error"] and item["status"] == "pending_push"
    assert git(root, "rev-parse", "HEAD") != git(remote, "rev-parse", "main")
    restarted = GitHubPublisher(service.directory)
    retry = restarted.retry(item["id"])
    assert retry["publication"]["sha"] == item["sha"]
    assert not retry["push_error"]
    assert git(root, "rev-parse", "HEAD") == git(remote, "rev-parse", "main") == item["sha"]
    assert len(restarted.publications) == 1


def test_publish_rejects_other_branch_and_expires_plans(repository):
    service, root, _, document = repository
    review = service.inspect(str(root), document)
    service.plans[review["token"]]["expires"] = 0
    with pytest.raises(ValueError, match="expirou"):
        service.publish(review["token"], ["projetos/guia á.html"], "docs")
    git(root, "switch", "-c", "teste")
    with pytest.raises(ValueError, match="branch main"):
        service.inspect(str(root), document)


def test_deletion_is_included_only_when_selected(repository):
    service, root, remote, document = repository
    (root / "index.html").unlink()
    review = service.inspect(str(root), document)
    deleted = next(row for row in review["files"] if row["path"] == "index.html")
    assert deleted["status"] == "deleted" and not deleted["selected"]
    result = service.publish(review["token"], ["index.html"], "docs: remove página")
    assert not result["push_error"]
    assert "index.html" not in git(remote, "ls-tree", "--name-only", "main").splitlines()


def test_remote_validation_and_error_redaction(tmp_path):
    for url in [
        "https://github.com/perdixti/SeaBirdsCloud-site.git",
        "git@github.com:perdixti/SeaBirdsCloud-site.git",
        "ssh://git@github.com/perdixti/SeaBirdsCloud-site.git",
    ]:
        assert github_repository(url) == "perdixti/SeaBirdsCloud-site"
    for url in [
        "https://usuario:senha@github.com/a/b.git",
        "https://outro.example/a/b.git",
        "file:///repositorio",
        "https://github.com/a/b?token=abc",
    ]:
        with pytest.raises(ValueError):
            github_repository(url)
    service = GitHubPublisher(tmp_path)
    service.token = "credencial-de-teste"
    cleaned = service.clean_error("https://user:senha@github.com/a/b credencial-de-teste")
    assert "senha" not in cleaned and "credencial-de-teste" not in cleaned
    assert not service.allowed(".github/workflows/deploy.html")
    assert not service.allowed("../externa.html")
    assert not service.allowed(".env")


def test_publication_catalog_has_no_token(repository):
    service, root, _, document = repository
    service.token = "token-falso-apenas-para-teste"
    review = service.inspect(str(root), document)
    service.publish(review["token"], ["projetos/guia á.html"], "docs")
    catalog = service.catalog.read_text(encoding="utf-8")
    assert service.token not in catalog
    assert len(json.loads(catalog)) == 1


def test_actions_reuses_git_credentials_and_filters_exact_commit(repository, monkeypatch):
    service, root, _, _ = repository
    sha = "a" * 40
    item = {
        "id": "publication",
        "root": str(root),
        "repository": "teste/site",
        "status": "pushed",
        "sha": sha,
        "workflow": "deploy.yml",
        "actions_url": "https://github.com/teste/site/actions",
    }
    service.publications.append(item)
    captured = {}
    original_git = service.git

    def credentials(root, *args, **kwargs):
        if args == ("credential", "fill"):
            return subprocess.CompletedProcess(
                args, 0, b"username=teste\npassword=oauth-somente-teste\n", b""
            )
        return original_git(root, *args, **kwargs)

    monkeypatch.setattr(service, "git", credentials)

    class Connection:
        def __init__(self, host, timeout):
            assert host == "api.github.com" and timeout == 15

        def request(self, method, path, headers):
            captured.update(method=method, path=path, headers=headers)

        def getresponse(self):
            class Response:
                status = 200

                def read(self, size):
                    return json.dumps(
                        {
                            "workflow_runs": [
                                {
                                    "id": 15,
                                    "head_sha": sha,
                                    "name": "Deploy S3",
                                    "status": "completed",
                                    "conclusion": "success",
                                },
                                {
                                    "id": 14,
                                    "head_sha": "b" * 40,
                                    "status": "completed",
                                    "conclusion": "failure",
                                },
                            ]
                        }
                    ).encode()

            return Response()

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(github.http.client, "HTTPSConnection", Connection)
    result = service.runs(item["id"])
    assert captured["headers"]["Authorization"] == "Bearer oauth-somente-teste"
    assert "head_sha=" + sha in captured["path"]
    assert "workflows/deploy.yml/runs" in captured["path"]
    assert captured["closed"]
    assert [run["id"] for run in result["runs"]] == [15]
    assert "oauth-somente-teste" not in json.dumps(result)
    assert not service.catalog.exists()


def test_github_routes_require_authentication_and_same_origin(tmp_path, monkeypatch):
    calls = []

    def inspect(self, directory, document):
        calls.append(directory)
        return {"repository": "perdixti/SeaBirdsCloud-site"}

    monkeypatch.setattr(GitHubPublisher, "inspect", inspect)
    with TestClient(create_app(Settings(tmp_path, password="senha-de-teste"))) as client:
        payload = {"directory": "repo", "document": {}}
        url = "/api/generator/github/review"
        assert client.post(url, json=payload).status_code == 401
        assert (
            client.post(
                url,
                json=payload,
                auth=("admin", "senha-de-teste"),
                headers={"Origin": "https://outro.example"},
            ).status_code
            == 403
        )
        response = client.post(url, json=payload, auth=("admin", "senha-de-teste"))
        assert (
            response.status_code == 200
            and response.json()["repository"] == "perdixti/SeaBirdsCloud-site"
        )
        assert calls == ["repo"]


def test_repository_path_is_preserved_in_drafts(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as client:
        saved = client.post(
            "/api/documents",
            json={"title": "Guia", "generation": {"github_repository_path": "/srv/seabirds/site"}},
        ).json()
        loaded = client.get("/api/documents/" + saved["id"]).json()
        assert loaded["generation"]["github_repository_path"] == "/srv/seabirds/site"


def test_multiple_push_destinations_are_rejected(repository):
    service, root, remote, document = repository
    git(root, "config", "--add", "remote.origin.pushurl", str(remote))
    git(root, "config", "--add", "remote.origin.pushurl", "https://github.com/outro/destino.git")
    with pytest.raises(ValueError, match="único destino"):
        service.inspect(str(root), document)


def test_token_askpass_supplies_credentials_without_network(repository):
    service, root, _, _ = repository
    service.token = "token-local-apenas-teste"
    result = service.git(root, "credential", "fill", data=b"protocol=https\nhost=github.com\n\n")
    fields = dict(line.split("=", 1) for line in result.stdout.decode().splitlines() if "=" in line)
    assert fields["username"] == "x-access-token"
    assert fields["password"] == service.token
    assert service.token not in service.environment()["GIT_ASKPASS"]
    launcher = Path(service.environment()["GIT_ASKPASS"])
    assert service.token not in launcher.read_text(encoding="utf-8")


def test_wrong_saved_generator_directory_is_corrected_to_document_site(repository, tmp_path):
    service, root, _, document = repository
    generator = tmp_path / "gerador"
    generator.mkdir()
    git(generator, "init", "--initial-branch=main")
    (generator / "index.html").write_text("interface do gerador", encoding="utf-8")
    (generator / "templates").mkdir()
    (generator / "templates/template.html").write_text("template interno", encoding="utf-8")
    document.generation.github_repository_path = str(generator)
    review = service.inspect(str(generator), document)
    assert review["root"] == review["site_root"] == str(root)
    assert review["repository"] == "teste/site"
    assert review["directory_corrected"]
    assert [file["path"] for file in review["files"]] == ["projetos/guia á.html"]
    implicit = service.inspect("", document)
    assert implicit["site_root"] == str(root) and implicit["directory_corrected"]


def test_recursive_document_images_are_selected_without_attachment_manifest(repository):
    service, root, remote, document = repository
    images = root / "imagens/projetos/outros"
    images.mkdir(parents=True)
    first, second = images / "captura 1.png", images / "captura-2.png"
    first.write_bytes(b"png-um")
    second.write_bytes(b"png-dois")
    Path(document.generation.output_path).write_text(
        '<h1>Guia</h1><img src="../imagens/projetos/outros/captura%201.png"><img src="/imagens/projetos/outros/captura-2.png">',
        encoding="utf-8",
    )
    review = service.inspect("", document)
    selected = {item["path"] for item in review["files"] if item["selected"]}
    assert selected == {
        "projetos/guia á.html",
        "imagens/projetos/outros/captura 1.png",
        "imagens/projetos/outros/captura-2.png",
    }
    result = service.publish(review["token"], list(selected), "docs: documentação e imagens")
    assert result["push_error"] is None
    assert git(remote, "show", "main:imagens/projetos/outros/captura 1.png") == "png-um"
    assert git(remote, "show", "main:imagens/projetos/outros/captura-2.png") == "png-dois"


def test_site_index_wins_over_nested_index_when_detecting_root(repository):
    service, root, _, document = repository
    nested = root / "projetos/index.html"
    nested.write_text("índice da seção", encoding="utf-8")
    review = service.inspect("", document)
    assert review["site_root"] == str(root)
    assert {item["path"] for item in review["files"]} == {
        "projetos/index.html",
        "projetos/guia á.html",
    }


def test_subsite_scope_excludes_html_outside_index_directory(repository):
    service, root, _, document = repository
    site = root / "public/site"
    site.mkdir(parents=True)
    (site / "index.html").write_text("subsite", encoding="utf-8")
    output = site / "paginas/guias/documento.html"
    output.parent.mkdir(parents=True)
    output.write_text("documentação", encoding="utf-8")
    (root / "fora-do-site.html").write_text("outra página", encoding="utf-8")
    document.generation.output_path = str(output)
    review = service.inspect(str(site), document)
    assert review["root"] == str(root) and review["site_root"] == str(site)
    assert {item["path"] for item in review["files"]} == {
        "public/site/index.html",
        "public/site/paginas/guias/documento.html",
    }


def test_missing_output_cannot_publish_an_arbitrary_repository(repository):
    service, root, _, _ = repository
    with pytest.raises(ValueError, match="HTML de saída"):
        service.inspect(str(root), DocumentInput())


def test_output_inside_generator_repository_is_rejected(repository, tmp_path, monkeypatch):
    service, _, _, _ = repository
    generator = tmp_path / "gerador"
    generator.mkdir()
    git(generator, "init", "--initial-branch=main")
    output = generator / "teste.html"
    output.write_text("pasta errada", encoding="utf-8")
    monkeypatch.setattr(github, "__file__", str(generator / "seabirds/github.py"))
    with pytest.raises(ValueError, match="pasta do gerador"):
        service.inspect(str(generator), DocumentInput(generation={"output_path": str(output)}))
