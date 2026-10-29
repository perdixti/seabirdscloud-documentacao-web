"""Exclusão definitiva revisada, limitada aos arquivos de uma página na lixeira."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from copy import deepcopy
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .filesystem import atomic_write
from .project_catalog import IMAGE_EXTENSIONS, CatalogSource
from .storage import ConflictError

TEXT_EXTENSIONS = {".html", ".htm", ".css", ".js", ".json", ".svg", ".md"}
QUOTED = re.compile(r"""["']([^"'\r\n]+)["']""")
CSS_URL = re.compile(r"""url\(\s*["']?([^)'"\r\n]+?)["']?\s*\)""", re.I)


class ImageReferences(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.values = []
        self.base = ""
        self.feed(text)
        self.values += QUOTED.findall(text) + CSS_URL.findall(text)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "base" and not self.base:
            self.base = attrs.get("href", "")
        for key, value in attributes:
            if not value:
                continue
            if key.endswith("srcset"):
                self.values += [
                    item.strip().split()[0] for item in value.split(",") if item.strip()
                ]
            else:
                self.values.append(value)


class PageDeletion:
    def __init__(self, workspace):
        self.workspace = workspace

    @staticmethod
    def text(raw):
        if raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
            return raw.decode("utf-32")
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16")
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return raw.decode("cp1252")

    @staticmethod
    def safe_path(root, path):
        if not path.resolve().is_relative_to(root):
            return False
        return not any(
            part.startswith(".")
            or (root.joinpath(*path.relative_to(root).parts[: index + 1])).is_symlink()
            for index, part in enumerate(path.relative_to(root).parts)
        )

    def image(self, root, base, reference):
        parsed = urlsplit(unescape(reference).strip().replace("\\/", "/"))
        if parsed.scheme or parsed.netloc or not parsed.path or "\\" in parsed.path:
            return None
        decoded = unquote(parsed.path)
        if "\\" in decoded:
            return None
        path = root / decoded.lstrip("/") if decoded.startswith("/") else base / decoded
        # Normaliza ../ antes de conferir os componentes e links simbólicos.
        path = Path(os.path.abspath(path))
        if path.suffix.lower() not in IMAGE_EXTENSIONS or not self.safe_path(root, path):
            return None
        return path

    def references(self, root, base, text):
        parser = ImageReferences(text)
        if parser.base:
            parsed = urlsplit(parser.base)
            if parsed.scheme or parsed.netloc:
                return set()
            decoded = unquote(parsed.path)
            target = root / decoded.lstrip("/") if decoded.startswith("/") else base / decoded
            base = target if decoded.endswith("/") else target.parent
        result = set()
        for value in parser.values:
            try:
                image = self.image(root, base, value)
            except ValueError:
                continue
            if image:
                result.add(image)
        return result

    def entry(self, root, identifier):
        entry = next(
            (item for item in self.workspace.state["trash"] if item["id"] == identifier), None
        )
        if not entry or entry["root"] != str(root):
            raise ValueError("Página não encontrada na lixeira deste site.")
        destination = self.workspace.page(root, entry["relative"], require_exists=False)
        if destination.exists() or destination.is_symlink():
            raise ConflictError(
                "Existe uma página neste caminho. Ela foi preservada; envie-a à lixeira antes de excluir a cópia antiga."
            )
        source = self.workspace.trash_file(entry)
        return entry, destination, source

    def catalog_plan(self, root, target):
        editor = self.workspace.catalog_editor
        path, page = self.workspace.catalog_options(root)
        catalog = editor.site_path(root, path)
        listing = editor.site_path(root, page)
        if not catalog.exists():
            return None, set()
        if not self.safe_path(root, catalog) or catalog.stat().st_size > 2_000_000:
            raise ValueError("O catálogo está fora do escopo ou excede 2 MB.")
        raw = catalog.read_bytes()
        source = CatalogSource(raw.decode("utf-8-sig"))
        matching, covers = [], set()
        for entry in source.entries.values():
            try:
                linked = editor.reference(
                    root, listing, entry["link"], {".html", ".htm"}, exists=False
                )[1]
            except ValueError:
                continue
            if linked == target.resolve():
                matching.append(entry["id"])
                cover = self.image(root, listing.parent, entry["imagem"])
                if cover:
                    covers.add(cover)
        for identifier in sorted(
            matching, key=lambda value: tuple(map(int, value.split(":"))), reverse=True
        ):
            source = CatalogSource(source.change("", {}, identifier, remove=True))
        changed = (("\ufeff" if raw.startswith(b"\xef\xbb\xbf") else "") + source.text).encode(
            "utf-8"
        )
        return {
            "path": catalog,
            "relative": path,
            "page": page,
            "raw": raw,
            "changed": changed,
            "count": len(matching),
        }, covers

    def plan(self, root, identifier):
        entry, target, source = self.entry(root, identifier)
        raw = source.read_bytes()
        candidates = self.references(root, target.parent, self.text(raw))
        catalog, covers = self.catalog_plan(root, target)
        candidates |= covers
        referenced, versions = set(), {}
        total = 0

        def scan(path, base, content=None):
            nonlocal total
            stat = path.stat()
            total += stat.st_size
            if stat.st_size > 10 * 1024 * 1024 or total > 50 * 1024 * 1024 or len(versions) >= 5000:
                raise ValueError(
                    "O site excede o limite de análise segura (5000 arquivos/50 MB). As imagens foram preservadas."
                )
            original = path.read_bytes()
            versions[path] = hashlib.sha256(original).hexdigest()
            text = self.text(original if content is None else content)
            referenced.update(self.references(root, base, text))
            # Scripts podem montar URLs a partir de fragmentos. Na dúvida, mantém a imagem.
            if path.suffix.lower() in {".js", ".json", ".md"} and not (
                catalog and path == catalog["path"]
            ):
                referenced.update(image for image in candidates if image.name in text)

        def walk_error(exc):
            raise ValueError(
                "Não foi possível conferir as referências do site. Verifique as permissões antes de excluir."
            ) from exc

        for parent, directories, names in os.walk(root, followlinks=False, onerror=walk_error):
            directories[:] = [
                name
                for name in directories
                if not name.startswith(".") and name not in {"node_modules", "__pycache__"}
            ]
            if any((Path(parent) / name).is_symlink() for name in directories):
                raise ValueError(
                    "A análise encontrou uma pasta com link simbólico. As imagens foram preservadas."
                )
            for name in names:
                path = Path(parent) / name
                if name.startswith(".") or path.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                if not self.safe_path(root, path):
                    raise ValueError(
                        "A análise encontrou um arquivo com link simbólico. As imagens foram preservadas."
                    )
                content = catalog["changed"] if catalog and path == catalog["path"] else None
                # URLs do catálogo são relativas à página de projetos, não à pasta js.
                base = (
                    (root / catalog["page"]).parent
                    if catalog and path == catalog["path"]
                    else path.parent
                )
                scan(path, base, content)
        for other in self.workspace.state["trash"]:
            if other["root"] == str(root) and other["id"] != identifier:
                scan(self.workspace.trash_file(other), (root / other["relative"]).parent)
        if catalog and catalog["path"] not in versions:
            raise ValueError("Não foi possível conferir o arquivo do catálogo.")
        images = sorted(path for path in candidates - referenced if path.is_file())
        if len(images) > 1000 or sum(path.stat().st_size for path in images) > 100 * 1024 * 1024:
            raise ValueError("As imagens excedem o limite de exclusão de 1000 arquivos/100 MB.")
        for path in images:
            versions[path] = self.workspace.digest(path)
        versions[source] = entry["digest"]
        public = {
            "id": identifier,
            "root": str(root),
            "path": entry["relative"],
            "catalog_path": catalog["relative"] if catalog else "",
            "catalog_entries": catalog["count"] if catalog else 0,
            "images": [path.relative_to(root).as_posix() for path in images],
            "preserved_images": sorted(
                path.relative_to(root).as_posix() for path in candidates & referenced
            ),
        }
        token = hashlib.sha256(
            json.dumps(
                {**public, "versions": {str(path): digest for path, digest in versions.items()}},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return {
            "public": {**public, "token": token},
            "versions": versions,
            "images": images,
            "catalog": catalog,
            "source": source,
            "entry": entry,
        }

    def delete(self, root, identifier, token):
        plan = self.plan(root, identifier)
        if token != plan["public"]["token"]:
            raise ConflictError(
                "O site ou a lixeira mudou desde a revisão. Revise novamente antes de excluir."
            )
        directory = Path(tempfile.mkdtemp(prefix=".page-delete-", dir=self.workspace.directory))
        keep = False
        copies = {}
        previous = deepcopy(self.workspace.state)
        removed = []
        catalog_written = False
        store = self.workspace.files.image_store
        with store.lock:
            old_images = deepcopy(store.entries)
            try:
                for index, path in enumerate([*plan["images"], plan["source"]]):
                    copy = directory / str(index)
                    shutil.copy2(path, copy)
                    if self.workspace.digest(copy) != plan["versions"][path]:
                        raise ConflictError(
                            "Um arquivo mudou durante a exclusão. Revise novamente."
                        )
                    copies[path] = copy
                for path, digest in plan["versions"].items():
                    if not path.is_file() or self.workspace.digest(path) != digest:
                        raise ConflictError(
                            "Um arquivo mudou durante a exclusão. Revise novamente."
                        )
                self.entry(root, identifier)
                if any(not self.safe_path(root, path) for path in plan["images"]):
                    raise ConflictError("O caminho de uma imagem mudou. Revise novamente.")
                catalog = plan["catalog"]
                changed = catalog and catalog["count"]
                if changed:
                    self.workspace.files.backup(catalog["path"])
                    atomic_write(catalog["path"], catalog["changed"].decode("utf-8"))
                    catalog_written = True
                for path in copies:
                    path.unlink()
                    removed.append(path)
                self.workspace.state["trash"].remove(plan["entry"])
                if changed:
                    self.workspace.state.setdefault("catalogs", {})[str(root)] = {
                        "path": catalog["relative"],
                        "page": catalog["page"],
                        "backup": "",
                        "version": hashlib.sha256(catalog["changed"]).hexdigest(),
                    }
                deleted = set(plan["images"])
                store.entries = {
                    key: value
                    for key, value in store.entries.items()
                    if value.get("trashed") or Path(value["path"]).resolve() not in deleted
                }
                store.save()
                self.workspace.persist()
            except Exception:
                try:
                    catalog = plan["catalog"]
                    if catalog_written and catalog["path"].read_bytes() == catalog["changed"]:
                        atomic_write(catalog["path"], catalog["raw"].decode("utf-8"))
                    for path in removed:
                        copy = copies[path]
                        if not path.exists():
                            with path.open("xb") as output, copy.open("rb") as original:
                                shutil.copyfileobj(original, output)
                            shutil.copystat(copy, path)
                    self.workspace.state.clear()
                    self.workspace.state.update(previous)
                    store.entries = old_images
                    store.save()
                    self.workspace.persist()
                except Exception as exc:
                    keep = True
                    raise ValueError(
                        "Falha ao recuperar a operação. Cópias preservadas em: " + str(directory)
                    ) from exc
                raise
            finally:
                if not keep:
                    shutil.rmtree(directory)
        return plan["public"]
