"""Operações acompanháveis; resultados sobrevivem ao navegador e ao serviço."""

import hashlib
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

_context = threading.local()


def progress(step, percent=None):
    if getattr(_context, "deadline", float("inf")) < time.monotonic():
        raise ValueError(
            "A operação excedeu o tempo permitido. Consulte os arquivos e o painel antes de repetir."
        )
    report = getattr(_context, "report", None)
    if report:
        report(step, percent)


class Operations:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "operations.sqlite3"
        self.handlers = {}
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="seabirds")
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT, request_id TEXT UNIQUE, fingerprint TEXT, status TEXT, step TEXT, percent INTEGER, result TEXT, error TEXT, created_at TEXT, updated_at TEXT)"
            )
            db.execute(
                "UPDATE jobs SET status='interrupted',step='O servidor reiniciou. Confira o resultado nos arquivos antes de repetir.',updated_at=? WHERE status IN ('queued','running')",
                (self.now(),),
            )

    @staticmethod
    def now():
        return datetime.now(UTC).isoformat()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, kind, handler):
        self.handlers[kind] = handler

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise ValueError("Operação não encontrada.")
        data = dict(row)
        data.pop("fingerprint", None)
        data.pop("request_id", None)
        data["result"] = json.loads(data["result"]) if data["result"] else None
        return data

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT id FROM jobs ORDER BY created_at DESC LIMIT 50").fetchall()
        return [
            {key: value for key, value in self.get(row["id"]).items() if key != "result"}
            for row in rows
        ]

    def start(self, kind, payload, request_id):
        if kind not in self.handlers:
            raise ValueError("Operação não disponível.")
        fingerprint = hashlib.sha256(
            (kind + json.dumps(payload, sort_keys=True)).encode()
        ).hexdigest()
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id,fingerprint FROM jobs WHERE request_id=? OR (fingerprint=? AND status IN ('queued','running')) ORDER BY created_at DESC LIMIT 1",
                (request_id, fingerprint),
            ).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise ValueError("Este identificador já foi usado para outra operação.")
                return self.get(existing["id"])
            identifier = uuid4().hex
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    kind,
                    request_id,
                    fingerprint,
                    "queued",
                    "Na fila",
                    0,
                    None,
                    None,
                    self.now(),
                    self.now(),
                ),
            )
        self.executor.submit(self.run, identifier, kind, payload)
        with self.connect() as db:
            db.execute(
                "DELETE FROM jobs WHERE status NOT IN ('queued','running') AND id NOT IN (SELECT id FROM jobs ORDER BY created_at DESC LIMIT 500)"
            )
        return self.get(identifier)

    def update(self, identifier, step, percent=None):
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET step=?,percent=MAX(percent,?),updated_at=? WHERE id=?",
                (step[:300], percent or 0, self.now(), identifier),
            )

    def run(self, identifier, kind, payload):
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET status='running',step='Iniciando',updated_at=? WHERE id=?",
                (self.now(), identifier),
            )
        _context.report = lambda step, percent=None: self.update(identifier, step, percent)
        _context.deadline = time.monotonic() + 600
        try:
            result = self.handlers[kind](payload)
            with self.connect() as db:
                db.execute(
                    "UPDATE jobs SET status='succeeded',step='Concluída',percent=100,result=?,updated_at=? WHERE id=?",
                    (json.dumps(result, ensure_ascii=False), self.now(), identifier),
                )
        except Exception as exc:
            # As integrações tratam mensagens e segredos antes de entregar o erro.
            message = (
                str(exc)
                if isinstance(exc, (ValueError, OSError)) or type(exc).__name__ == "ConflictError"
                else "Falha na operação. Consulte o diagnóstico e tente novamente."
            )
            with self.connect() as db:
                db.execute(
                    "UPDATE jobs SET status='failed',step='Falhou',error=?,updated_at=? WHERE id=?",
                    (message[:1500], self.now(), identifier),
                )
        finally:
            _context.report = None
            _context.deadline = float("inf")

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
