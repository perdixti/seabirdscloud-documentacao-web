"""Backup completo em arquivo cifrado, com manifesto e restauração revisada."""

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .filesystem import atomic_write, local_path
from .operations import progress
from .storage import ConflictError

MAGIC = b"SEABIRDS-BACKUP-1\n"
EXCLUDED = {
    "backups",
    "operations.sqlite3",
    "operations.sqlite3-wal",
    "operations.sqlite3-shm",
    "backup-catalog.json",
    "restore-in-progress.json",
}


class ActivityGate:
    def __init__(self):
        self.condition = threading.Condition()
        self.active = 0
        self.busy = False

    def enter(self):
        with self.condition:
            if self.busy:
                return False
            self.active += 1
            return True

    def leave(self):
        with self.condition:
            self.active -= 1
            self.condition.notify_all()

    @contextmanager
    def exclusive(self):
        with self.condition:
            if self.busy:
                raise ValueError("Outra operação de recuperação está em andamento.")
            self.busy = True
            deadline = time.monotonic() + 30
            while self.active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.busy = False
                    raise ValueError(
                        "Há operações em andamento. Aguarde antes de criar ou restaurar o backup."
                    )
                self.condition.wait(remaining)
        try:
            yield
        finally:
            with self.condition:
                self.busy = False
                self.condition.notify_all()


@contextmanager
def database_connection(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(128 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def key(password, salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000).derive(
        password.encode()
    )


def encrypt(source, destination, password):
    salt, iv = os.urandom(16), os.urandom(12)
    header = (
        json.dumps(
            {"salt": base64.b64encode(salt).decode(), "iv": base64.b64encode(iv).decode()}
        ).encode()
        + b"\n"
    )
    cipher = Cipher(algorithms.AES(key(password, salt)), modes.GCM(iv)).encryptor()
    cipher.authenticate_additional_data(MAGIC + header)
    with source.open("rb") as old, destination.open("xb") as new:
        new.write(MAGIC + header)
        for block in iter(lambda: old.read(128 * 1024), b""):
            new.write(cipher.update(block))
        new.write(cipher.finalize() + cipher.tag)
        new.flush()
        os.fsync(new.fileno())
    destination.chmod(0o600)


def decrypt(source, destination, password):
    try:
        with source.open("rb") as old:
            if old.readline(100) != MAGIC:
                raise ValueError("Selecione um backup completo .sbbak.")
            header = old.readline(4096)
            info = json.loads(header)
            start = old.tell()
            old.seek(-16, 2)
            tag = old.read(16)
            remaining = source.stat().st_size - start - 16
            cipher = Cipher(
                algorithms.AES(key(password, base64.b64decode(info["salt"], validate=True))),
                modes.GCM(base64.b64decode(info["iv"], validate=True), tag),
            ).decryptor()
            cipher.authenticate_additional_data(MAGIC + header)
            old.seek(start)
            with destination.open("wb") as new:
                while remaining > 0:
                    block = old.read(min(128 * 1024, remaining))
                    if not block:
                        raise ValueError("Backup incompleto.")
                    remaining -= len(block)
                    new.write(cipher.update(block))
                new.write(cipher.finalize())
    except Exception:
        destination.unlink(missing_ok=True)
        raise ValueError(
            "Não foi possível abrir o backup. Confira a senha e a integridade do arquivo."
        ) from None


def remap(value, mappings):
    if isinstance(value, dict):
        return {remap(k, mappings): remap(v, mappings) for k, v in value.items()}
    if isinstance(value, list):
        return [remap(v, mappings) for v in value]
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        for old, new in sorted(mappings.items(), key=lambda item: len(item[0]), reverse=True):
            old = old.replace("\\", "/").rstrip("/")
            compare = normalized.casefold() if len(old) > 1 and old[1] == ":" else normalized
            prefix = old.casefold() if len(old) > 1 and old[1] == ":" else old
            if compare == prefix or compare.startswith(prefix + "/"):
                return new.rstrip("/\\") + normalized[len(old) :]
    return value


class Backups:
    def __init__(self, settings, workspace, store, gate, reload_services):
        self.settings, self.workspace, self.store = settings, workspace, store
        self.gate, self.reload_services = gate, reload_services
        self.directory = settings.data_dir
        self.storage = self.directory / "backups"
        self.storage.mkdir(exist_ok=True, mode=0o700)
        self.config_path = self.directory / "backup-settings.json"
        self.key_path = self.directory / "secrets/backup-master.key"
        self.catalog_path = self.directory / "backup-catalog.json"
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.plans = {}
        self.restore_marker = self.directory / "restore-in-progress.json"

    def config(self):
        return (
            json.loads(self.config_path.read_text(encoding="utf-8"))
            if self.config_path.exists()
            else {"enabled": False, "interval_hours": 24, "retention": 7}
        )

    def password(self):
        try:
            return (
                Fernet(self.key_path.read_bytes())
                .decrypt(self.config()["password"].encode())
                .decode()
            )
        except Exception:
            return ""

    def status(self):
        config = self.config()
        return {k: v for k, v in config.items() if k != "password"} | {
            "interrupted_restore": json.loads(self.restore_marker.read_text(encoding="utf-8"))
            if self.restore_marker.exists()
            else None,
            "password_configured": bool(self.password()),
            "site_roots": [item["path"] for item in self.workspace.state["roots"]],
        }

    def configure(self, enabled, interval_hours, retention, password=""):
        config = self.config()
        if password:
            if not 12 <= len(password) <= 1024:
                raise ValueError("Use uma senha de backup com 12 a 1024 caracteres.")
            self.key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                cipher = Fernet(self.key_path.read_bytes())
            except (OSError, ValueError):
                raw = Fernet.generate_key()
                atomic_write(self.key_path, raw.decode())
                self.key_path.chmod(0o600)
                cipher = Fernet(raw)
            config["password"] = cipher.encrypt(password.encode()).decode()
        if not config.get("password"):
            raise ValueError("Defina a senha que será usada para abrir os backups.")
        config.update(
            enabled=enabled,
            interval_hours=interval_hours,
            retention=retention,
            next_at=(datetime.now(UTC) + timedelta(hours=interval_hours)).isoformat(),
        )
        atomic_write(self.config_path, json.dumps(config))
        self.config_path.chmod(0o600)
        return self.status()

    def records(self):
        return (
            json.loads(self.catalog_path.read_text(encoding="utf-8"))
            if self.catalog_path.exists()
            else []
        )

    def list(self):
        return [
            record
            for record in self.records()
            if (self.storage / (record["id"] + ".sbbak")).is_file()
        ]

    def backup_file(self, identifier):
        if (
            not identifier
            or len(identifier) != 32
            or any(char not in "0123456789abcdef" for char in identifier)
        ):
            raise ValueError("Backup não encontrado.")
        path = self.storage / (identifier + ".sbbak")
        if path.is_symlink() or not path.is_file():
            raise ValueError("Backup não encontrado.")
        return path

    def register_upload(self, identifier):
        with self.lock:
            path = self.backup_file(identifier)
            with path.open("rb") as stream:
                valid = stream.readline(100) == MAGIC
            if not valid:
                path.unlink()
                raise ValueError("Selecione um arquivo de backup .sbbak válido.")
            record = {
                "id": identifier,
                "created_at": datetime.now(UTC).isoformat(),
                "version": "a conferir",
                "size": path.stat().st_size,
                "sites": 0,
                "scheduled": False,
                "recovery": False,
                "imported": True,
                "sha256": digest(path),
            }
            atomic_write(self.catalog_path, json.dumps(self.records() + [record]))
            return {"identifier": identifier, "size": path.stat().st_size}

    def inventory(self, root, prefix):
        result = []
        for parent, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [
                name
                for name in dirs
                if name
                not in {".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}
                and not (
                    prefix == "data" and (name == "backups" or name.startswith(".page-delete-"))
                )
            ]
            for name in dirs + names:
                if (Path(parent) / name).is_symlink():
                    raise ValueError(
                        "O backup encontrou um link simbólico. Use uma cópia normal dos arquivos: "
                        + str(Path(parent) / name)
                    )
            for name in names:
                path = Path(parent) / name
                relative = path.relative_to(root)
                if prefix == "data" and (
                    relative.parts[0] in EXCLUDED
                    or name.endswith(("-wal", "-shm"))
                    or path == self.store.path
                ):
                    continue
                if path.is_file():
                    result.append((path, prefix + "/" + relative.as_posix()))
        return result

    def create(self, scheduled=False, password_override="", recovery=False):
        password = password_override or self.password()
        if not password:
            raise ValueError("Configure a senha de backup pela interface antes de continuar.")
        with self.lock, self.gate.exclusive():
            return self._create(password, scheduled, recovery)

    def _create(self, password, scheduled=False, recovery=False):
        from . import __version__

        identifier = uuid4().hex
        roots, missing = [], []
        for item in self.workspace.state["roots"]:
            if recovery and not Path(item["path"]).is_dir():
                missing.append(item["path"])
                continue
            roots.append(self.workspace.root(item["path"]))
        manifest = {
            "format": 1,
            "version": __version__,
            "created_at": datetime.now(UTC).isoformat(),
            "source_data": str(self.directory),
            "sites": [
                {"id": str(index), "root": str(root), "name": root.name}
                for index, root in enumerate(roots)
            ],
            "files": {},
            "missing_sites": missing,
        }
        inventory = self.inventory(self.directory, "data")
        for index, root in enumerate(roots):
            if (
                self.directory.is_relative_to(root)
                or root.is_relative_to(self.directory)
                or any(root != other and root.is_relative_to(other) for other in roots)
            ):
                raise ValueError(
                    "As pastas de dados e sites não podem estar sobrepostas para o backup completo."
                )
            inventory += self.inventory(root, "sites/" + str(index))
        if (
            len(inventory) > 50000
            or sum(path.stat().st_size for path, _ in inventory) > 2 * 1024**3
        ):
            raise ValueError("Backup limitado a 50 mil arquivos/2 GB para manter o servidor leve.")
        with tempfile.TemporaryDirectory(prefix="backup-", dir=self.storage) as staging:
            staging = Path(staging)
            snapshot = staging / "seabirds.sqlite3"
            with self.store.connection() as source, database_connection(snapshot) as target:
                source.backup(target)
            inventory.append((snapshot, "data/seabirds.sqlite3"))
            package = staging / "backup.zip"
            with ZipFile(package, "w", ZIP_DEFLATED, compresslevel=1) as archive:
                for index, (path, name) in enumerate(inventory):
                    progress(
                        "Copiando para backup: " + name,
                        5 + int(index / max(len(inventory), 1) * 75),
                    )
                    before = digest(path)
                    archive.write(path, name)
                    if digest(path) != before:
                        raise ConflictError(
                            "Um arquivo mudou durante o backup. Tente novamente: " + name
                        )
                    manifest["files"][name] = before
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
            progress("Protegendo o backup com senha", 85)
            target = self.storage / (identifier + ".sbbak")
            try:
                encrypt(package, target, password)
            except Exception:
                target.unlink(missing_ok=True)
                raise
        record = {
            "id": identifier,
            "created_at": manifest["created_at"],
            "version": __version__,
            "size": target.stat().st_size,
            "sites": len(roots),
            "scheduled": scheduled,
            "recovery": recovery,
            "sha256": digest(target),
        }
        records = self.records() + [record]
        if scheduled:
            config = self.config()
            config.update(
                last_at=record["created_at"],
                next_at=(datetime.now(UTC) + timedelta(hours=config["interval_hours"])).isoformat(),
            )
            atomic_write(self.config_path, json.dumps(config))
            old = [item for item in records if item.get("scheduled") and not item.get("recovery")][
                : -config["retention"]
            ]
            for item in old:
                self.backup_file(item["id"]).unlink()
            records = [item for item in records if item not in old]
        atomic_write(self.catalog_path, json.dumps(records))
        return record

    @contextmanager
    def opened(self, identifier, password):
        source = self.backup_file(identifier)
        with tempfile.TemporaryDirectory(prefix="restore-", dir=self.storage) as temporary:
            package = Path(temporary) / "backup.zip"
            decrypt(source, package, password)
            with ZipFile(package) as archive:
                names = archive.namelist()
                if (
                    len(names) > 50001
                    or len(set(names)) != len(names)
                    or "manifest.json" not in names
                ):
                    raise ValueError("Manifesto de backup inválido.")
                total = 0
                for item in archive.infolist():
                    path = PurePosixPath(item.filename)
                    total += item.file_size
                    if (
                        path.is_absolute()
                        or path.as_posix() != item.filename
                        or ".." in path.parts
                        or "\\" in item.filename
                        or ":" in item.filename
                        or ((item.external_attr >> 16) & 0o170000) == 0o120000
                        or total > 2 * 1024**3
                    ):
                        raise ValueError("Backup contém caminhos ou tamanhos inválidos.")
                if archive.getinfo("manifest.json").file_size > 20 * 1024**2:
                    raise ValueError("Manifesto maior que 20 MB.")
                manifest = json.loads(archive.read("manifest.json"))
                if (
                    not isinstance(manifest.get("sites"), list)
                    or len(manifest["sites"]) > 30
                    or not isinstance(manifest.get("source_data"), str)
                ):
                    raise ValueError("A lista de sites do backup é inválida.")
                identifiers = [site.get("id") for site in manifest["sites"]]
                if any(
                    not isinstance(value, str) or not value.isdigit() for value in identifiers
                ) or len(set(identifiers)) != len(identifiers):
                    raise ValueError("Identificadores de site inválidos no backup.")
                if "data/seabirds.sqlite3" not in manifest.get("files", {}):
                    raise ValueError("Banco de dados ausente no backup.")
                if manifest.get("format") != 1 or set(names) != set(manifest["files"]) | {
                    "manifest.json"
                }:
                    raise ValueError("Manifesto e conteúdo do backup não correspondem.")
                for name, expected in manifest["files"].items():
                    result = hashlib.sha256()
                    with archive.open(name) as stream:
                        for block in iter(lambda: stream.read(128 * 1024), b""):
                            result.update(block)
                    if result.hexdigest() != expected:
                        raise ValueError("Arquivo do backup corrompido: " + name)
                yield archive, manifest, Path(temporary)

    def targets(self, manifest, requested):
        result = {}
        for site in manifest["sites"]:
            value = requested.get(site["id"], site["root"])
            path = local_path(value)
            if (
                path == Path(path.anchor)
                or path
                in {Path.home().resolve(), self.directory, Path(__file__).resolve().parent.parent}
                or path.is_relative_to(self.directory)
                or self.directory.is_relative_to(path)
            ):
                raise ValueError("Escolha pastas próprias para os sites restaurados.")
            if path.exists() and (not path.is_dir() or path.is_symlink()):
                raise ValueError("Destino de restauração inválido.")
            result[site["id"]] = path
        if any(
            a != b and (a.is_relative_to(b) or b.is_relative_to(a))
            for a in result.values()
            for b in result.values()
        ) or len(set(result.values())) != len(result):
            raise ValueError("Os destinos dos sites não podem se sobrepor.")
        return result

    def preview(self, identifier, password, requested):
        with self.lock, self.opened(identifier, password) as (_, manifest, _):
            targets = self.targets(manifest, requested)
            token = uuid4().hex
            plan = {
                "id": identifier,
                "sha256": digest(self.backup_file(identifier)),
                "targets": {k: str(v) for k, v in targets.items()},
                "expires": time.monotonic() + 900,
            }
            self.plans = {
                key: value
                for key, value in self.plans.items()
                if value["expires"] > time.monotonic()
            }
            self.plans[token] = plan
            return {
                "token": token,
                "version": manifest["version"],
                "created_at": manifest["created_at"],
                "files": len(manifest["files"]),
                "sites": [
                    {**site, "target": str(targets[site["id"]])} for site in manifest["sites"]
                ],
                "message": "Os arquivos presentes no backup serão restaurados. Arquivos adicionais do site serão preservados. Uma cópia de segurança do estado atual será criada antes da restauração.",
            }

    def restore(self, token, password):
        with self.lock, self.gate.exclusive():
            plan = self.plans.get(token)
            if (
                not plan
                or plan["expires"] < time.monotonic()
                or digest(self.backup_file(plan["id"])) != plan["sha256"]
            ):
                raise ValueError("A revisão expirou ou o arquivo mudou. Revise novamente.")
            with self.opened(plan["id"], password) as (archive, manifest, temporary):
                targets = self.targets(manifest, plan["targets"])
                mappings = {manifest["source_data"]: str(self.directory)} | {
                    site["root"]: str(targets[site["id"]]) for site in manifest["sites"]
                }
                recovery = self._create(self.password() or password, recovery=True)
                progress("Preparando restauração", 20)
                rollback, changed = temporary / "rollback", []
                rollback.mkdir()
                db_before = temporary / "before.sqlite3"
                with self.store.connection() as source, database_connection(db_before) as target:
                    source.backup(target)
                atomic_write(
                    self.restore_marker,
                    json.dumps(
                        {
                            "recovery_backup": recovery["id"],
                            "started_at": datetime.now(UTC).isoformat(),
                        }
                    ),
                )
                try:
                    for index, name in enumerate(manifest["files"]):
                        parts = PurePosixPath(name).parts
                        if parts[0] == "data":
                            if (
                                len(parts) < 2
                                or parts[1] in EXCLUDED
                                or parts[1] == "seabirds.sqlite3"
                            ):
                                continue
                            destination = self.directory.joinpath(*parts[1:])
                            allowed = self.directory
                        elif len(parts) > 2 and parts[0] == "sites" and parts[1] in targets:
                            allowed = targets[parts[1]]
                            destination = allowed.joinpath(*parts[2:])
                        else:
                            raise ValueError("Arquivo fora do escopo do backup.")
                        if not destination.resolve().is_relative_to(allowed.resolve()) or any(
                            parent.is_symlink()
                            for parent in [destination, *destination.parents]
                            if parent != allowed.parent
                        ):
                            raise ValueError(
                                "Destino com link simbólico ou fora da pasta autorizada."
                            )
                        previous = rollback / str(index)
                        exists = destination.is_file()
                        if exists:
                            shutil.copy2(destination, previous)
                        elif destination.exists():
                            raise ValueError("Uma pasta ocupa o lugar de um arquivo do backup.")
                        changed.append((destination, previous, exists))
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if name.endswith(".json") and parts[0] == "data":
                            if archive.getinfo(name).file_size > 10 * 1024**2:
                                raise ValueError("Uma configuração JSON excede o limite de 10 MB.")
                            content = remap(json.loads(archive.read(name)), mappings)
                            if name == "data/backup-settings.json":
                                content["enabled"] = False
                            atomic_write(destination, json.dumps(content, ensure_ascii=False))
                        else:
                            with archive.open(name) as source, destination.open("wb") as target:
                                shutil.copyfileobj(source, target, 128 * 1024)
                            if os.name == "posix":
                                mode = (archive.getinfo(name).external_attr >> 16) & 0o777
                                destination.chmod(
                                    0o600 if parts[:2] == ("data", "secrets") else (mode or 0o600)
                                )
                        progress(
                            "Restaurando: " + name, 25 + int(index / len(manifest["files"]) * 60)
                        )
                    database = temporary / "database.sqlite3"
                    with (
                        archive.open("data/seabirds.sqlite3") as source,
                        database.open("wb") as target,
                    ):
                        shutil.copyfileobj(source, target)
                    with database_connection(database) as db:
                        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise ValueError("Banco de dados inválido no backup.")
                        for table in ["documents", "revisions"]:
                            for row in db.execute(
                                f"SELECT rowid,generation FROM {table}"
                            ).fetchall():
                                db.execute(
                                    f"UPDATE {table} SET generation=? WHERE rowid=?",
                                    (json.dumps(remap(json.loads(row[1]), mappings)), row[0]),
                                )
                    with database_connection(database) as source, self.store.connection() as target:
                        source.backup(target)
                    self.reload_services()
                except Exception:
                    for destination, previous, existed in reversed(changed):
                        if existed:
                            shutil.copy2(previous, destination)
                        else:
                            destination.unlink(missing_ok=True)
                    with (
                        database_connection(db_before) as source,
                        self.store.connection() as target,
                    ):
                        source.backup(target)
                    self.reload_services()
                    self.restore_marker.unlink(missing_ok=True)
                    raise
                self.restore_marker.unlink(missing_ok=True)
                self.plans.pop(token, None)
                return {
                    "restored": True,
                    "sites": [str(path) for path in targets.values()],
                    "recovery_backup": recovery["id"],
                    "message": "Dados restaurados. O agendamento de backup foi pausado para conferência. A autenticação e os serviços do servidor atual foram preservados.",
                }

    def schedule(self, jobs):
        def loop():
            while not self.stop.wait(60):
                try:
                    config = self.config()
                    if (
                        config.get("enabled")
                        and config.get("next_at", "") <= datetime.now(UTC).isoformat()
                    ):
                        job = jobs.start(
                            "backup.create", {"scheduled": True}, "scheduled-" + config["next_at"]
                        )
                        if job["status"] in {"failed", "interrupted"}:
                            config.update(
                                last_error=job["error"] or job["step"],
                                next_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                            )
                            atomic_write(self.config_path, json.dumps(config))
                except Exception:
                    # A falha aparece no painel de operações; o processo web continua.
                    pass

        thread = threading.Thread(target=loop, name="seabirds-backups", daemon=True)
        thread.start()
