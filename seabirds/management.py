"""Gerenciamento web: operações, diagnóstico, verificação, backup e revisão."""

import os
import platform
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from starlette.concurrency import run_in_threadpool

from .backups import Backups
from .document_flow import DocumentFlow
from .github_api import PlanInput, PublishInput, ReviewInput, SiteReviewInput
from .models import DocumentInput
from .operations import progress
from .paths import folder_access, server_user
from .site_api import CloneInput, DeletePageInput, PageInput, SiteInput
from .site_audit import SiteAudit
from .text_review import TextReview


class JobInput(BaseModel):
    kind: str = Field(max_length=80)
    payload: dict
    request_id: str = Field(pattern=r"^[A-Za-z0-9-]{8,100}$")


class BackupSettingsInput(BaseModel):
    enabled: bool = False
    interval_hours: int = Field(default=24, ge=1, le=168)
    retention: int = Field(default=7, ge=1, le=100)
    password: SecretStr = SecretStr("")


class BackupCreateInput(BaseModel):
    scheduled: bool = False


class BackupOpenInput(BaseModel):
    identifier: str = Field(pattern=r"^[a-f0-9]{32}$")
    password: SecretStr
    targets: dict[str, str] = Field(default_factory=dict, max_length=30)


class BackupRestoreInput(BaseModel):
    token: str = Field(pattern=r"^[a-f0-9]{32}$")
    password: SecretStr
    confirm: Literal[True]


class IdentifierInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=64)


class PageJobInput(SiteInput):
    identifier: str = Field(pattern=r"^[a-f0-9]{32}$")


class DeleteJobInput(DeletePageInput):
    identifier: str = Field(pattern=r"^[a-f0-9]{32}$")


class TextInput(BaseModel):
    text: str = Field(max_length=50_000)


class TextSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["local", "openai"] = "local"
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=100)
    allow_cloud: bool = False
    ignored_words: list[str] = Field(default_factory=list, max_length=500)
    key_action: Literal["keep", "replace", "remove"] = "keep"
    api_key: SecretStr = SecretStr("")


class PrepareDocumentInput(SiteInput):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    cover: str = Field(default="", max_length=4096)
    template: str = Field(default="", max_length=4096)


class Management:
    def __init__(self, settings, workspace, store, jobs, gate, filesystem_access):
        self.settings, self.workspace, self.store = settings, workspace, store
        self.jobs, self.gate = jobs, gate
        self.filesystem_access = filesystem_access
        self.publisher, self.files = workspace.publisher, workspace.files
        self.review = TextReview(settings.data_dir)
        self.flow = DocumentFlow(workspace)
        self.audit = SiteAudit(workspace)
        self.publisher.site_audit = self.audit.run
        self.backups = Backups(settings, workspace, store, gate, self.reload)
        self.schemas = {}
        self.register(
            "github.review", ReviewInput, lambda p: self.publisher.inspect(p.directory, p.document)
        )
        self.register(
            "github.review-site",
            SiteReviewInput,
            lambda p: self.publisher.inspect(p.directory, DocumentInput(), site_only=True),
        )
        self.register("github.sync", PlanInput, lambda p: self.publisher.sync(p.token))
        self.register(
            "github.publish",
            PublishInput,
            lambda p: self.publisher.publish(p.token, p.selected, p.message),
        )
        self.register("github.retry", IdentifierInput, lambda p: self.publisher.retry(p.identifier))
        self.register(
            "site.clone",
            CloneInput,
            lambda p: self.workspace.clone(p.url, p.destination, p.author_name, p.author_email),
        )
        self.register("site.audit", SiteInput, lambda p: self.audit.run(p.root))
        self.register(
            "site.delete-preview",
            PageJobInput,
            lambda p: self.workspace.preview_delete_page(p.root, p.identifier),
        )
        self.register(
            "site.delete",
            DeleteJobInput,
            lambda p: self.workspace.delete_page(p.root, p.identifier, p.token),
        )
        self.register("document.generate", DocumentInput, lambda p: self.flow.generate(p))
        self.register("text.review", TextInput, lambda p: self.review.review(p.text))
        self.register("diagnostics", SiteInput, lambda p: self.diagnostics(p.root))
        self.register("diagnostics.git", SiteInput, lambda p: self.test_git(p.root))
        self.register(
            "backup.create",
            BackupCreateInput,
            lambda p: self.backups.create(scheduled=p.scheduled),
            exclusive=True,
        )
        self.register(
            "backup.inspect", BackupOpenInput, lambda p: self.inspect_backup(p), exclusive=False
        )
        self.register(
            "backup.preview",
            BackupOpenInput,
            lambda p: self.backups.preview(p.identifier, p.password.get_secret_value(), p.targets),
        )
        self.register(
            "backup.restore",
            BackupRestoreInput,
            lambda p: self.backups.restore(p.token, p.password.get_secret_value()),
            exclusive=True,
        )

    def register(self, name, schema, handler, exclusive=False):
        self.schemas[name] = schema

        def run(payload):
            model = schema.model_validate(payload)
            if exclusive:
                return handler(model)
            if not self.gate.enter():
                raise ValueError("Backup ou restauração em andamento. Aguarde.")
            try:
                progress("Preparando " + name, 2)
                return handler(model)
            finally:
                self.gate.leave()

        self.jobs.register(name, run)

    def start(self, payload):
        if payload.kind not in self.schemas:
            raise ValueError("Operação não disponível.")
        try:
            model = self.schemas[payload.kind].model_validate(payload.payload)
        except ValidationError:
            raise ValueError("Campos inválidos para esta operação. Confira o formulário.") from None
        data = model.model_dump()
        for name, value in data.items():
            if isinstance(value, SecretStr):
                data[name] = value.get_secret_value()
        return self.jobs.start(payload.kind, data, payload.request_id)

    def reload(self):
        import json

        from .github_settings import GitHubSettings

        state = (
            json.loads(self.workspace.catalog.read_text(encoding="utf-8"))
            if self.workspace.catalog.exists()
            else {"roots": [], "trash": [], "editor_url": "", "editor_kind": "code-server"}
        )
        self.workspace.state.clear()
        self.workspace.state.update(state)
        image_store = self.files.image_store
        image_store.entries = (
            json.loads(image_store.catalog.read_text(encoding="utf-8"))
            if image_store.catalog.exists()
            else {}
        )
        self.publisher.preferences = GitHubSettings(self.settings.data_dir)
        self.publisher.token = self.publisher.preferences.token(self.publisher.environment_token)
        self.publisher.publications = (
            json.loads(self.publisher.catalog.read_text(encoding="utf-8"))
            if self.publisher.catalog.exists()
            else []
        )
        self.publisher.plans.clear()
        self.files.views.clear()
        self.review.reload()

    def inspect_backup(self, payload):
        with self.backups.opened(payload.identifier, payload.password.get_secret_value()) as (
            _,
            manifest,
            _,
        ):
            return {key: manifest[key] for key in ["version", "created_at", "sites"]} | {
                "files": len(manifest["files"]),
                "identifier": payload.identifier,
            }

    def diagnostics(self, value):
        from . import __version__

        root = self.workspace.root(value)
        checks = []

        def add(name, ok, detail):
            checks.append({"name": name, "status": "ok" if ok else "warning", "detail": detail})

        add(
            "Aplicação",
            True,
            "SeaBirdsCloud "
            + __version__
            + " · Python "
            + platform.python_version()
            + " · "
            + platform.system(),
        )
        add("Usuário do serviço", True, server_user())
        process_status = Path("/proc/self/status")
        if process_status.exists():
            for line in process_status.read_text().splitlines():
                if line.startswith("VmRSS:"):
                    add(
                        "Memória do gerador",
                        True,
                        str(round(int(line.split()[1]) / 1024, 1)) + " MB de RAM neste processo",
                    )
        add(
            "Perfil do revisor",
            True,
            "Regras locais, sem modelo e sem GPU"
            if self.review.settings.get("provider") == "local"
            else "Cliente de API; o modelo roda no provedor externo",
        )
        add(
            "Fila de operações",
            True,
            "Uma operação em segundo plano por vez para limitar CPU e memória",
        )
        for name, path in [("Dados", self.settings.data_dir), ("Site", root)]:
            access = folder_access(path)
            add(
                name,
                access["writable"],
                str(path)
                + (
                    " · leitura e escrita"
                    if access["writable"]
                    else " · sem escrita; confira dono, permissões e ReadWritePaths do serviço"
                ),
            )
            free = shutil.disk_usage(path).free
            add(
                "Espaço livre: " + name,
                free >= 200 * 1024**2,
                str(round(free / 1024**2)) + " MB livres",
            )
        with self.store.connection() as db:
            ok = db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        add("Banco de dados", ok, "SQLite íntegro" if ok else "O banco precisa de recuperação")
        add(
            "Git instalado",
            bool(shutil.which("git")),
            shutil.which("git") or "Instale o Git no servidor",
        )
        try:
            git_root = self.publisher.root(str(root))
            repository = self.publisher.repository(git_root)[0]
            branch = self.publisher.text(git_root, "branch", "--show-current")
            add("Repositório", branch == "main", repository + " · branch " + branch)
            author = self.publisher.author(git_root)
            add(
                "Autor dos commits",
                bool(author["name"] and author["email"]),
                author["name"]
                + (" · e-mail configurado" if author["email"] else " · configure o e-mail"),
            )
            add(
                "Autenticação Git",
                bool(self.publisher.token),
                "Token configurado; use Testar acesso para validar."
                if self.publisher.token
                else "Sem token na aplicação. SSH/helper Git podem estar configurados; use Testar acesso.",
            )
        except ValueError as exc:
            add("Repositório", False, self.publisher.clean_error(str(exc)))
        add(
            "Editor",
            bool(self.workspace.settings().get("editor_url")),
            self.workspace.settings().get("editor_url") or "Configure o editor pela interface",
        )
        if os.name == "posix":
            for name in ["seabirds", "seabirds-editor", "seabirds-web"]:
                try:
                    result = subprocess.run(
                        ["systemctl", "is-active", name], capture_output=True, text=True, timeout=2
                    )
                    add(
                        "Serviço " + name,
                        result.stdout.strip() == "active",
                        result.stdout.strip() or "Não disponível nesta instalação",
                    )
                except (OSError, subprocess.TimeoutExpired):
                    add("Serviço " + name, False, "Consulta indisponível neste ambiente")
        for name, port in [
            ("Gerador interno", int(os.environ.get("SEABIRDS_PORT", "8000"))),
            ("Editor interno", 8765),
        ]:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    add(name, True, "Respondendo em 127.0.0.1:" + str(port))
            except OSError:
                add(name, False, "Sem conexão local na porta " + str(port))
        add(
            "Backup",
            bool(self.backups.password()),
            "Senha configurada; " + str(len(self.backups.list())) + " backup(s) disponível(is)"
            if self.backups.password()
            else "Configure a senha e o agendamento pela interface",
        )
        return {
            "root": str(root),
            "checks": checks,
            "note": "Um teste local não confirma o acesso externo. Se o navegador não conecta, confira o endereço público, a porta do proxy e as regras de rede/firewall da EC2 ou do LXC.",
        }

    def test_git(self, value):
        root = self.publisher.root(value)
        self.publisher.repository(root)
        self.publisher.git(
            root, "ls-remote", "--exit-code", "origin", "refs/heads/main", timeout=15
        )
        return {
            "ok": True,
            "message": "Acesso de leitura à main confirmado para o usuário do aplicativo. O teste não cria commit nem push.",
        }


def management_router(management):
    router = APIRouter(prefix="/api", dependencies=[Depends(management.filesystem_access)])

    @router.post("/operations")
    def start(payload: JobInput):
        return management.start(payload)

    @router.get("/operations")
    def operations():
        return management.jobs.list()

    @router.get("/operations/{identifier}")
    def operation(identifier: str):
        return management.jobs.get(identifier)

    @router.get("/maintenance/backups")
    def backups():
        return {"settings": management.backups.status(), "files": management.backups.list()}

    @router.post("/maintenance/backups/settings")
    def configure_backup(payload: BackupSettingsInput):
        return management.backups.configure(
            payload.enabled,
            payload.interval_hours,
            payload.retention,
            payload.password.get_secret_value(),
        )

    @router.get("/maintenance/backups/{identifier}/download")
    def download(identifier: str):
        return FileResponse(
            management.backups.backup_file(identifier),
            media_type="application/octet-stream",
            filename="seabirds-" + identifier + ".sbbak",
        )

    @router.post("/maintenance/backups/upload")
    async def upload(request: Request):
        identifier = uuid4().hex
        path = management.backups.storage / (identifier + ".sbbak")
        total = 0
        try:
            with path.open("xb") as stream:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > 3 * 1024**3:
                        raise HTTPException(413, "O backup enviado deve ter até 3 GB.")
                    if shutil.disk_usage(path.parent).free < 128 * 1024**2:
                        raise ValueError("Espaço insuficiente para receber o backup.")
                    stream.write(chunk)
            if not total:
                raise ValueError("Selecione um arquivo de backup.")
            path.chmod(0o600)
            return await run_in_threadpool(management.backups.register_upload, identifier)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @router.get("/text-review/settings")
    def review_settings():
        return management.review.status()

    @router.post("/text-review/settings")
    def configure_review(payload: TextSettingsInput):
        data = payload.model_dump()
        data["api_key"] = payload.api_key.get_secret_value()
        if any(len(word) > 100 or "\n" in word for word in payload.ignored_words):
            raise ValueError("Cada termo do dicionário deve ter até 100 caracteres.")
        return management.review.configure(data)

    @router.post("/site/documents/prepare")
    def prepare_document(payload: PrepareDocumentInput):
        return management.flow.prepare(
            payload.root,
            payload.title,
            payload.category,
            payload.description,
            payload.cover,
            payload.template,
        )

    @router.post("/site/documents/source")
    def read_source(payload: PageInput):
        return management.flow.read(payload.root, payload.path)

    return router
