import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from seabirds.app import create_app
from seabirds.config import Settings
from seabirds.project_catalog import CatalogSource

SOURCE = """// comentário original: 🐧
const dadosCategorias = [
    // LINUX
    {
        categoria: 'Linux',
        projetos: [
            {titulo: "Antigo", imagem: "../imagens/logo.png", descricao: "Descrição", link: "../projetos/linux/antigo.html", extra: {preservar: true}}, // manter
        ]
    },
    {categoria: "Outros", projetos: []}
];
// Código e comentário fora dos dados permanecem intactos.
window.sinalizador = () => "não executar";
"""


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "site"
    for folder in ["js", "paginas", "projetos/linux", "imagens"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    for file in [
        "index.html",
        "paginas/projetos.html",
        "projetos/linux/antigo.html",
        "projetos/linux/novo.html",
    ]:
        (root / file).write_text("<title>Página</title>", encoding="utf-8")
    (root / "imagens/logo.png").write_bytes(b"imagem-de-teste")
    path = root / "js/projetos-conteudo.js"
    path.write_text(SOURCE, encoding="utf-8", newline="")
    settings = Settings(tmp_path / "data")
    with TestClient(create_app(settings)) as client:
        yield client, root, path, settings


def read(client, root, **extra):
    response = client.post("/api/generator/site/catalog/read", json={"root": str(root), **extra})
    assert response.status_code == 200, response.text
    return response.json()


def payload(root, current, **extra):
    return {
        "root": str(root),
        "path": current["path"],
        "page": current["page"],
        "version": current["version"],
        "categoria": "Linux",
        "titulo": "Nova documentação",
        "imagem": "../imagens/logo.png",
        "descricao": "Descrição nova",
        "link": "../projetos/linux/novo.html",
        **extra,
    }


def test_add_preserves_comments_other_categories_and_suffix_with_backup(catalog):
    client, root, path, _ = catalog
    before = path.read_bytes()
    current = read(client, root)
    saved = client.post("/api/generator/site/catalog/save", json=payload(root, current))
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert len(data["categories"][0]["projetos"]) == 2
    assert data["saved_link"] == "../projetos/linux/novo.html"
    assert Path(data["backup"]).read_bytes() == before
    after = path.read_text(encoding="utf-8")
    assert "// manter" in after and "// comentário original: 🐧" in after
    assert '{categoria: "Outros", projetos: []}' in after
    assert after.endswith('window.sinalizador = () => "não executar";\n')
    assert "extra: {preservar: true}" in after


def test_edit_and_move_keep_extra_fields_and_do_not_duplicate(catalog):
    client, root, path, _ = catalog
    current = read(client, root)
    result = client.post(
        "/api/generator/site/catalog/save",
        json=payload(
            root,
            current,
            entry_id="0:0",
            categoria="Outros",
            link="../projetos/linux/antigo.html",
            titulo='Título "com aspas" e 🐧',
        ),
    )
    assert result.status_code == 200, result.text
    categories = result.json()["categories"]
    assert not categories[0]["projetos"] and len(categories[1]["projetos"]) == 1
    assert categories[1]["projetos"][0]["titulo"] == 'Título "com aspas" e 🐧'
    assert "extra: {preservar: true}" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "source",
    [
        "const dadosCategorias=[];",
        "const dadosCategorias=[{categoria:'Linux',projetos:[]}];",
        "const dadosCategorias=[{categoria:'Linux',projetos:[],},];",
    ],
)
def test_empty_and_inline_arrays_and_new_categories_remain_valid(catalog, source):
    client, root, path, _ = catalog
    path.write_text(source, encoding="utf-8")
    current = read(client, root)
    result = client.post(
        "/api/generator/site/catalog/save", json=payload(root, current, categoria="Nova categoria")
    )
    assert result.status_code == 200, result.text
    parsed = CatalogSource(path.read_text(encoding="utf-8"))
    assert parsed.categories[-1]["name"] == "Nova categoria"
    assert len(parsed.categories[-1]["projects"]) == 1


def test_bom_crlf_and_category_case_preserved(catalog):
    client, root, path, _ = catalog
    path.write_bytes(b"\xef\xbb\xbf" + SOURCE.replace("\n", "\r\n").encode())
    current = read(client, root)
    response = client.post(
        "/api/generator/site/catalog/save", json=payload(root, current, categoria="linux")
    )
    assert response.status_code == 200
    content = path.read_bytes()
    assert content.startswith(b"\xef\xbb\xbf") and b"\n" not in content.replace(b"\r\n", b"")
    assert len(response.json()["categories"]) == 2


def test_remove_last_trailing_comma_and_undo_survive_restart(catalog):
    client, root, path, settings = catalog
    current = read(client, root)
    before = path.read_bytes()
    removed = client.post(
        "/api/generator/site/catalog/remove",
        json={
            "root": str(root),
            "path": current["path"],
            "page": current["page"],
            "version": current["version"],
            "entry_id": "0:0",
            "confirm": True,
        },
    )
    assert removed.status_code == 200 and not removed.json()["categories"][0]["projetos"]
    assert (root / "projetos/linux/antigo.html").is_file() and (root / "imagens/logo.png").is_file()
    with TestClient(create_app(settings)) as restarted:
        current = read(restarted, root)
        assert current["can_undo"]
        restored = restarted.post(
            "/api/generator/site/catalog/undo",
            json={
                "root": str(root),
                "path": current["path"],
                "page": current["page"],
                "version": current["version"],
            },
        )
        assert restored.status_code == 200 and path.read_bytes() == before


def test_duplicate_link_and_external_changes_are_rejected_without_writing(catalog):
    client, root, path, _ = catalog
    current = read(client, root)
    before = path.read_bytes()
    result = client.post(
        "/api/generator/site/catalog/save",
        json=payload(root, current, link="/projetos/linux/antigo.html"),
    )
    assert result.status_code == 422 and path.read_bytes() == before
    path.write_bytes(before + b"// alterado externamente\n")
    changed = path.read_bytes()
    result = client.post("/api/generator/site/catalog/save", json=payload(root, current))
    assert result.status_code == 409 and path.read_bytes() == changed


def test_generated_document_prefill_uses_catalog_page_base_and_escapes_text(catalog):
    client, root, path, _ = catalog
    image = root / "imagens/logo com espaço.png"
    image.write_bytes(b"imagem")
    current = read(
        client,
        root,
        title="Título atual",
        output_path=str(root / "projetos/linux/novo.html"),
        image_path=str(image),
    )
    assert current["prefill"] == {
        "titulo": "Título atual",
        "link": "../projetos/linux/novo.html",
        "imagem": "../imagens/logo%20com%20espa%C3%A7o.png",
    }
    title = '<img src=x onerror="alert(1)">'
    result = client.post(
        "/api/generator/site/catalog/save",
        json=payload(
            root, current, titulo=title, descricao="A < B & C", imagem=current["prefill"]["imagem"]
        ),
    )
    assert result.status_code == 200
    assert result.json()["categories"][0]["projetos"][-1]["titulo"] == title
    assert "<img src=x" not in path.read_text(encoding="utf-8")
    assert "&lt;img" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "extra",
    [
        {"link": "javascript:alert(1)"},
        {"link": "../../../fora.html"},
        {"imagem": "https://outside.example/image.png"},
        {"imagem": "../imagens/inexistente.png"},
    ],
)
def test_invalid_references_do_not_change_catalog(catalog, extra):
    client, root, path, _ = catalog
    current = read(client, root)
    before = path.read_bytes()
    response = client.post("/api/generator/site/catalog/save", json=payload(root, current, **extra))
    assert response.status_code == 422 and path.read_bytes() == before


def test_read_never_executes_javascript_and_rejects_computed_fields(catalog, tmp_path):
    client, root, path, _ = catalog
    sentinel = tmp_path / "nao-criar"
    code = 'require("fs").writeFileSync(' + json.dumps(str(sentinel)) + ',"x");\n'
    path.write_text(code + SOURCE, encoding="utf-8")
    assert len(read(client, root)["categories"]) == 2 and not sentinel.exists()
    path.write_text(SOURCE.replace('titulo: "Antigo"', "titulo: dangerous()"), encoding="utf-8")
    response = client.post("/api/generator/site/catalog/read", json={"root": str(root)})
    assert response.status_code == 422 and not sentinel.exists()


def test_catalog_paths_are_scoped_and_file_name_fixed(catalog):
    client, root, path, _ = catalog
    for extra in [
        {"path": "../projetos-conteudo.js"},
        {"path": "js/outro.js"},
        {"page": "../pagina.html"},
    ]:
        response = client.post(
            "/api/generator/site/catalog/read", json={"root": str(root), **extra}
        )
        assert response.status_code == 422


def test_invalid_javascript_does_not_modify_file(catalog):
    client, root, path, _ = catalog
    path.write_text("const dadosCategorias = [broken syntax;", encoding="utf-8")
    before = path.read_bytes()
    response = client.post("/api/generator/site/catalog/read", json={"root": str(root)})
    assert response.status_code == 422 and path.read_bytes() == before


def test_unavailable_document_image_does_not_block_manual_cover_selection(catalog):
    client, root, _, _ = catalog
    current = read(
        client,
        root,
        output_path=str(root / "projetos/linux/novo.html"),
        image_path=str(root / "imagens/removida.png"),
    )
    assert "imagem" not in current["prefill"]
    assert current["prefill"]["link"] == "../projetos/linux/novo.html"


def test_catalog_api_authentication_and_origin(catalog):
    _, root, _, settings = catalog
    with TestClient(create_app(Settings(settings.data_dir, password="qa-password"))) as client:
        assert (
            client.post("/api/generator/site/catalog/read", json={"root": str(root)}).status_code
            == 401
        )
        response = client.post(
            "/api/generator/site/catalog/read",
            json={"root": str(root)},
            auth=("admin", "qa-password"),
            headers={"Origin": "https://other.example"},
        )
        assert response.status_code == 403
