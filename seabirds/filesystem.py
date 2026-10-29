"""Operações explícitas em arquivos: HTML, imagens numeradas e pastas de texto."""

import hashlib
import io
import os
import re
import stat
import tempfile
import threading
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from bs4 import BeautifulSoup
from PIL import Image, ImageOps

from .image_store import ImageStore
from .models import DocumentInput, GenerationSettings
from .paths import local_path as local_path
from .renderer import render_document
from .tools import TEXT_EXTENSIONS, format_html

WEB_EXTENSIONS = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
}


class TemplateAssets(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.references = []
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "link" and attrs.get("href"):
            stylesheet = "stylesheet" in attrs.get("rel", "").split() or attrs.get("as") == "style"
            self.references.append((attrs["href"], stylesheet))
        elif tag in {"script", "img", "source", "video", "audio"} and attrs.get("src"):
            self.references.append((attrs["src"], False))


def preview_asset_path(reference, output, root=None):
    parsed = urlsplit(reference.replace("\\", "/"))
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    path = unquote(parsed.path)
    if path.startswith("/"):
        if root is not None:
            return (root / path.lstrip("/")).resolve()
        for candidate in [output.parent, *output.parent.parents]:
            target = (candidate / path.lstrip("/")).resolve()
            if target.is_file():
                return target
        return (output.parent / path.lstrip("/")).resolve()
    return (output.parent / path).resolve()


def rewrite_css_root_paths(css, prefix):
    css = re.sub(
        r"""url\(\s*(["']?)(/(?!/)[^\s)"']*)\1\s*\)""",
        lambda match: "url(" + match[1] + prefix + match[2] + match[1] + ")",
        css,
        flags=re.I,
    )
    return re.sub(
        r"""(@import\s+)(["'])(/(?!/)[^"']*)\2""",
        lambda match: match[1] + match[2] + prefix + match[3] + match[2],
        css,
        flags=re.I,
    )


def read_utf8(path: Path, limit=2_000_000) -> str:
    if path.stat().st_size > limit:
        raise ValueError(f"Arquivo excede o limite de {limit} bytes: {path.name}")
    return path.read_text(encoding="utf-8-sig")


def atomic_write(path: Path, content: str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".seabirds-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if os.name == "posix" and path.is_file():
                os.fchmod(stream.fileno(), stat.S_IMODE(path.stat().st_mode) & 0o777)
            stream.write(content.encode("utf-8") if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class ProjectFiles:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.default_template = Path.cwd() / "templates" / "templete.html"
        if not self.default_template.is_file():
            self.default_template = Path(__file__).parent / "templates" / "legacy.html"
        self.views = {}
        self.image_store = ImageStore(data_dir)
        self.scans = {}
        self.lock = threading.Lock()

    def prepare(self, document: DocumentInput) -> DocumentInput:
        path = document.generation.template_path
        template = read_utf8(local_path(path), 1_000_000) if path else document.template
        if not template:
            template = read_utf8(self.default_template)
        if "{{content}}" not in template:
            raise ValueError("O template precisa conter {{content}}.")
        return document.model_copy(update={"template": template})

    def backup(self, path: Path) -> str | None:
        if not path.exists():
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        key = hashlib.sha256(str(path).encode()).hexdigest()[:12]
        destination = self.data_dir / "file-backups" / stamp / key / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
        return str(destination)

    def view(self, document: DocumentInput):
        document = self.prepare(document)
        generation = document.generation
        output = (
            local_path(generation.output_path)
            if generation.output_path
            else self.default_template.parent / "preview.html"
        )
        html = render_document(document)
        root = self.preview_root(generation, output, html)
        if not output.is_relative_to(root):
            raise ValueError(
                "O arquivo HTML de saída precisa ficar dentro da pasta do site informada."
            )
        return self.register_view(root, output, html, automatic=not bool(generation.site_dir))

    @staticmethod
    def preview_root(generation, output, html):
        if generation.site_dir:
            return local_path(generation.site_dir)
        paths = [output.parent]
        for reference, _ in TemplateAssets(html).references:
            asset = preview_asset_path(reference, output)
            if asset and asset.suffix.lower() in WEB_EXTENSIONS and asset.is_file():
                paths.append(asset.parent)
        try:
            root = Path(os.path.commonpath(paths)).resolve()
        except ValueError:
            return output.parent
        # A template may reference an unrelated file; never infer a whole drive/home.
        if root == Path(root.anchor) or root == Path.home().resolve():
            return output.parent
        return root

    def register_view(self, root, output, html, automatic=False):
        token = uuid4().hex
        prefix = f"/api/generator/view/{token}"
        references = TemplateAssets(html).references
        missing = []
        for reference, stylesheet in references:
            asset = preview_asset_path(reference, output, root)
            if stylesheet and asset and (not asset.is_relative_to(root) or not asset.is_file()):
                missing.append(reference)
        if any(
            reference.startswith("/") and not reference.startswith("//")
            for reference, _ in references
        ):
            soup = BeautifulSoup(html, "html.parser")
            for node in soup.find_all(True):
                for attribute in ("src", "href", "poster"):
                    value = node.get(attribute)
                    if (
                        isinstance(value, str)
                        and value.startswith("/")
                        and not value.startswith("//")
                    ):
                        node[attribute] = prefix + value
            html = str(soup)
        self.views[token] = (root, output, html, time.monotonic())
        self._prune(self.views)
        return {
            "url": f"{prefix}/{output.relative_to(root).as_posix()}",
            "site_root": str(root),
            "root_inferred": automatic,
            "missing_stylesheets": missing,
        }

    def view_generated(self, document: DocumentInput):
        output = local_path(document.generation.output_path)
        if output.suffix.lower() not in {".html", ".htm"} or not output.is_file():
            raise ValueError("Gere o arquivo HTML antes de visualizar.")
        html = read_utf8(output, 12 * 1024 * 1024)
        root = self.preview_root(document.generation, output, html)
        if not output.is_relative_to(root):
            raise ValueError("O HTML precisa ficar dentro da raiz do site para visualização.")
        return self.register_view(
            root, output, html, automatic=not bool(document.generation.site_dir)
        )

    @staticmethod
    def _prune(entries):
        now = time.monotonic()
        for key, value in list(entries.items()):
            if now - value[-1] > 3600:
                entries.pop(key, None)
        while len(entries) > 100:
            entries.pop(next(iter(entries)))

    def generate(self, document: DocumentInput):
        document = self.prepare(document)
        path = local_path(document.generation.output_path)
        if path.suffix.lower() not in {".html", ".htm"}:
            raise ValueError("O arquivo de saída precisa ter extensão .html ou .htm.")
        if document.generation.template_path and path == local_path(
            document.generation.template_path
        ):
            raise ValueError("Escolha uma saída diferente do arquivo de template.")
        # Validate preview root before changing any file.
        view = self.view(document)
        backup = self.backup(path)
        atomic_write(path, render_document(document))
        return {"path": str(path), "backup": backup, **view}

    def save_image(self, raw: bytes, generation: GenerationSettings):
        directory = local_path(generation.images_dir)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("Imagem excede 10 MB.")
        with Image.open(io.BytesIO(raw)) as original:
            if original.width * original.height > 25_000_000:
                raise ValueError("Imagem excede 25 megapixels.")
            image = ImageOps.exif_transpose(original)
            image.load()
            alpha = "A" in image.getbands() or "transparency" in image.info
            image = image.convert("RGBA" if alpha else "RGB")
            directory.mkdir(parents=True, exist_ok=True)
            with self.lock:
                index = generation.image_index
                while True:
                    path = directory / f"img-{index}.png"
                    candidate_url = (generation.image_web_path.rstrip("/") or ".") + "/" + path.name
                    if any(image.web_path == candidate_url for image in generation.images):
                        index += 1
                        continue
                    try:
                        stream = path.open("xb")
                        break
                    except FileExistsError:
                        index += 1
                try:
                    with stream:
                        image.save(stream, format="PNG")
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
        web_path = generation.image_web_path.rstrip("/") or "."
        attachment = self.image_store.add(path, web_path + "/" + path.name)
        return {
            "path": str(path),
            "filename": path.name,
            "next_index": index + 1,
            "markdown": f"![imagem]({web_path}/{path.name})",
            "thumbnail": attachment["thumbnail"],
            "attachment": attachment,
        }

    def snapshot(self, document: DocumentInput):
        if not document.markdown.strip() or not document.generation.output_path:
            return {"path": None}
        stem = local_path(document.generation.output_path).stem
        directory = self.data_dir / "historico" / stem
        directory.mkdir(parents=True, exist_ok=True)
        existing = list(directory.glob(f"autosave_v{document.version:06d}_*.md"))
        if existing:
            return {"path": str(existing[0])}
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S%f")
        path = directory / f"autosave_v{document.version:06d}_{stamp}.md"
        atomic_write(path, document.markdown)
        for obsolete in sorted(directory.glob("autosave_*.md"), reverse=True)[
            document.generation.history_limit :
        ]:
            obsolete.unlink()
        return {"path": str(path)}

    def scan(self, folder: str, operation: str, old: str, new: str):
        root = local_path(folder)
        if not root.is_dir():
            raise ValueError("Pasta não encontrada.")
        if operation not in {"replace", "format"}:
            raise ValueError("Operação inválida.")
        if operation == "replace" and not old:
            raise ValueError("Preencha o texto antigo.")
        candidates, errors = {}, []
        for parent, directories, names in os.walk(root, followlinks=False):
            directories[:] = [
                name
                for name in directories
                if name not in {".git", ".venv", "node_modules", "file-backups"}
                and not (Path(parent) / name).is_symlink()
            ]
            for name in names:
                path = (Path(parent) / name).resolve()
                if not path.is_relative_to(root) or path.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                if len(candidates) >= 5000:
                    raise ValueError("Mais de 5000 arquivos encontrados. Selecione uma subpasta.")
                try:
                    if path.stat().st_size > 10 * 1024 * 1024:
                        raise ValueError("Arquivo maior que 10 MB")
                    raw = path.read_bytes()
                    if len(raw) > 10 * 1024 * 1024:
                        raise ValueError("Arquivo maior que 10 MB")
                    content = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
                    count = content.count(old) if old else 0
                    if operation == "replace" and not count:
                        continue
                    relative = path.relative_to(root).as_posix()
                    candidates[relative] = {
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "count": count,
                    }
                except (OSError, UnicodeError, ValueError) as exc:
                    errors.append(f"{name}: {exc}")
        token = uuid4().hex
        self.scans[token] = (root, operation, old, new, candidates, time.monotonic())
        self._prune(self.scans)
        return {
            "token": token,
            "files": [{"name": name, **meta} for name, meta in candidates.items()],
            "errors": errors,
        }

    def apply(self, token: str, selected: list[str]):
        if token not in self.scans:
            raise ValueError("A busca expirou. Pesquise os arquivos novamente.")
        root, operation, old, new, candidates, _ = self.scans[token]
        if not selected or any(name not in candidates for name in selected):
            raise ValueError("Seleção inválida ou vazia.")
        pending = []
        for name in dict.fromkeys(selected):
            path = (root / name).resolve()
            if not path.is_relative_to(root):
                raise ValueError("O arquivo saiu da pasta selecionada.")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != candidates[name]["sha256"]:
                raise ValueError(f"O arquivo {name} mudou após a busca. Pesquise novamente.")
            content = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
            pending.append(
                (
                    path,
                    content.replace(old, new) if operation == "replace" else format_html(content),
                )
            )
        log = []
        with self.lock:
            for path, content in pending:
                relative = path.relative_to(root).as_posix()
                if hashlib.sha256(path.read_bytes()).hexdigest() != candidates[relative]["sha256"]:
                    raise ValueError(
                        f"O arquivo {relative} mudou durante a aplicação. Pesquise novamente."
                    )
                # Keep one recovery copy for every file actually changed.
                backup = self.backup(path)
                atomic_write(path, content)
                log.append({"path": str(path), "backup": backup})
        self.scans.pop(token, None)
        return {"changed": log}
