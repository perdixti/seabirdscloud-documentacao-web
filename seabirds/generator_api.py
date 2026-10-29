import mimetypes
import os
import webbrowser
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from markdown_it import MarkdownIt
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from .filesystem import WEB_EXTENSIONS, ProjectFiles, local_path, read_utf8, rewrite_css_root_paths
from .github import GitHubPublisher
from .github_api import github_router
from .models import DocumentInput, GenerationSettings
from .paths import directory_entries, folder_access
from .renderer import render_document
from .site_api import site_router


class PathInput(BaseModel):
    path: str = Field(max_length=4096)


class ScanInput(BaseModel):
    folder: str = Field(max_length=4096)
    operation: str
    old: str = Field(default="", max_length=1_000_000)
    new: str = Field(default="", max_length=1_000_000)


class ApplyInput(BaseModel):
    token: str
    selected: list[str] = Field(max_length=5000)


class BrowseInput(BaseModel):
    path: str = Field(default="", max_length=4096)
    kind: str = "folder"


class ImageFolderInput(BaseModel):
    directory: str = Field(max_length=4096)
    web_path: str = Field(default="imagens", max_length=4096)


class DeleteImageInput(BaseModel):
    confirm: Literal[True]


def generator_router(settings, store=None, jobs=None, gate=None):
    router = APIRouter(prefix="/api/generator")
    files = ProjectFiles(settings.data_dir)

    def native_available(request):
        return (
            os.name == "nt"
            and request.client
            and request.client.host in {"127.0.0.1", "::1"}
            and request.url.hostname in {"localhost", "127.0.0.1", "::1"}
        )

    def filesystem_access(request: Request):
        if (
            not settings.password
            and request.client
            and request.client.host not in {"127.0.0.1", "::1", "testclient"}
        ):
            raise HTTPException(
                403, "Configure SEABIRDS_PASSWORD para usar arquivos por acesso remoto."
            )

    @router.get("/config")
    def config(request: Request):
        filesystem_access(request)
        return {
            "template": read_utf8(files.default_template),
            "template_path": str(files.default_template),
            "native_dialogs": bool(native_available(request)),
            "local_file_open": bool(native_available(request)),
            "history_dir": str(settings.data_dir / "historico"),
            "platform": "windows" if os.name == "nt" else "posix",
        }

    @router.post("/template")
    def template(payload: PathInput, request: Request):
        filesystem_access(request)
        path = local_path(payload.path)
        content = read_utf8(path, 1_000_000)
        if "{{content}}" not in content:
            raise ValueError("O template precisa conter {{content}}.")
        return {"path": str(path), "template": content}

    @router.post("/generate")
    def generate(document: DocumentInput, request: Request):
        filesystem_access(request)
        return management.flow.generate(document)

    @router.post("/download")
    def download(document: DocumentInput, request: Request):
        filesystem_access(request)
        html = render_document(files.prepare(document))
        return Response(
            html,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="documentacao.html"'},
        )

    @router.post("/preview")
    def preview(document: DocumentInput, request: Request):
        filesystem_access(request)
        return files.view(document)

    @router.post("/open-output")
    def open_output(document: DocumentInput, request: Request):
        filesystem_access(request)
        return files.view_generated(document)

    @router.post("/open-local")
    def open_local(payload: PathInput, request: Request):
        filesystem_access(request)
        if not native_available(request):
            raise HTTPException(
                409, "A abertura de arquivo no Windows só está disponível no acesso local."
            )
        path = local_path(payload.path)
        if path.suffix.lower() not in {".html", ".htm"} or not path.is_file():
            raise ValueError("O arquivo HTML não existe. Gere o HTML antes de visualizar.")
        url = path.as_uri()
        if not webbrowser.open_new_tab(url):
            raise ValueError("Não foi possível abrir o arquivo no navegador padrão.")
        return {"url": url}

    @router.post("/snapshot")
    def snapshot(document: DocumentInput, request: Request):
        filesystem_access(request)
        return files.snapshot(document)

    @router.get("/view/{token}/{relative:path}")
    def view(token: str, relative: str, request: Request):
        filesystem_access(request)
        entry = files.views.get(token)
        if not entry:
            raise HTTPException(404, "Prévia expirada. Atualize a visualização.")
        root, output, html, _ = entry
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise HTTPException(404, "Recurso fora da pasta do site.")
        if path == output:
            return HTMLResponse(
                html,
                headers={
                    "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'self' 'unsafe-inline'; "
                    "style-src 'self' 'unsafe-inline' https:; img-src 'self' data: https: http:; "
                    "font-src 'self' data: https:; connect-src 'none'; form-action 'none'; frame-ancestors 'self'"
                },
            )
        if path.suffix.lower() not in WEB_EXTENSIONS or not path.is_file():
            raise HTTPException(404, "Recurso não encontrado na pasta do site.")
        if path.suffix.lower() == ".css":
            css = rewrite_css_root_paths(
                read_utf8(path, 10 * 1024 * 1024), f"/api/generator/view/{token}"
            )
            return Response(css, media_type="text/css")
        return FileResponse(
            path,
            media_type=mimetypes.guess_type(path)[0],
            headers={"Content-Security-Policy": "sandbox; default-src 'none'"},
        )

    @router.post("/image", status_code=201)
    async def image(
        file: Annotated[UploadFile, File()], generation: Annotated[str, Form()], request: Request
    ):
        filesystem_access(request)
        raw = await file.read(10 * 1024 * 1024 + 1)
        await file.close()
        try:
            return files.save_image(raw, GenerationSettings.model_validate_json(generation))
        except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise ValueError("A área de transferência não contém uma imagem válida.") from exc

    @router.get("/image/{token}")
    def thumbnail(token: str, request: Request):
        filesystem_access(request)
        try:
            path = files.image_store.image_path(token)
        except ValueError:
            raise HTTPException(404, "Imagem não encontrada.") from None
        if not path.is_file():
            raise HTTPException(404, "Imagem não encontrada.")
        return FileResponse(path)

    @router.post("/images/sync")
    def sync_images(document: DocumentInput, request: Request):
        filesystem_access(request)
        records = files.image_store.list_ids([image.id for image in document.generation.images])
        contexts = {image.id: image.web_path for image in document.generation.images}
        for record in records:
            record["web_path"] = contexts.get(record["id"], record["web_path"])
        if document.generation.images_dir:
            references = []
            for token in MarkdownIt().parse(document.markdown):
                references.extend(
                    child.attrGet("src") for child in token.children or [] if child.type == "image"
                )
            names = {
                Path(reference.replace("\\", "/")).name
                for reference in references
                if reference and "://" not in reference and not reference.startswith("data:")
            }
            known = {record["filename"] for record in records}
            imported = (
                files.image_store.import_folder(
                    local_path(document.generation.images_dir),
                    document.generation.image_web_path,
                    names=names - known,
                )
                if names - known
                else []
            )
            records.extend(imported)
        return records

    @router.post("/images/import-folder")
    def import_images(payload: ImageFolderInput, request: Request):
        filesystem_access(request)
        return files.image_store.import_folder(local_path(payload.directory), payload.web_path)

    @router.post("/images/{identifier}/move")
    def move_image(identifier: str, payload: ImageFolderInput, request: Request):
        filesystem_access(request)
        return files.image_store.move(identifier, local_path(payload.directory), payload.web_path)

    @router.post("/images/{identifier}/trash")
    def trash_image(identifier: str, request: Request):
        filesystem_access(request)
        return files.image_store.trash(identifier)

    @router.post("/images/{identifier}/restore")
    def restore_image(identifier: str, request: Request):
        filesystem_access(request)
        return files.image_store.restore(identifier)

    @router.delete("/images/{identifier}")
    def delete_image(identifier: str, payload: DeleteImageInput, request: Request):
        filesystem_access(request)
        return files.image_store.delete(identifier)

    @router.post("/scan")
    def scan(payload: ScanInput, request: Request):
        filesystem_access(request)
        return files.scan(payload.folder, payload.operation, payload.old, payload.new)

    @router.post("/apply")
    def apply(payload: ApplyInput, request: Request):
        filesystem_access(request)
        return files.apply(payload.token, payload.selected)

    @router.post("/read-markdown")
    def read_markdown(payload: PathInput, request: Request):
        filesystem_access(request)
        path = local_path(payload.path)
        if path.suffix.lower() not in {".md", ".txt"}:
            raise ValueError("Selecione um arquivo Markdown ou texto.")
        return {"title": path.stem, "markdown": read_utf8(path)}

    @router.get("/legacy-history")
    def legacy_history(request: Request):
        filesystem_access(request)
        roots = {Path.cwd() / "historico", settings.data_dir / "historico"}
        return [
            {"path": str(path), "project": path.parent.name, "name": path.name}
            for root in roots
            for path in sorted(root.glob("*/autosave_*.md"), reverse=True)
            if path.is_file()
        ]

    @router.post("/pick/{kind}")
    def pick(kind: str, request: Request):
        filesystem_access(request)
        if not native_available(request):
            return {"path": "", "supported": False}
        import tkinter as tk
        from tkinter import filedialog

        try:
            root = tk.Tk()
        except tk.TclError:
            return {"path": "", "supported": False}
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            if kind in {"images", "site", "folder"}:
                path = filedialog.askdirectory(parent=root)
            elif kind == "output":
                path = filedialog.asksaveasfilename(
                    parent=root, defaultextension=".html", filetypes=[("HTML", "*.html")]
                )
            elif kind == "template":
                path = filedialog.askopenfilename(parent=root, filetypes=[("HTML", "*.html *.htm")])
            elif kind == "markdown":
                path = filedialog.askopenfilename(
                    parent=root, filetypes=[("Markdown", "*.md *.txt")]
                )
            elif kind == "image":
                path = filedialog.askopenfilename(
                    parent=root,
                    filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp *.gif *.svg *.ico")],
                )
            else:
                raise ValueError("Tipo de seleção inválido.")
        except tk.TclError:
            return {"path": "", "supported": False}
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass
        return {"path": path, "supported": True}

    @router.post("/browse")
    def browse(payload: BrowseInput, request: Request):
        filesystem_access(request)
        if payload.path.strip():
            directory = local_path(payload.path)
            if directory.is_file():
                directory = directory.parent
        else:
            directory = next(
                (
                    path
                    for path in [Path("/workspace"), Path("/srv/seabirds"), settings.data_dir]
                    if path.is_dir()
                ),
                settings.data_dir,
            )
        if not directory.is_dir():
            raise ValueError("Pasta não encontrada no servidor: " + str(directory))
        entries = []
        candidates, skipped = directory_entries(directory)
        for path, is_directory in candidates:
            if is_directory:
                entries.append({"name": path.name, "path": str(path), "directory": True})
            elif payload.kind in {"template", "output"} and path.suffix.lower() in {
                ".html",
                ".htm",
            }:
                entries.append({"name": path.name, "path": str(path), "directory": False})
            elif payload.kind == "markdown" and path.suffix.lower() in {".md", ".txt"}:
                entries.append({"name": path.name, "path": str(path), "directory": False})
            elif payload.kind == "image" and path.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".gif",
                ".svg",
                ".ico",
            }:
                entries.append({"name": path.name, "path": str(path), "directory": False})
            if len(entries) >= 1000:
                break
        return {
            "path": str(directory),
            "parent": str(directory.parent),
            "entries": entries,
            "skipped": skipped,
            "access": folder_access(directory),
        }

    @router.post("/mkdir")
    def mkdir(payload: PathInput, request: Request):
        filesystem_access(request)
        path = local_path(payload.path)
        path.mkdir(parents=False, exist_ok=False)
        return {"path": str(path)}

    publisher = GitHubPublisher(settings.data_dir)
    from .management import Management
    from .site_workspace import SiteWorkspace

    workspace = SiteWorkspace(
        settings.data_dir, files, publisher=publisher, managed_editor_url=settings.editor_url
    )
    management = Management(settings, workspace, store, jobs, gate, filesystem_access)
    router.management = management
    router.include_router(github_router(settings, filesystem_access, publisher))
    router.include_router(site_router(settings, files, filesystem_access, publisher, workspace))
    return router
