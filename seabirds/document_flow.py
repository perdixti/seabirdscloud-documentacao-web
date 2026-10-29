"""Criação guiada e fonte portátil associada ao HTML."""

import hashlib
import html
import json
import os
import re
import unicodedata
from pathlib import Path

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
            return self.files.generate(document)
        with self.workspace.lock:
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
            if generation.save_source:
                changes[source_path(output)] = json.dumps(
                    self.portable(document, root, output), ensure_ascii=False, indent=2
                )
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
                cover = generation.catalog_image or (
                    generation.images[0].path if generation.images else ""
                )
                if not cover:
                    raise ValueError(
                        "Cole uma imagem ou selecione a capa antes de gerar e cadastrar a documentação."
                    )
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
                        atomic_write(path, previous[path].decode("utf-8"))
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
            }
