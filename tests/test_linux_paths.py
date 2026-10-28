import importlib.util
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from seabirds.app import create_app
from seabirds.config import Settings
from seabirds.filesystem import atomic_write
from seabirds.paths import local_path


def helper():
    spec = importlib.util.spec_from_file_location(
        "configure_site", Path(__file__).resolve().parents[1] / "deploy/configure-site.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quoted_paths_and_file_urls_preserve_unicode_and_spaces(tmp_path):
    folder = tmp_path / "Meu site ç"
    folder.mkdir()
    for value in (str(folder), '"' + str(folder) + '"', "'" + str(folder) + "'", folder.as_uri()):
        assert local_path(value) == folder
    for value in ("https://servidor/site", "file://outra-maquina/site", "file:///site?token=x"):
        with pytest.raises(ValueError):
            local_path(value)


@pytest.mark.skipif(os.name != "posix", reason="Caminhos POSIX reais")
def test_windows_paths_are_not_created_as_relative_linux_folders():
    for value in ("C:/site", "C:\\site", "C:site", "\\\\servidor\\site"):
        with pytest.raises(ValueError, match="Linux"):
            local_path(value)


def test_browse_absolute_path_does_not_fall_back_to_parent(tmp_path):
    root = tmp_path / "Meu site"
    root.mkdir()
    with TestClient(create_app(Settings(tmp_path / "data"))) as client:
        listing = client.post("/api/generator/browse", json={"path": str(root)})
        assert listing.status_code == 200 and listing.json()["path"] == str(root)
        assert listing.json()["access"]["user"]
        missing = client.post("/api/generator/browse", json={"path": str(root / "inexistente")})
        assert missing.status_code == 422
        assert "inexistente" in missing.json()["detail"]
        assert not (root / "inexistente").exists()


@pytest.mark.skipif(os.name != "posix", reason="Permissões POSIX reais")
def test_unreadable_child_does_not_break_folder_browser(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("Executar sem root para verificar permissões")
    root = tmp_path / "site"
    root.mkdir()
    blocked = root / "sem-acesso"
    blocked.mkdir()
    (root / "disponivel").mkdir()
    blocked.chmod(0)
    try:
        with TestClient(create_app(Settings(tmp_path / "data"))) as client:
            response = client.post("/api/generator/browse", json={"path": str(root)})
            assert response.status_code == 200
            assert [entry["name"] for entry in response.json()["entries"]] == ["disponivel"]
            assert response.json()["skipped"] == 1
    finally:
        blocked.chmod(0o700)


@pytest.mark.skipif(os.name != "posix", reason="Permissões POSIX reais")
def test_readonly_site_is_reported_without_hiding_existing_pages(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("Executar sem root para verificar permissões")
    root = tmp_path / "site"
    root.mkdir()
    index = root / "index.html"
    index.write_text("<title>Meu site</title>")
    root.chmod(0o500)
    try:
        with TestClient(create_app(Settings(tmp_path / "data"))) as client:
            result = client.post("/api/generator/site/pages", json={"root": str(root)})
            assert result.status_code == 200
            assert result.json()["access"]["writable"] is False
            assert result.json()["pages"][0]["title"] == "Meu site"
            with pytest.raises(PermissionError):
                atomic_write(index, "não pode substituir")
            assert index.read_text() == "<title>Meu site</title>"
    finally:
        root.chmod(0o700)


@pytest.mark.skipif(os.name != "posix", reason="Permissões POSIX reais")
def test_atomic_html_save_preserves_permissions_and_new_private_files(tmp_path):
    path = tmp_path / "pagina.html"
    path.write_text("anterior")
    path.chmod(0o640)
    atomic_write(path, "novo")
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    private = tmp_path / "token"
    atomic_write(private, "credencial de teste")
    assert stat.S_IMODE(private.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="Permissões POSIX reais")
def test_unreadable_html_does_not_abort_site_listing(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("Executar sem root para verificar permissões")
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text("<title>Home</title>")
    blocked = root / "sem-acesso.html"
    blocked.write_text("<title>Privado</title>")
    blocked.chmod(0)
    try:
        with TestClient(create_app(Settings(tmp_path / "data"))) as client:
            result = client.post("/api/generator/site/pages", json={"root": str(root)})
            assert result.status_code == 200
            assert len(result.json()["pages"]) == 1
            assert result.json()["unreadable"] == ["sem-acesso.html"]
    finally:
        blocked.chmod(0o600)


def test_remote_authenticated_client_uses_server_picker_and_preview(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<title>Site</title>")
    (site / "css").mkdir()
    (site / "css/estilo.css").write_text("h1{color:teal}")
    app = create_app(Settings(tmp_path / "data", password="senha apenas do teste"))
    with TestClient(app, base_url="http://lxc.local", client=("192.0.2.10", 40000)) as client:
        client.auth = ("admin", "senha apenas do teste")
        config = client.get("/api/generator/config").json()
        assert not config["native_dialogs"] and not config["local_file_open"]
        assert config["history_dir"] == str(tmp_path / "data/historico")
        assert client.post("/api/generator/browse", json={"path": str(site)}).status_code == 200
        result = client.post(
            "/api/generator/generate",
            json={
                "markdown": "# Página remota",
                "template": '<html><link rel="stylesheet" href="css/estilo.css"><main>{{content}}</main></html>',
                "generation": {"site_dir": str(site), "output_path": str(site / "pagina.html")},
            },
        )
        assert result.status_code == 200
        view = result.json()["url"]
        assert client.get(view).status_code == 200
        assert client.get(view.rsplit("/", 1)[0] + "/css/estilo.css").status_code == 200


def test_systemd_site_dropin_quotes_spaces_percent_and_unicode():
    module = helper()
    unit = module.dropin(Path('/opt/Meu site 50% "ç"'))
    assert '50%% \\"ç\\"' in unit
    assert unit.startswith('[Service]\nReadWritePaths="') and unit.count("\n") == 2


@pytest.mark.skipif(os.name != "posix", reason="Preparador Linux")
def test_site_preparation_changes_only_named_tree_and_writes_scoped_dropin(tmp_path, monkeypatch):
    module = helper()
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text("preservar")
    outside = tmp_path / "fora.html"
    outside.write_text("fora")
    (root / "link.html").symlink_to(outside)
    unit_directory = tmp_path / "units"
    unit_directory.mkdir()
    (unit_directory / "seabirds.service").write_text("[Service]\n")
    changed = []
    monkeypatch.setattr(module.os, "chown", lambda path, *args, **kwargs: changed.append(path))
    module.configure(module.validate_site(str(root)), 1000, 1000, unit_directory)
    assert outside not in changed and root / "link.html" not in changed
    assert (root / "index.html").read_text() == "preservar" and outside.read_text() == "fora"
    dropins = list((unit_directory / "seabirds.service.d").glob("*.conf"))
    assert len(dropins) == 1 and str(root) in dropins[0].read_text()
    assert "ProtectSystem=no" not in dropins[0].read_text()


@pytest.mark.skipif(os.name != "posix", reason="Hard links POSIX")
def test_site_preparation_preflight_rejects_hard_links_before_chown(tmp_path, monkeypatch):
    module = helper()
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text("preservar")
    outside = tmp_path / "fora"
    outside.write_text("não tocar")
    os.link(outside, root / "hardlink")
    units = tmp_path / "units"
    units.mkdir()
    (units / "seabirds.service").touch()
    changes = []
    monkeypatch.setattr(module.os, "chown", lambda *args, **kwargs: changes.append(args))
    with pytest.raises(ValueError, match="hard links"):
        module.configure(root, 1000, 1000, units)
    assert not changes and outside.read_text() == "não tocar"
