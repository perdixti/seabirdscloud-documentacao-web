from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .models import DocumentInput
from .site_workspace import SiteWorkspace


class SiteInput(BaseModel):
    root: str = Field(min_length=1, max_length=4096)


class PageInput(SiteInput):
    path: str = Field(min_length=1, max_length=4096)


class PageSaveInput(PageInput):
    version: str = Field(pattern=r"^[a-f0-9]{64}$")
    html: str = Field(max_length=2_000_000)


class PageSelection(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    version: str = Field(pattern=r"^[a-f0-9]{64}$")


class TrashPagesInput(SiteInput):
    pages: list[PageSelection] = Field(min_length=1, max_length=100)
    confirm: Literal[True]


class CloneInput(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    destination: str = Field(min_length=1, max_length=4096)
    author_name: str = Field(default="", max_length=200)
    author_email: str = Field(default="", max_length=254)


class EditorSettingsInput(BaseModel):
    url: str = Field(default="", max_length=4096)
    kind: Literal["code-server", "vscode-serve-web"] = "code-server"


class LocalEditorInput(SiteInput):
    confirm_license: Literal[True]
    port: int = Field(default=8765, ge=1024, le=65535)


def site_router(settings, files, filesystem_access):
    router = APIRouter(prefix="/site")
    workspace = SiteWorkspace(settings.data_dir, files, managed_editor_url=settings.editor_url)

    def local_request(request):
        return bool(
            request.client
            and request.client.host in {"127.0.0.1", "::1"}
            and request.url.hostname in {"127.0.0.1", "localhost", "::1"}
        )

    @router.get("/settings")
    def settings_read(request: Request):
        filesystem_access(request)
        result = workspace.settings()
        result["local_editor_available"] = result["local_editor_available"] and local_request(
            request
        )
        return result

    @router.post("/settings/editor")
    def editor_settings(payload: EditorSettingsInput, request: Request):
        filesystem_access(request)
        return workspace.editor_settings(payload.url, payload.kind)

    @router.post("/pages")
    def pages(payload: SiteInput, request: Request):
        filesystem_access(request)
        return workspace.pages(payload.root)

    @router.post("/pages/read")
    def read(payload: PageInput, request: Request):
        filesystem_access(request)
        return workspace.read_page(payload.root, payload.path)

    @router.post("/pages/save")
    def save(payload: PageSaveInput, request: Request):
        filesystem_access(request)
        return workspace.save_page(payload.root, payload.path, payload.version, payload.html)

    @router.post("/pages/trash")
    def trash(payload: TrashPagesInput, request: Request):
        filesystem_access(request)
        return workspace.trash_pages(payload.root, payload.pages)

    @router.post("/pages/trash/{identifier}/restore")
    def restore(identifier: str, request: Request):
        filesystem_access(request)
        return workspace.restore_page(identifier)

    @router.post("/pages/view")
    def view(payload: PageInput, request: Request):
        filesystem_access(request)
        root = workspace.root(payload.root)
        path = workspace.page(root, payload.path)
        return files.view_generated(
            DocumentInput(generation={"output_path": str(path), "site_dir": str(root)})
        )

    @router.post("/editor-link")
    def editor_link(payload: SiteInput, request: Request):
        filesystem_access(request)
        return workspace.editor_link(payload.root)

    @router.post("/editor/local/start")
    def local_editor(payload: LocalEditorInput, request: Request):
        filesystem_access(request)
        if not local_request(request):
            raise HTTPException(
                403, "O iniciador do editor local só pode ser usado neste computador."
            )
        return workspace.start_local_editor(payload.root, payload.confirm_license, payload.port)

    @router.post("/clone")
    def clone(payload: CloneInput, request: Request):
        filesystem_access(request)
        return workspace.clone(
            payload.url, payload.destination, payload.author_name, payload.author_email
        )

    return router
