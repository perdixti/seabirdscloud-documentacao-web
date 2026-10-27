"""SQLite com transações e controle de concorrência por versão."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import DocumentInput


class ConflictError(Exception):
    pass


class Store:
    def __init__(self, directory: Path, history_limit: int = 50):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "seabirds.sqlite3"
        self.history_limit = history_limit
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, markdown TEXT NOT NULL,
                    template TEXT NOT NULL, options TEXT NOT NULL,
                    version INTEGER NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    title TEXT NOT NULL, markdown TEXT NOT NULL, template TEXT NOT NULL,
                    options TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS revisions_document ON revisions(document_id, id);
            """)
            for table in ("documents", "revisions"):
                columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                if "generation" not in columns:
                    db.execute(
                        f"ALTER TABLE {table} ADD COLUMN generation TEXT NOT NULL DEFAULT '{{}}'"
                    )
            db.execute("PRAGMA user_version=2")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row):
        if row is None:
            return None
        result = dict(row)
        if "options" in result:
            result["options"] = json.loads(result["options"])
        if "generation" in result:
            result["generation"] = json.loads(result["generation"])
        return result

    def list(self):
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id, title, version, updated_at FROM documents ORDER BY updated_at DESC"
                )
            ]

    def get(self, document_id):
        with self.connection() as db:
            return self.decode(
                db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            )

    def save(self, document: DocumentInput, document_id=None):
        now = datetime.now(UTC).isoformat()
        options = json.dumps(document.options.model_dump(), sort_keys=True)
        generation = json.dumps(document.generation.model_dump(), sort_keys=True)
        values = (document.title, document.markdown, document.template, options, generation)
        with self.connection() as db:
            # Serialize read/check/write so two tabs cannot silently overwrite each other.
            db.execute("BEGIN IMMEDIATE")
            if document_id:
                old = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
                if old is None:
                    raise KeyError(document_id)
                if old["version"] != document.version:
                    raise ConflictError(
                        "Este documento foi alterado em outra aba. Reabra-o antes de salvar."
                    )
                if (
                    tuple(
                        old[key]
                        for key in ("title", "markdown", "template", "options", "generation")
                    )
                    == values
                ):
                    return self.decode(old)
                version = old["version"] + 1
                db.execute(
                    "UPDATE documents SET title=?,markdown=?,template=?,options=?,generation=?,version=?,updated_at=? WHERE id=?",
                    (*values, version, now, document_id),
                )
            else:
                document_id, version = uuid4().hex, 1
                db.execute(
                    "INSERT INTO documents(id,title,markdown,template,options,generation,version,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (document_id, *values, version, now),
                )
            db.execute(
                "INSERT INTO revisions(document_id,title,markdown,template,options,generation,version,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (document_id, *values, version, now),
            )
            db.execute(
                "DELETE FROM revisions WHERE document_id=? AND id NOT IN "
                "(SELECT id FROM revisions WHERE document_id=? ORDER BY id DESC LIMIT ?)",
                (
                    document_id,
                    document_id,
                    document.generation.history_limit
                    if "history_limit" in document.generation.model_fields_set
                    else self.history_limit,
                ),
            )
            return self.decode(
                db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            )

    def history(self, document_id):
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id, title, version, created_at FROM revisions WHERE document_id=? ORDER BY id DESC",
                    (document_id,),
                )
            ]

    def revision(self, document_id, revision_id):
        with self.connection() as db:
            return self.decode(
                db.execute(
                    "SELECT * FROM revisions WHERE document_id=? AND id=?",
                    (document_id, revision_id),
                ).fetchone()
            )
