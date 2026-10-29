"""Criação guiada e fonte portátil associada ao HTML."""

import hashlib
import html
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote

from markdown_it import MarkdownIt

from .filesystem import atomic_write, local_path
from .models import DocumentInput
from .operations import progress
from .project_catalog import IMAGE_EXTENSIONS, CatalogSource
from .storage import ConflictError


def slug(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")[:100] or "documentacao"


def source_path(output):
    return output.with_suffix(".documentacao.json")


class DocumentFlow:
    def __init__(self, workspace):
        self.workspace = workspace
        self.files = workspace.files

    def context(self, document, required=True, check_cover=True):
        """Resolve o mesmo site e a mesma capa para geração e formulários."""
        document = document.model_copy(deep=True)
        generation = document.generation
        output = local_path(generation.output_path) if generation.output_path else None
        if generation.site_dir:
            root = self.workspace.root(generation.site_dir)
        else:
            root = None
            if output:
                for parent in [output.parent, *output.parent.parents]:
                    if (parent / "index.html").is_file():
                        root = self.workspace.root(str(parent))
                        break
            if root is None:
                for value in [
                    generation.github_repository_path,
                    self.workspace.state.get("selected_root", ""),
                ]:
                    if value and (output is None or output.is_relative_to(local_path(value))):
                        root = self.workspace.root(value)
                        break
            if root is None:
                if required:
                    raise ValueError(
                        "Não encontrei a raiz do site a partir do HTML de saída. Selecione a pasta que contém o index.html em Configurar arquivos."
                    )
                return document
        if output and not output.is_relative_to(root):
            raise ValueError("O HTML de saída precisa ficar dentro da raiz do site selecionada.")
        generation.site_dir = str(root)
        if not generation.github_repository_path:
            generation.github_repository_path = str(root)
        if check_cover and generation.catalog_image:
            generation.catalog_image = self.cover(root, output, generation.catalog_image)
        return document

    def cover(self, root, output, value):
        listing = root / self.workspace.catalog_options(root)[1]
        targets = set()
        for base in [listing, output]:
            if base is None:
                continue
            try:
                targets.add(
                    self.workspace.catalog_editor.reference(root, base, value, IMAGE_EXTENSIONS)[1]
                )
            except ValueError:
                pass
        if len(targets) > 1:
            raise ValueError(
                "A capa corresponde a duas imagens diferentes. Selecione a imagem pelo botão Escolher capa ou informe seu caminho absoluto."
            )
        if not targets:
            raise ValueError(
                "Capa não encontrada dentro do site. Use o caminho da imagem no Markdown, no catálogo ou o caminho absoluto de um arquivo existente."
            )
        return "/" + quote(targets.pop().relative_to(root).as_posix(), safe="/-._~")

    def first_cover(self, document, root, output):
        candidates = [image.path for image in document.generation.images]
        for token in MarkdownIt().parse(document.markdown):
            for child in token.children or []:
                if child.type == "image":
                    try:
                        target = self.workspace.catalog_editor.reference(
                            root, output, child.attrGet("src") or "", IMAGE_EXTENSIONS
                        )[1]
                        candidates.append(str(target))
                    except ValueError:
                        continue
        for value in candidates:
            try:
                return self.cover(root, output, value)
            except ValueError:
                continue
        raise ValueError("Cole uma imagem ou selecione a capa antes de cadastrar a documentação.")

    def prepare(self, root, title, category, description, cover="", template=""):
        root = self.workspace.root(root, register=True)
        name, group = slug(title), slug(category)
        output = f"projetos/{group}/{name}.html"
        images = f"imagens/projetos/{group}/{name}"
        path = self.workspace.page(root, output, require_exists=False)
        if path.exists() or source_path(path).exists():
            raise ValueError(
                "Já existe uma documentação com este caminho. Abra a fonte existente ou altere o título."
            )
        if template:
            self.files.prepare(DocumentInput(generation={"template_path": template}))
        return DocumentInput(
            title=title,
            markdown="# " + title + "\n\n",
            generation={
                "site_dir": str(root),
                "github_repository_path": str(root),
                "template_path": template,
                "output_path": str(path),
                "images_dir": str(root / images),
                "image_web_path": Path(os.path.relpath(root / images, path.parent)).as_posix(),
                "catalog_category": category,
                "catalog_description": description,
                "catalog_image": cover,
                "register_catalog": True,
                "save_source": True,
            },
        ).model_dump()

    def portable(self, document, root, output):
        data = document.model_dump()
        generation = data["generation"]
        for field in ["output_path", "images_dir", "template_path"]:
            if generation.get(field):
                path = local_path(generation[field])
                generation[field] = (
                    path.relative_to(root).as_posix() if path.is_relative_to(root) else ""
                )
        generation["site_dir"] = "."
        generation["github_repository_path"] = ""
        generation["output_version"] = ""
        if generation.get("catalog_image"):
            listing = root / self.workspace.catalog_options(root)[1]
            generation["catalog_image"] = self.workspace.catalog_editor.reference(
                root, listing, generation["catalog_image"], IMAGE_EXTENSIONS
            )[0]
        for image in generation["images"]:
            path = local_path(image["path"])
            if not path.is_relative_to(root):
                raise ValueError("As imagens da fonte precisam estar dentro do site.")
            image["path"] = path.relative_to(root).as_posix()
        return {
            "format": "seabirds-document-1",
            "output": output.relative_to(root).as_posix(),
            "document": data,
        }

    def read(self, root, relative):
        root = self.workspace.root(root)
        output = self.workspace.page(root, relative)
        source = source_path(output)
        if not source.is_file() or source.is_symlink() or source.stat().st_size > 8 * 1024 * 1024:
            raise ValueError(
                "Esta página não tem uma fonte associada. Use Editar HTML para páginas antigas."
            )
        data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("format") != "seabirds-document-1" or data.get("output") != relative:
            raise ValueError("A fonte não corresponde à página selecionada.")
        doc = data["document"]
        generation = doc["generation"]
        for field in ["output_path", "images_dir", "template_path"]:
            if generation.get(field):
                generation[field] = str(
                    self.workspace.catalog_editor.site_path(root, generation[field])
                )
        if local_path(generation["output_path"]) != output.resolve():
            raise ValueError("A fonte aponta para outra página.")
        generation.update(
            site_dir=str(root),
            github_repository_path=str(root),
            output_version=self.workspace.digest(output),
        )
        for image in generation.get("images", []):
            path = self.workspace.catalog_editor.site_path(root, image["path"])
            image["path"] = str(path)
            if path.is_file():
                image["id"] = self.files.image_store.add(path, image["web_path"])["id"]
        return DocumentInput.model_validate(doc).model_dump()

    def generate(self, document):
        if not document.generation.save_source and not document.generation.register_catalog:
            result = self.files.generate(document)
            context = (
                {"site_dir": result["site_root"]}
                if (Path(result["site_root"]) / "index.html").is_file()
                else {}
            )
            return {**result, "context": context}
        with self.workspace.lock:
            if not document.generation.output_path:
                raise ValueError("Informe o arquivo HTML de saída antes de gerar a documentação.")
            document = self.context(document)
            document = self.files.prepare(document)
            generation = document.generation
            root = self.workspace.root(generation.site_dir, register=True)
            output = local_path(generation.output_path)
            relative = output.relative_to(root).as_posix()
            self.workspace.page(root, relative, require_exists=False)
            if generation.output_version and (
                not output.is_file() or self.workspace.digest(output) != generation.output_version
            ):
                raise ConflictError(
                    "O HTML mudou fora do gerador. Reabra a fonte antes de gerar novamente."
                )
            if generation.template_path and output == local_path(generation.template_path):
                raise ValueError("A saída não pode substituir o template.")
            if (
                generation.save_source
                and generation.images_dir
                and not local_path(generation.images_dir).is_relative_to(root)
            ):
                raise ValueError(
                    "A pasta das imagens precisa estar dentro do site para salvar a fonte portátil."
                )
            view = self.files.view(document)
            changes = {output: view["html"] if "html" in view else None}
            from .renderer import render_document

            changes[output] = render_document(document)
            catalog = None
            if generation.register_catalog:
                progress("Preparando o cadastro da documentação", 30)
                path, listing = self.workspace.catalog_options(root)
                catalog, page = self.workspace.catalog_editor.paths(root, path, listing)
                raw = catalog.read_bytes()
                source = CatalogSource(raw.decode("utf-8-sig"))
                link = self.workspace.catalog_editor.reference(
                    root, page, str(output), {".html", ".htm"}, exists=False
                )[0]
                cover = generation.catalog_image or self.first_cover(document, root, output)
                generation.catalog_image = cover
                image = self.workspace.catalog_editor.reference(
                    root, page, cover, IMAGE_EXTENSIONS
                )[0]
                category, description = (
                    generation.catalog_category.strip(),
                    generation.catalog_description.strip(),
                )
                if not category or not description:
                    raise ValueError("Informe categoria e descrição da documentação.")
                matching = []
                for entry in source.entries.values():
                    try:
                        target = self.workspace.catalog_editor.reference(
                            root, page, entry["link"], {".html", ".htm"}, exists=False
                        )[1]
                    except ValueError:
                        continue
                    if target == output:
                        matching.append(entry["id"])
                if len(matching) > 1:
                    raise ValueError(
                        "Esta página está duplicada no catálogo. Corrija os cadastros antes de gerar."
                    )
                values = {
                    key: html.escape(value, quote=True)
                    for key, value in {
                        "titulo": document.title,
                        "descricao": description,
                        "imagem": image,
                        "link": link,
                    }.items()
                }
                changed = source.change(category, values, matching[0] if matching else "")
                changes[catalog] = ("\ufeff" if raw.startswith(b"\xef\xbb\xbf") else "") + changed
            if generation.save_source:
                changes[source_path(output)] = json.dumps(
                    self.portable(document, root, output), ensure_ascii=False, indent=2
                )
            previous = {path: path.read_bytes() if path.is_file() else None for path in changes}
            backups = {path: self.files.backup(path) for path in changes}
            written = []
            try:
                for path, content in changes.items():
                    if (path.read_bytes() if path.is_file() else None) != previous[path]:
                        raise ConflictError(
                            "Um arquivo mudou durante a geração. Reabra antes de continuar."
                        )
                    atomic_write(path, content)
                    written.append(path)
            except Exception:
                for path in reversed(written):
                    if previous[path] is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_write(path, previous[path])
                raise
            if catalog:
                self.workspace.state.setdefault("catalogs", {})[str(root)] = {
                    "path": catalog.relative_to(root).as_posix(),
                    "page": self.workspace.catalog_options(root)[1],
                    "backup": "",
                    "version": hashlib.sha256(catalog.read_bytes()).hexdigest(),
                }
                self.workspace.persist()
            return {
                **view,
                "path": str(output),
                "backup": backups[output],
                "source": str(source_path(output)) if generation.save_source else "",
                "catalog_updated": bool(catalog),
                "output_version": self.workspace.digest(output),
                "context": {
                    "site_dir": str(root),
                    "github_repository_path": generation.github_repository_path,
                    "catalog_image": generation.catalog_image,
                },
            }
