import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from seabirds.models import DocumentInput
from seabirds.storage import ConflictError, Store


def test_history_retention_and_deduplication(tmp_path):
    store = Store(tmp_path, history_limit=3)
    saved = store.save(DocumentInput(title="Documento"))
    doc_id = saved["id"]
    same = store.save(DocumentInput(title="Documento", version=1), doc_id)
    assert same["version"] == 1
    for version in range(1, 7):
        saved = store.save(DocumentInput(title=f"Versão {version}", version=version), doc_id)
    assert saved["version"] == 7
    assert [row["version"] for row in store.history(doc_id)] == [7, 6, 5]
    assert Store(tmp_path).get(doc_id)["title"] == "Versão 6"


def test_concurrent_updates_have_one_winner(tmp_path):
    store = Store(tmp_path)
    saved = store.save(DocumentInput(title="Base"))

    def update(title):
        try:
            store.save(DocumentInput(title=title, version=1), saved["id"])
            return "ok"
        except ConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, ["A", "B"])) == ["conflict", "ok"]


def test_missing_document_and_bound_parameters(tmp_path):
    store = Store(tmp_path)
    assert store.get("' OR 1=1 --") is None
    with pytest.raises(KeyError):
        store.save(DocumentInput(), "missing")
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
