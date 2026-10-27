"""Catálogo de imagens com movimentação e lixeira recuperável."""

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from PIL import Image


class ImageStore:
    def __init__(self, data_dir):
        self.directory = Path(data_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.catalog = self.directory / "image-catalog.json"
        self.lock = threading.RLock()
        self.entries = (
            json.loads(self.catalog.read_text(encoding="utf-8")) if self.catalog.exists() else {}
        )
        for entry in self.entries.values():
            if entry.get("trashed") and entry.get("trash_path"):
                entry["trash_path"] = str(
                    self.directory / "image-trash" / Path(entry["trash_path"]).name
                )

    def save(self):
        descriptor, temporary = tempfile.mkstemp(prefix=".images-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.entries, stream, ensure_ascii=False)
            os.replace(temporary, self.catalog)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def describe(self, entry):
        path = Path(entry["trash_path"] if entry.get("trashed") else entry["path"])
        return {key: entry[key] for key in ("id", "path", "filename", "web_path")} | {
            "trashed": bool(entry.get("trashed")),
            "missing": not path.is_file(),
            "thumbnail": f"/api/generator/image/{entry['id']}",
        }

    def add(self, path, web_path):
        path = Path(path).resolve()
        with self.lock:
            for entry in self.entries.values():
                if entry["path"] == str(path) and not entry.get("trashed"):
                    entry["digest"] = self.digest(path)
                    self.save()
                    return self.describe(entry)
            entry = {
                "id": uuid4().hex,
                "path": str(path),
                "filename": path.name,
                "web_path": web_path,
                "digest": self.digest(path),
                "trashed": False,
            }
            self.entries[entry["id"]] = entry
            self.save()
            return self.describe(entry)

    def get(self, identifier):
        entry = self.entries.get(identifier)
        if not entry:
            raise ValueError("Imagem não encontrada no catálogo.")
        return entry

    def image_path(self, identifier):
        entry = self.get(identifier)
        return Path(entry["trash_path"] if entry.get("trashed") else entry["path"])

    def list_ids(self, identifiers):
        return [
            self.describe(self.entries[key])
            for key in dict.fromkeys(identifiers)
            if key in self.entries
        ]

    def import_folder(self, directory, web_path, names=None):
        directory = Path(directory).expanduser().resolve()
        if not directory.is_dir():
            raise ValueError("Pasta de imagens não encontrada.")
        paths = (
            [directory / name for name in names]
            if names is not None
            else sorted(directory.iterdir())
        )
        result = []
        for candidate in paths:
            path = candidate.resolve()
            if (
                not path.is_relative_to(directory)
                or not path.is_file()
                or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
            ):
                continue
            if path.stat().st_size > 10 * 1024 * 1024:
                continue
            try:
                with Image.open(path) as image:
                    if image.width * image.height > 25_000_000:
                        continue
                    image.verify()
                result.append(self.add(path, web_path.rstrip("/") + "/" + path.name))
            except (OSError, ValueError, Image.DecompressionBombError):
                continue
            if len(result) >= 1000:
                break
        return result

    def check_file(self, entry):
        path = Path(entry["path"])
        if not path.is_file():
            raise ValueError("O arquivo da imagem não existe mais.")
        if self.digest(path) != entry["digest"]:
            raise ValueError("O arquivo mudou no disco. Atualize o catálogo antes de movê-lo.")
        return path

    @staticmethod
    def free_path(directory, name):
        path = directory / name
        number = (
            int(re.search(r"(\d+)$", path.stem)[1]) + 1 if re.search(r"(\d+)$", path.stem) else 1
        )
        prefix = (
            re.sub(r"\d+$", "", path.stem) if re.search(r"\d+$", path.stem) else path.stem + "-"
        )
        while path.exists():
            path = directory / f"{prefix}{number}{path.suffix}"
            number += 1
        return path

    def move(self, identifier, directory, web_path):
        with self.lock:
            entry = self.get(identifier)
            if entry.get("trashed"):
                raise ValueError("Restaure a imagem da lixeira antes de mover.")
            original = self.check_file(entry)
            directory = Path(directory).expanduser().resolve()
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / original.name
            if target != original:
                target = self.free_path(directory, original.name)
                self.relocate(original, target, entry["digest"])
            entry.update(
                path=str(target),
                filename=target.name,
                web_path=web_path.rstrip("/") + "/" + target.name,
            )
            self.save()
            return self.describe(entry)

    def trash(self, identifier):
        with self.lock:
            entry = self.get(identifier)
            if not entry.get("trashed"):
                original = self.check_file(entry)
                destination = (
                    self.directory / "image-trash" / f"{identifier}-{uuid4().hex}{original.suffix}"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                self.relocate(original, destination, entry["digest"])
                entry.update(trashed=True, trash_path=str(destination))
                self.save()
            return self.describe(entry)

    def restore(self, identifier):
        with self.lock:
            entry = self.get(identifier)
            if entry.get("trashed"):
                original = Path(entry["path"])
                original.parent.mkdir(parents=True, exist_ok=True)
                destination = self.free_path(original.parent, original.name)
                self.relocate(Path(entry["trash_path"]), destination, entry["digest"])
                prefix = entry["web_path"].rsplit("/", 1)[0]
                entry.update(
                    trashed=False,
                    path=str(destination),
                    filename=destination.name,
                    web_path=prefix + "/" + destination.name,
                )
                entry.pop("trash_path", None)
                self.save()
            return self.describe(entry)

    def delete(self, identifier):
        with self.lock:
            entry = self.get(identifier)
            if not entry.get("trashed"):
                raise ValueError("Apenas imagens na lixeira podem ser excluídas definitivamente.")
            trash = (self.directory / "image-trash").resolve()
            path = Path(entry["trash_path"])
            if (
                not trash.is_relative_to(self.directory.resolve())
                or path.is_symlink()
                or path.resolve().parent != trash
                or not path.name.startswith(identifier + "-")
            ):
                raise ValueError("O arquivo não pertence à lixeira de imagens do aplicativo.")
            if path.exists() and self.digest(path) != entry["digest"]:
                raise ValueError("O arquivo da lixeira foi modificado. A exclusão foi cancelada.")
            path.unlink(missing_ok=True)
            del self.entries[identifier]
            try:
                self.save()
            except Exception:
                self.entries[identifier] = entry
                raise
            return {"id": identifier, "deleted": True}

    def relocate(self, original, destination, expected):
        created = False
        try:
            with original.open("rb") as source, destination.open("xb") as target:
                created = True
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            if self.digest(destination) != expected:
                raise ValueError("A imagem mudou durante a operação. O original foi preservado.")
            original.unlink()
        except Exception:
            if created:
                destination.unlink(missing_ok=True)
            raise
