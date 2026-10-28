import base64
import binascii
import errno
import io
import re
import secrets
import sqlite3
import tempfile
import warnings
from collections import deque
from contextlib import closing
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from . import __version__
from .config import Settings
from .generator_api import generator_router
from .models import DocumentInput
from .paths import server_user
from .renderer import ASSET_PATTERN, render_document
from .storage import ConflictError, Store

PACKAGE = Path(__file__).parent
MAX_UPLOAD = 10 * 1024 * 1024
ASSET_NAME = re.compile(r"[a-f0-9]{32}\.png\Z")


class BodyLimit:
    """Bound even chunked requests before JSON/multipart parsing allocates the whole body."""

    def __init__(self, app, limit=12 * 1024 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            return await self.app(scope, receive, send)
        size, messages = 0, deque()
        while True:
            message = await receive()
            size += len(message.get("body", b""))
            if size > self.limit:
                return await JSONResponse({"detail": "Envio excede o limite de 12 MB."}, 413)(
                    scope, receive, send
                )
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            return messages.popleft() if messages else await receive()

        await self.app(scope, replay, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.data_dir, settings.history_limit)
    assets = settings.data_dir / "assets"
    assets.mkdir(exist_ok=True)
    app = FastAPI(title="SeaBirdsCloud", version=__version__, docs_url=None, redoc_url=None)
    app.state.store = store

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if (
            not settings.password
            and request.client
            and request.client.host != "testclient"
            and request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
            and request.url.path != "/healthz"
        ):
            return JSONResponse({"detail": "Configure SEABIRDS_PASSWORD para acesso remoto."}, 403)
        if settings.password and request.url.path != "/healthz":
            credentials = ("", "")
            try:
                scheme, value = request.headers.get("authorization", "").split(" ", 1)
                if scheme.lower() == "basic":
                    user, password = base64.b64decode(value, validate=True).decode().split(":", 1)
                    credentials = user, password
            except (ValueError, UnicodeDecodeError, binascii.Error):
                pass
            user_ok = secrets.compare_digest(credentials[0].encode(), settings.username.encode())
            password_ok = secrets.compare_digest(
                credentials[1].encode(), settings.password.encode()
            )
            if not (user_ok and password_ok):
                return JSONResponse(
                    {"detail": "Autenticação necessária."},
                    401,
                    headers={"WWW-Authenticate": 'Basic realm="SeaBirdsCloud", charset="UTF-8"'},
                )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin and urlsplit(origin).netloc != request.headers.get("host")
            ):
                return JSONResponse({"detail": "Origem não permitida."}, 403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if not request.url.path.startswith("/api/generator/view/"):
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(BodyLimit)

    @app.exception_handler(ConflictError)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, 409)

    @app.exception_handler(KeyError)
    async def not_found_handler(request, exc):
        return JSONResponse({"detail": "Documento não encontrado."}, 404)

    @app.exception_handler(ValueError)
    async def invalid_file_operation(request, exc):
        return JSONResponse({"detail": str(exc)}, 422)

    @app.exception_handler(OSError)
    async def file_error(request, exc):
        if exc.errno in {errno.EACCES, errno.EPERM, errno.EROFS}:
            return JSONResponse(
                {
                    "detail": "Sem permissão de acesso ou escrita para o usuário "
                    + server_user()
                    + ". Confira as permissões da pasta e, no serviço Linux, a liberação do diretório do site. Caminho: "
                    + str(exc.filename or "não informado")
                },
                422,
            )
        return JSONResponse({"detail": f"Não foi possível acessar o arquivo ou pasta: {exc}"}, 422)

    def get_document(document_id):
        document = store.get(document_id)
        if document is None:
            raise HTTPException(404, "Documento não encontrado.")
        return document

    @app.get("/healthz")
    def health():
        with store.connection() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "version": __version__}

    @app.get("/")
    def index():
        return FileResponse(PACKAGE / "static" / "index.html")

    @app.get("/api/documents")
    def documents():
        return store.list()

    @app.post("/api/documents", status_code=201)
    def create(document: DocumentInput):
        return store.save(document)

    @app.get("/api/documents/{document_id}")
    def read(document_id: str):
        return get_document(document_id)

    @app.put("/api/documents/{document_id}")
    def update(document_id: str, document: DocumentInput):
        return store.save(document, document_id)

    @app.get("/api/documents/{document_id}/history")
    def history(document_id: str):
        get_document(document_id)
        return store.history(document_id)

    @app.get("/api/documents/{document_id}/history/{revision_id}")
    def revision(document_id: str, revision_id: int):
        result = store.revision(document_id, revision_id)
        if result is None:
            raise HTTPException(404, "Versão não encontrada.")
        return result

    @app.post("/api/preview")
    def preview(document: DocumentInput):
        return {"html": render_document(document)}

    @app.get("/api/documents/{document_id}/export")
    def export(document_id: str):
        saved = get_document(document_id)
        document = DocumentInput(
            **{key: saved[key] for key in DocumentInput.model_fields if key in saved}
        )
        html = render_document(document)
        buffer = io.BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            archive.writestr("index.html", html)
            archive.writestr("documento.md", document.markdown)
            if document.template:
                archive.writestr("template.html", document.template)
            for name in sorted(set(ASSET_PATTERN.findall(html))):
                if (assets / name).is_file():
                    archive.write(assets / name, f"assets/{name}")
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="documentacao.zip"'},
        )

    @app.post("/api/assets", status_code=201)
    async def upload(file: Annotated[UploadFile, File()]):
        raw = await file.read(MAX_UPLOAD + 1)
        await file.close()
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "Imagem excede 10 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.width * image.height > 25_000_000:
                        raise HTTPException(413, "Imagem excede 25 megapixels.")
                    # Decode/re-encode: reject disguised files and omit metadata.
                    image.load()
                    oriented = ImageOps.exif_transpose(image)
                    alpha = "A" in oriented.getbands() or "transparency" in oriented.info
                    converted = oriented.convert("RGBA" if alpha else "RGB")
                    name = f"{uuid4().hex}.png"
                    converted.save(assets / name, format="PNG")
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise HTTPException(422, "Imagem inválida. Envie PNG, JPEG, GIF ou WebP.") from exc
        return {"path": f"assets/{name}", "markdown": f"![Imagem](assets/{name})"}

    @app.get("/assets/{name}")
    def asset(name: str):
        if not ASSET_NAME.fullmatch(name) or not (assets / name).is_file():
            raise HTTPException(404, "Imagem não encontrada.")
        return FileResponse(assets / name, media_type="image/png")

    @app.get("/api/backup")
    def backup():
        buffer = io.BytesIO()
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "seabirds.sqlite3"
            with store.connection() as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
            with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
                archive.write(snapshot, "seabirds.sqlite3")
                for path in assets.glob("*.png"):
                    archive.write(path, f"assets/{path.name}")
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="seabirds-backup.zip"'},
        )

    @app.post("/api/tools/batch")
    async def batch(
        files: Annotated[list[UploadFile], File()],
        operation: Annotated[str, Form()],
        old: Annotated[str, Form()] = "",
        new: Annotated[str, Form()] = "",
    ):
        from .tools import transform_files

        if len(files) > 100:
            raise HTTPException(422, "Selecione no máximo 100 arquivos por lote.")
        payload = []
        total = 0
        for file in files:
            raw = await file.read(MAX_UPLOAD + 1)
            await file.close()
            total += len(raw)
            if total > MAX_UPLOAD:
                raise HTTPException(413, "O lote excede 10 MB.")
            payload.append((file.filename or "arquivo.txt", raw))
        try:
            result = transform_files(payload, operation, old, new)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return Response(
            result,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="arquivos-processados.zip"'},
        )

    app.include_router(generator_router(settings))
    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
    return app
