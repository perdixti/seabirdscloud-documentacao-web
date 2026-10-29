"""Páginas e clones locais; alterações são publicadas somente pela revisão Git."""

import hashlib
import json
import os
import shutil
import tempfile
import threading
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from .filesystem import atomic_write, local_path
from .github import GitHubPublisher, github_repository
from .local_editor import LocalEditor
from .page_deletion import PageDeletion
from .paths import folder_access
from .project_catalog import ProjectCatalog
from .storage import ConflictError


class PageTitle(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.inside = False
        self.title = ""
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.inside = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.inside = False

    def handle_data(self, text):
        if self.inside:
            self.title += text


class SiteWorkspace:
    def __init__(self, directory, files, publisher=None, managed_editor_url=""):
        self.directory = Path(directory).resolve()
        self.catalog = self.directory / "site-workspace.json"
        self.files = files
        self.catalog_editor = ProjectCatalog(files)
        self.managed_editor_url = self.validate_editor_url(managed_editor_url)
        self.publisher = publisher or GitHubPublisher(directory)
        self.lock = threading.RLock()
        self.state = (
            json.loads(self.catalog.read_text(encoding="utf-8"))
            if self.catalog.exists()
            else {"roots": [], "trash": [], "editor_url": "", "editor_kind": "code-server"}
        )
        self.local_editor = LocalEditor(self.directory, self.state, self.persist)
        self.page_deletion = PageDeletion(self)

    def persist(self):
        atomic_write(self.catalog, json.dumps(self.state, ensure_ascii=False))

    @staticmethod
    def digest(path):
        result = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(256 * 1024), b""):
                result.update(block)
        return result.hexdigest()

    def root(self, value, register=False, cloned=False):
        path = local_path(value)
        if not path.is_dir():
            raise ValueError("Pasta do site não encontrada no servidor: " + str(path))
        if not os.access(path, os.R_OK | os.X_OK):
            raise ValueError("O usuário do aplicativo não pode ler esta pasta: " + str(path))
        if path in {
            Path(path.anchor),
            Path.home().resolve(),
            Path(__file__).resolve().parent.parent,
            self.directory,
        }:
            raise ValueError("Selecione a pasta do site, onde está o index.html.")
        known = any(item["path"] == str(path) for item in self.state["roots"])
        if not known and not cloned and not (path / "index.html").is_file():
            raise ValueError("Selecione a raiz do site que contém o index.html.")
        if register:
            if not known:
                self.state["roots"].append({"path": str(path), "name": path.name})
            self.state["selected_root"] = str(path)
            self.persist()
        return path

    def page(self, root, relative, require_exists=True):
        name = PurePosixPath(relative)
        if (
            name.is_absolute()
            or any(part in {"..", ".git"} or part.startswith(".") for part in name.parts)
            or "\\" in relative
            or name.suffix.lower() not in {".html", ".htm"}
        ):
            raise ValueError("Selecione uma página HTML dentro do site.")
        path = root / relative
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError("A página aponta para fora da raiz do site.")
        if require_exists and (not path.is_file() or path.stat().st_size > 10 * 1024 * 1024):
            raise ValueError("Página não encontrada ou maior que 10 MB.")
        return path

    def settings(self):
        with self.lock:
            settings = {
                key: self.state.get(key, "")
                for key in ("roots", "selected_root", "editor_url", "editor_kind")
            }
            return {
                **settings,
                **(
                    {"editor_url": self.managed_editor_url, "editor_kind": "code-server"}
                    if self.managed_editor_url
                    else {}
                ),
                "editor_managed": bool(self.managed_editor_url),
                "local_editor_available": self.local_editor.executable() is not None,
            }

    def start_local_editor(self, value, confirm_license, port=8765):
        with self.lock:
            root = self.root(value, register=True)
            return self.local_editor.start(root, confirm_license, port)

    @staticmethod
    def validate_editor_url(url):
        url = url.strip()
        parsed = urlsplit(url)
        relative = url.startswith("/") and not url.startswith("//")
        if url and (
            (not relative and (parsed.scheme not in {"http", "https"} or not parsed.hostname))
            or (relative and (parsed.scheme or parsed.netloc))
            or "\\" in url
            or any(ord(char) < 33 or ord(char) == 127 for char in url)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Informe a URL HTTP/HTTPS do editor ou um caminho como /editor/, sem senha, token ou parâmetros."
            )
        if parsed.netloc:
            _ = parsed.port  # Rejeita portas inválidas antes de salvar a conexão.
        return url

    def editor_settings(self, url, kind):
        if self.managed_editor_url:
            raise ValueError(
                "A conexão do editor está configurada no servidor por SEABIRDS_EDITOR_URL."
            )
        url = self.validate_editor_url(url)
        if kind not in {"code-server", "vscode-serve-web"}:
            raise ValueError("Tipo de editor inválido.")
        with self.lock:
            self.state.update(editor_url=url, editor_kind=kind)
            self.persist()
            return self.settings()

    def editor_link(self, value, relative=""):
        with self.lock:
            root = self.root(value)
            if relative:
                self.page(root, relative)
            settings = self.settings()
            url = settings["editor_url"]
            if not url:
                raise ValueError("Configure a URL do editor do site na aba Site e repositórios.")
            parsed = urlsplit(url)
            folder = root.as_uri() if settings["editor_kind"] == "vscode-serve-web" else str(root)
            query = dict(parse_qsl(parsed.query))
            query["folder"] = folder
            if settings["editor_kind"] == "vscode-serve-web":
                query.update(self.local_editor.auth_query(parsed))
            return {
                "url": urlunsplit(
                    (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), "")
                ),
                "root": str(root),
            }

    def info(self, root):
        repository_error = ""
        try:
            git_root = self.publisher.root(str(root))
            repository = self.publisher.repository(git_root)[0]
            branch = self.publisher.text(git_root, "branch", "--show-current")
        except ValueError as exc:
            repository, branch = None, None
            if (root / ".git").exists():
                repository_error = str(exc)
        return {
            "root": str(root),
            "repository": repository,
            "branch": branch,
            "has_index": (root / "index.html").is_file(),
            "access": folder_access(root),
            "repository_error": repository_error,
        }

    def pages(self, value):
        with self.lock:
            root = self.root(value, register=True)
            pages = []
            skipped = []
            for parent, directories, names in os.walk(
                root,
                followlinks=False,
                onerror=lambda exc: skipped.append(str(Path(exc.filename).relative_to(root))),
            ):
                directories[:] = [
                    name
                    for name in directories
                    if not name.startswith(".")
                    and name not in {"node_modules", "__pycache__"}
                    and not (Path(parent) / name).is_symlink()
                ]
                for name in names:
                    path = Path(parent) / name
                    if (
                        path.suffix.lower() not in {".html", ".htm"}
                        or name.startswith(".")
                        or path.is_symlink()
                        or not path.is_file()
                        or not path.resolve().is_relative_to(root)
                    ):
                        continue
                    if len(pages) >= 2000:
                        raise ValueError("O site tem mais de 2000 páginas. Escolha uma raiz menor.")
                    try:
                        with path.open("rb") as source:
                            title = PageTitle(
                                source.read(128 * 1024).decode("utf-8", errors="replace")
                            ).title.strip()
                        stat = path.stat()
                        version = self.digest(path)
                    except OSError:
                        skipped.append(path.relative_to(root).as_posix())
                        continue
                    pages.append(
                        {
                            "path": path.relative_to(root).as_posix(),
                            "title": title or path.stem,
                            "size": stat.st_size,
                            "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                            "version": version,
                        }
                    )
            pages.sort(key=lambda item: (item["path"] != "index.html", item["path"].casefold()))
            return {
                **self.info(root),
                "pages": pages,
                "trash": self.trash_entries(root),
                "unreadable": skipped,
            }

    def read_page(self, value, relative):
        with self.lock:
            root = self.root(value)
            path = self.page(root, relative)
            raw = path.read_bytes()
            content = raw.decode("utf-8-sig")
            if len(content) > 2_000_000:
                raise ValueError(
                    "Abra este HTML no VS Code Web: ele excede o limite do editor integrado."
                )
            return {"path": relative, "html": content, "version": hashlib.sha256(raw).hexdigest()}

    def catalog_options(self, root, path="", page=""):
        saved = self.state.get("catalogs", {}).get(str(root), {})
        return path or saved.get("path", "js/projetos-conteudo.js"), page or saved.get(
            "page", "paginas/projetos.html"
        )

    def read_catalog(self, value, path="", page="", draft=None):
        with self.lock:
            root = self.root(value, register=True)
            path, page = self.catalog_options(root, path, page)
            result = self.catalog_editor.read(root, path, page, draft)
            previous = self.state.get("catalogs", {}).get(str(root), {})
            previous = (
                previous if previous.get("path") == path and previous.get("page") == page else {}
            )
            self.state.setdefault("catalogs", {})[str(root)] = {
                **previous,
                "path": path,
                "page": page,
            }
            self.persist()
            return {
                **result,
                "can_undo": bool(previous.get("backup"))
                and previous.get("version") == result["version"],
            }

    def save_catalog(self, value, path, page, version, data, entry_id="", remove=False):
        with self.lock:
            root = self.root(value)
            result = self.catalog_editor.write(root, path, page, version, data, entry_id, remove)
            self.state.setdefault("catalogs", {})[str(root)] = {
                "path": path,
                "page": page,
                "backup": result["backup"],
                "version": result["version"],
            }
            self.persist()
            return {**result, "can_undo": True}

    def undo_catalog(self, value, path, page, version):
        with self.lock:
            root = self.root(value)
            previous = self.state.get("catalogs", {}).get(str(root), {})
            if (
                previous.get("path") != path
                or previous.get("page") != page
                or previous.get("version") != version
                or not previous.get("backup")
            ):
                raise ValueError(
                    "Recarregue o catálogo para consultar a última alteração que pode ser desfeita."
                )
            result = self.catalog_editor.undo(root, path, page, version, previous["backup"])
            self.state["catalogs"][str(root)] = {
                "path": path,
                "page": page,
                "backup": "",
                "version": result["version"],
            }
            self.persist()
            return {**result, "can_undo": False}

    def save_page(self, value, relative, version, html):
        with self.lock:
            root = self.root(value)
            path = self.page(root, relative)
            if self.digest(path) != version:
                raise ConflictError(
                    "O HTML foi alterado fora deste editor. Copie sua edição e recarregue o arquivo antes de salvar."
                )
            if len(html.encode("utf-8")) > 10 * 1024 * 1024:
                raise ValueError("O HTML deve ter até 10 MB.")
            backup = self.files.backup(path)
            atomic_write(path, html)
            return {"path": relative, "version": self.digest(path), "backup": backup}

    def trash_entries(self, root):
        return [
            {key: entry[key] for key in ("id", "relative", "trashed_at")}
            for entry in self.state["trash"]
            if entry["root"] == str(root)
        ]

    def trash_pages(self, value, selections):
        with self.lock:
            root = self.root(value, register=True)
            checked = []
            seen = set()
            for selection in selections:
                path = self.page(root, selection.path)
                if self.digest(path) != selection.version:
                    raise ConflictError(
                        "Uma página mudou após a listagem. Atualize a lista antes de excluir: "
                        + selection.path
                    )
                if path not in seen:
                    checked.append((path, selection))
                    seen.add(path)
            changed = []
            for path, selection in checked:
                identifier = uuid4().hex
                destination = self.directory / "page-trash" / (identifier + path.suffix)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with path.open("rb") as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target)
                    target.flush()
                    os.fsync(target.fileno())
                if (
                    self.digest(destination) != selection.version
                    or self.digest(path) != selection.version
                ):
                    destination.unlink()
                    raise ConflictError(
                        "A página mudou durante a operação. Atualize a lista antes de excluir."
                    )
                entry = {
                    "id": identifier,
                    "root": str(root),
                    "relative": selection.path,
                    "digest": selection.version,
                    "trash_file": destination.name,
                    "trashed_at": datetime.now(UTC).isoformat(),
                }
                # Registra a cópia recuperável antes de retirar a página do site.
                self.state["trash"].append(entry)
                self.persist()
                path.unlink()
                changed.append(selection.path)
            return {"changed": changed, "trash": self.trash_entries(root)}

    def restore_page(self, identifier):
        with self.lock:
            entry = next((item for item in self.state["trash"] if item["id"] == identifier), None)
            if not entry:
                raise ValueError("Página não encontrada na lixeira.")
            root = self.root(entry["root"])
            destination = self.page(root, entry["relative"], require_exists=False)
            source = self.trash_file(entry)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with source.open("rb") as old, destination.open("xb") as new:
                    shutil.copyfileobj(old, new)
                    new.flush()
                    os.fsync(new.fileno())
            except FileExistsError as exc:
                raise ValueError(
                    "Já existe uma página neste caminho. Renomeie-a antes de restaurar."
                ) from exc
            source.unlink()
            self.state["trash"].remove(entry)
            self.persist()
            return {"root": str(root), "path": entry["relative"]}

    def trash_file(self, entry):
        trash = self.directory / "page-trash"
        source = trash / entry["trash_file"]
        if (
            trash.is_symlink()
            or source.resolve().parent != trash.resolve()
            or source.name != entry["id"] + Path(entry["relative"]).suffix
            or source.is_symlink()
        ):
            raise ValueError("Arquivo fora da lixeira de páginas.")
        if not source.is_file() or self.digest(source) != entry["digest"]:
            raise ValueError("A cópia da página na lixeira foi alterada ou não existe.")
        return source

    def preview_delete_page(self, value, identifier):
        with self.lock:
            root = self.root(value)
            return self.page_deletion.plan(root, identifier)["public"]

    def delete_page(self, value, identifier, token):
        with self.lock:
            root = self.root(value)
            return self.page_deletion.delete(root, identifier, token)

    def clone(self, url, destination, author_name="", author_email=""):
        defaults = self.publisher.preferences.author
        author_name = author_name.strip() or defaults["name"]
        author_email = author_email.strip() or defaults["email"]
        self.publisher.preferences.identity(author_name, author_email, require_pair=False)
        repository = github_repository(url.strip())
        target = local_path(destination)
        if target.exists():
            raise ValueError("A pasta de destino já existe. Escolha uma nova pasta para o clone.")
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".seabirds-clone-", dir=target.parent)).resolve()
        try:
            checkout = staging / "checkout"
            self.publisher.git(
                target.parent, "clone", "--", url.strip(), str(checkout), timeout=300
            )
            if author_name.strip():
                self.publisher.git(
                    checkout, "config", "--local", "--", "user.name", author_name.strip()
                )
            if author_email.strip():
                self.publisher.git(
                    checkout, "config", "--local", "--", "user.email", author_email.strip()
                )
            if target.exists():
                raise ValueError(
                    "A pasta de destino foi criada durante o clone. Os arquivos existentes foram preservados."
                )
            checkout.rename(target)
            with self.lock:
                self.root(str(target), register=True, cloned=True)
            return {**self.info(target), "repository": repository}
        finally:
            # O diretório é exclusivo desta operação, criado ao lado do destino informado.
            if (
                staging.parent == target.parent.resolve()
                and staging.name.startswith(".seabirds-clone-")
                and staging.is_dir()
            ):
                shutil.rmtree(staging)
