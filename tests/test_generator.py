import io
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from seabirds.app import create_app
from seabirds.config import Settings
from seabirds.filesystem import ProjectFiles
from seabirds.models import DocumentInput, GenerationSettings
from seabirds.storage import Store


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "site com espaços"
    root.mkdir()
    template = root / "template.html"
    template.write_text(
        '<!doctype html><html><head><title>Antigo</title><link href="../../css/style.css" rel="stylesheet"></head>'
        '<body><header id="original">Cabeçalho original</header>{{content}}<footer>Rodapé original</footer>'
        '<script src="../../js/copy.js"></script></body></html>',
        encoding="utf-8",
    )
    (root / "css").mkdir()
    (root / "css/style.css").write_text("body { color: teal; }", encoding="utf-8")
    (root / "js").mkdir()
    (root / "js/copy.js").write_text(
        "function copiarCodigo(b) { b.dataset.copied='yes'; }", encoding="utf-8"
    )
    generation = {
        "template_path": str(template),
        "output_path": str(root / "paginas/guias/tutorial.html"),
        "images_dir": str(root / "imagens/tutorial"),
        "image_web_path": "../../imagens/tutorial",
        "image_index": 7,
        "site_dir": str(root),
        "history_limit": 3,
    }
    with TestClient(create_app(Settings(tmp_path / "data"))) as client:
        yield client, root, generation


def test_exact_file_workflow_template_image_html_and_preview(project):
    client, root, generation = project
    image = io.BytesIO()
    Image.new("RGB", (3, 2), "red").save(image, format="PNG")
    import json

    uploaded = client.post(
        "/api/generator/image",
        data={"generation": json.dumps(generation)},
        files={"file": ("clipboard.png", image.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 201
    pasted = uploaded.json()
    assert pasted["filename"] == "img-7.png"
    assert pasted["next_index"] == 8
    assert Path(pasted["path"]) == root / "imagens/tutorial/img-7.png"
    assert Path(pasted["path"]).is_file()
    assert pasted["markdown"] == "![imagem](../../imagens/tutorial/img-7.png)"
    second = client.post(
        "/api/generator/image",
        data={"generation": json.dumps(generation)},
        files={"file": ("clipboard.png", image.getvalue(), "image/png")},
    ).json()
    assert second["filename"] == "img-8.png"
    document = {
        "title": "Meu tutorial",
        "markdown": "# Tutorial\n\n" + pasted["markdown"] + "\n\n```bash\necho teste\n```",
        "generation": generation,
    }
    response = client.post("/api/generator/generate", json=document)
    assert response.status_code == 200
    assert Path(response.json()["path"]) == root / "paginas/guias/tutorial.html"
    html = Path(response.json()["path"]).read_text(encoding="utf-8")
    assert "<title>Meu tutorial</title>" in html
    assert '<header id="original">Cabeçalho original</header>' in html
    assert "<footer>Rodapé original</footer>" in html
    assert 'src="../../imagens/tutorial/img-7.png"' in html
    assert 'onclick="copiarCodigo(this)"' in html
    assert "{{content}}" not in html
    preview = client.get(response.json()["url"])
    assert preview.status_code == 200
    assert preview.text == html
    assert "sandbox allow-scripts" in preview.headers["content-security-policy"]
    assert "x-frame-options" not in preview.headers
    token = response.json()["url"].split("/")[4]
    assert client.get(f"/api/generator/view/{token}/css/style.css").status_code == 200
    assert client.get(f"/api/generator/view/{token}/imagens/tutorial/img-7.png").status_code == 200
    assert client.get(f"/api/generator/view/{token}/%2e%2e/secret.css").status_code == 404
    download = client.post("/api/generator/download", json=document)
    assert download.headers["content-type"].startswith("text/html")
    assert "documentacao.html" in download.headers["content-disposition"]
    assert download.content[:2] != b"PK"
    assert download.text == html


def test_preview_finds_site_css_without_manual_site_root(project):
    client, root, generation = project
    generation = {**generation, "site_dir": ""}
    response = client.post(
        "/api/generator/preview", json={"markdown": "# Prévia com CSS", "generation": generation}
    )
    assert response.status_code == 200
    preview = response.json()
    assert Path(preview["site_root"]) == root
    assert preview["root_inferred"] is True
    assert preview["missing_stylesheets"] == []
    assert preview["url"].endswith("/paginas/guias/tutorial.html")
    token = preview["url"].split("/")[4]
    css = client.get(f"/api/generator/view/{token}/css/style.css")
    assert css.status_code == 200 and "color: teal" in css.text
    assert not Path(generation["output_path"]).exists()


def test_generated_view_infers_root_and_keeps_exported_paths(project):
    client, root, generation = project
    document = {"markdown": "Conteúdo", "generation": {**generation, "site_dir": ""}}
    generated = client.post("/api/generator/generate", json=document)
    assert generated.status_code == 200
    output = Path(generation["output_path"])
    before = output.read_bytes()
    assert b"../../css/style.css" in before
    assert b"/api/generator/view/" not in before
    viewed = client.post("/api/generator/open-output", json=document).json()
    assert Path(viewed["site_root"]) == root
    assert output.read_bytes() == before


def test_root_relative_css_imports_and_images_use_preview_root_only(project):
    client, root, generation = project
    template = Path(generation["template_path"])
    template.write_text(
        '<html><head><title>Modelo</title><link rel="stylesheet" href="/css/style.css"></head><body>{{content}}</body></html>',
        encoding="utf-8",
    )
    (root / "css/style.css").write_text(
        "@import \"/css/child.css\"; body{background:url('/imagens/back.png')} .x{background:url(//cdn.example/test.png)}",
        encoding="utf-8",
    )
    (root / "css/child.css").write_text("p{color:teal}", encoding="utf-8")
    document = {"markdown": "Teste", "generation": {**generation, "site_dir": ""}}
    generated = client.post("/api/generator/generate", json=document).json()
    token = generated["url"].split("/")[4]
    prefix = f"/api/generator/view/{token}"
    html = client.get(generated["url"]).text
    assert f'href="{prefix}/css/style.css"' in html
    css = client.get(prefix + "/css/style.css").text
    assert f'@import "{prefix}/css/child.css"' in css
    assert f"url('{prefix}/imagens/back.png')" in css
    assert "url(//cdn.example/test.png)" in css
    saved = Path(generation["output_path"]).read_text(encoding="utf-8")
    assert 'href="/css/style.css"' in saved
    assert prefix not in saved


def test_missing_stylesheet_is_reported_in_preview(project):
    client, root, generation = project
    (root / "css/style.css").unlink()
    preview = client.post(
        "/api/generator/preview", json={"generation": {**generation, "site_dir": ""}}
    ).json()
    assert preview["missing_stylesheets"] == ["../../css/style.css"]


def test_overwrite_keeps_recovery_copy_and_protects_template(project):
    client, root, generation = project
    output = Path(generation["output_path"])
    output.parent.mkdir(parents=True)
    output.write_text("HTML anterior", encoding="utf-8")
    response = client.post(
        "/api/generator/generate", json={"markdown": "Novo", "generation": generation}
    )
    assert response.status_code == 200
    assert Path(response.json()["backup"]).read_text(encoding="utf-8") == "HTML anterior"
    template = Path(generation["template_path"])
    before = template.read_bytes()
    bad = {**generation, "output_path": str(template)}
    assert client.post("/api/generator/generate", json={"generation": bad}).status_code == 422
    assert template.read_bytes() == before


def test_visualizar_reads_generated_html_without_regenerating(project):
    client, _, generation = project
    before = client.post(
        "/api/generator/generate", json={"markdown": "Conteúdo gerado", "generation": generation}
    ).json()
    path = Path(before["path"])
    saved = path.read_bytes()
    view = client.post(
        "/api/generator/open-output",
        json={"markdown": "Rascunho diferente", "generation": generation},
    )
    assert view.status_code == 200
    assert path.read_bytes() == saved
    assert "Conteúdo gerado" in client.get(view.json()["url"]).text
    assert "Rascunho diferente" not in client.get(view.json()["url"]).text


def test_template_required_marker_and_missing_paths(project):
    client, root, generation = project
    invalid = root / "invalid.html"
    invalid.write_text("<html>Sem marcador</html>", encoding="utf-8")
    assert client.post("/api/generator/template", json={"path": str(invalid)}).status_code == 422
    assert client.post("/api/generator/generate", json={}).status_code == 422
    assert (
        client.post(
            "/api/generator/generate",
            json={"generation": {**generation, "output_path": str(root / "app.py")}},
        ).status_code
        == 422
    )
    assert client.post("/api/generator/pick/images").json()["supported"] is False


def test_folder_replacement_selection_backups_and_changed_file(project):
    client, root, _ = project
    (root / "one.md").write_text("antigo\nmultilinha", encoding="utf-8")
    (root / "two.md").write_text("antigo\nmultilinha", encoding="utf-8")
    payload = {
        "folder": str(root),
        "operation": "replace",
        "old": "antigo\nmultilinha",
        "new": "novo",
    }
    scan = client.post("/api/generator/scan", json=payload).json()
    assert {file["name"] for file in scan["files"]} == {"one.md", "two.md"}
    applied = client.post(
        "/api/generator/apply", json={"token": scan["token"], "selected": ["one.md"]}
    )
    assert applied.status_code == 200
    assert (root / "one.md").read_text() == "novo"
    assert (root / "two.md").read_text() == "antigo\nmultilinha"
    assert Path(applied.json()["changed"][0]["backup"]).read_text() == "antigo\nmultilinha"
    scan = client.post("/api/generator/scan", json=payload).json()
    (root / "two.md").write_text("modificado em outra aplicação", encoding="utf-8")
    assert (
        client.post(
            "/api/generator/apply", json={"token": scan["token"], "selected": ["two.md"]}
        ).status_code
        == 422
    )
    assert (root / "two.md").read_text(encoding="utf-8") == "modificado em outra aplicação"


def test_folder_formatting_preserves_pre_and_does_not_touch_unselected(project):
    client, root, _ = project
    original = "<div><p>Texto <b>forte</b>!</p><pre> a\n    b &lt; c</pre></div>"
    (root / "format.html").write_text(original, encoding="utf-8")
    scan = client.post(
        "/api/generator/scan", json={"folder": str(root), "operation": "format"}
    ).json()
    result = client.post(
        "/api/generator/apply", json={"token": scan["token"], "selected": ["format.html"]}
    )
    assert result.status_code == 200
    assert "<pre> a\n    b &lt; c</pre>" in (root / "format.html").read_text()
    assert (root / "template.html").read_text().startswith("<!doctype html>")


def test_settings_history_markdown_files_and_retention(tmp_path):
    files = ProjectFiles(tmp_path)
    generation = GenerationSettings(
        output_path=str(tmp_path / "saida/tutorial.html"), history_limit=2
    )
    for version in range(1, 5):
        result = files.snapshot(
            DocumentInput(markdown=f"Versão {version}", version=version, generation=generation)
        )
    entries = list((tmp_path / "historico/tutorial").glob("*.md"))
    assert len(entries) == 2
    assert Path(result["path"]).read_text(encoding="utf-8") == "Versão 4"


def test_migrates_previous_database_without_losing_drafts(tmp_path):
    path = tmp_path / "seabirds.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TABLE documents(id TEXT PRIMARY KEY,title TEXT,markdown TEXT,template TEXT,options TEXT,version INTEGER,updated_at TEXT);
        CREATE TABLE revisions(id INTEGER PRIMARY KEY AUTOINCREMENT,document_id TEXT,title TEXT,markdown TEXT,template TEXT,options TEXT,version INTEGER,created_at TEXT);
        INSERT INTO documents VALUES('existing','Anterior','Meu rascunho','','{}',1,'2026-10-26');""")
    store = Store(tmp_path)
    previous = store.get("existing")
    assert previous["markdown"] == "Meu rascunho"
    assert previous["generation"] == {}
    saved = store.save(
        DocumentInput(
            title="Anterior",
            markdown="Meu rascunho",
            version=1,
            generation=GenerationSettings(output_path=str(tmp_path / "out.html")),
        ),
        "existing",
    )
    assert saved["generation"]["output_path"].endswith("out.html")


def test_server_folder_picker_filters_files_and_creates_folder(project):
    client, root, _ = project
    (root / "private.env").write_text("not listed", encoding="utf-8")
    listing = client.post("/api/generator/browse", json={"path": str(root), "kind": "template"})
    assert listing.status_code == 200
    names = {entry["name"] for entry in listing.json()["entries"]}
    assert "template.html" in names and "css" in names
    assert "private.env" not in names
    created = client.post("/api/generator/mkdir", json={"path": str(root / "nova-pasta")})
    assert created.status_code == 200 and (root / "nova-pasta").is_dir()


def test_local_files_reject_untrusted_host_and_remote_without_password(tmp_path):
    app = create_app(Settings(tmp_path))
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/generator/config").status_code == 200
        assert (
            client.get("/api/generator/config", headers={"Host": "evil.example"}).status_code == 403
        )
    with TestClient(app, base_url="http://server.example", client=("192.168.1.2", 50000)) as client:
        assert client.get("/api/generator/config").status_code == 403


def test_open_local_uses_exact_file_url_without_changing_html(tmp_path, monkeypatch):
    import os

    if os.name != "nt":
        pytest.skip("Abertura local nativa no Windows")
    from seabirds import generator_api

    path = tmp_path / "página #1.html"
    path.write_text("<h1>HTML existente</h1>", encoding="utf-8")
    opened = []
    monkeypatch.setattr(
        generator_api.webbrowser, "open_new_tab", lambda url: opened.append(url) or True
    )
    with TestClient(
        create_app(Settings(tmp_path / "data")),
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    ) as client:
        response = client.post("/api/generator/open-local", json={"path": str(path)})
        assert response.status_code == 200
        assert opened == [path.as_uri()]
        assert path.read_text(encoding="utf-8") == "<h1>HTML existente</h1>"
        assert (
            client.post(
                "/api/generator/open-local", json={"path": str(tmp_path / "ausente.html")}
            ).status_code
            == 422
        )
