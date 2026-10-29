"""Lixeira recuperável de HTML e cards, com pré-validação do lote."""

import hashlib
import html
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .filesystem import atomic_write
from .project_catalog import CatalogSource, literal
from .storage import ConflictError


def insert_card(source, card):
    probe = CatalogSource("const dadosCategorias=[{categoria:'x',projetos:[" + card["raw"] + "]}];")
    if len(probe.entries) != 1:
        raise ValueError("Cadastro da lixeira inválido.")
    category = next(
        (cat for cat in source.categories if cat["name"].casefold() == card["category"].casefold()),
        None,
    )
    if category:
        array = category["array"]
        indent = source.item_indent(array)
        rendered = indent + card["raw"].replace("\n", "\n" + indent)
        index = min(card.get("index", len(array.elements)), len(array.elements))
        if index < len(array.elements):
            offset = array.elements[index].range[0]
            edits = [(offset, offset, card["raw"] + "," + source.newline + indent)]
        else:
            edits = source.append(array, rendered)
    else:
        indent = source.item_indent(source.array)
        rendered = (
            indent
            + "{categoria: "
            + literal(html.escape(card["category"], quote=True))
            + ", projetos: ["
            + card["raw"]
            + "]}"
        )
        edits = source.append(source.array, rendered)
    text = source.text
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        text = text[:start] + replacement + text[end:]
    return CatalogSource(text)


class PageTrash:
    def __init__(self, workspace):
        self.workspace = workspace

    def catalog(self, root):
        path, page = self.workspace.catalog_options(root)
        catalog = self.workspace.catalog_editor.site_path(root, path)
        if not catalog.exists():
            return None
        if catalog.stat().st_size > 2_000_000:
            raise ValueError("Catálogo maior que 2 MB.")
        raw = catalog.read_bytes()
        return {
            "path": catalog,
            "relative": path,
            "page": page,
            "raw": raw,
            "source": CatalogSource(raw.decode("utf-8-sig")),
        }

    def remove_cards(self, root, catalog, targets):
        cards = {path: [] for path in targets}
        if not catalog:
            return cards
        source = catalog["source"]
        identifiers = []
        for entry in source.entries.values():
            try:
                target = self.workspace.catalog_editor.reference(
                    root, root / catalog["page"], entry["link"], {".html", ".htm"}, exists=False
                )[1]
            except ValueError:
                continue
            if target in targets:
                start, end = entry["node"].range
                cards[target].append(
                    {
                        "category": entry["category"]["name"],
                        "index": int(entry["id"].split(":")[1]),
                        "raw": source.text[start:end],
                        "image": entry["imagem"],
                    }
                )
                identifiers.append(entry["id"])
        for identifier in sorted(
            identifiers, key=lambda value: tuple(map(int, value.split(":"))), reverse=True
        ):
            source = CatalogSource(source.change("", {}, identifier, remove=True))
        catalog["changed"] = (
            ("\ufeff" if catalog["raw"].startswith(b"\xef\xbb\xbf") else "") + source.text
        ).encode("utf-8")
        return cards

    def write_catalog(self, catalog):
        if catalog and catalog["raw"] != catalog["changed"]:
            if catalog["path"].read_bytes() != catalog["raw"]:
                raise ConflictError("O catálogo mudou durante a operação. Atualize a lista.")
            self.workspace.files.backup(catalog["path"])
            atomic_write(catalog["path"], catalog["changed"].decode("utf-8"))

    def clear_undo(self, root, catalog):
        if catalog and catalog["raw"] != catalog["changed"]:
            self.workspace.state.setdefault("catalogs", {})[str(root)] = {
                "path": catalog["relative"],
                "page": catalog["page"],
                "backup": "",
                "version": hashlib.sha256(catalog["changed"]).hexdigest(),
            }

    def trash(self, root, selections):
        checked = {}
        for selection in selections:
            path = self.workspace.page(root, selection.path)
            if self.workspace.digest(path) != selection.version:
                raise ConflictError(
                    "Uma página mudou após a listagem. Atualize antes de excluir: " + selection.path
                )
            checked[path] = selection
        catalog = self.catalog(root)
        cards = self.remove_cards(root, catalog, checked)
        before = deepcopy(self.workspace.state)
        entries, removed, copies = [], [], []
        try:
            for path, selection in checked.items():
                identifier = uuid4().hex
                destination = self.workspace.directory / "page-trash" / (identifier + path.suffix)
                destination.parent.mkdir(parents=True, exist_ok=True)
                companion = path.with_suffix(".documentacao.json")
                if companion.exists() and (
                    companion.is_symlink() or companion.stat().st_size > 8 * 1024 * 1024
                ):
                    raise ValueError("Fonte associada inválida ou maior que 8 MB.")
                raw = path.read_bytes()
                with destination.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                copies.append((path, destination, selection.version))
                entry = {
                    "id": identifier,
                    "root": str(root),
                    "relative": selection.path,
                    "digest": selection.version,
                    "trash_file": destination.name,
                    "trashed_at": datetime.now(UTC).isoformat(),
                    "cards": cards[path],
                    "catalog_path": catalog["relative"] if catalog else "",
                    "catalog_page": catalog["page"] if catalog else "",
                    "companions": [],
                }
                if companion.is_file():
                    companion_copy = destination.parent / (identifier + ".source.json")
                    companion_digest = self.workspace.digest(companion)
                    with companion_copy.open("xb") as stream:
                        stream.write(companion.read_bytes())
                        stream.flush()
                        os.fsync(stream.fileno())
                    copies.append((companion, companion_copy, companion_digest))
                    entry["companions"].append(
                        {
                            "relative": companion.relative_to(root).as_posix(),
                            "digest": companion_digest,
                            "trash_file": companion_copy.name,
                        }
                    )
                entries.append((path, destination, entry))
            for path, destination, expected in copies:
                if (
                    self.workspace.digest(path) != expected
                    or self.workspace.digest(destination) != expected
                ):
                    raise ConflictError("Uma página mudou durante a operação. Atualize a lista.")
            self.workspace.state["trash"].extend(entry for _, _, entry in entries)
            self.workspace.persist()
            self.write_catalog(catalog)
            for path, _, _ in copies:
                path.unlink()
                removed.append(path)
            self.clear_undo(root, catalog)
            self.workspace.persist()
        except Exception:
            for path, copy, _ in copies:
                if path in removed and not path.exists():
                    with path.open("xb") as stream:
                        stream.write(copy.read_bytes())
            if (
                catalog
                and catalog.get("changed")
                and catalog["path"].read_bytes() == catalog["changed"]
            ):
                atomic_write(catalog["path"], catalog["raw"].decode("utf-8"))
            self.workspace.state.clear()
            self.workspace.state.update(before)
            self.workspace.persist()
            for _, copy, _ in copies:
                copy.unlink(missing_ok=True)
            raise
        return {
            "changed": [entry["relative"] for _, _, entry in entries],
            "trash": self.workspace.trash_entries(root),
        }

    def companions(self, root, entry):
        result = []
        records = entry.get("companions", [])
        if len(records) > 1:
            raise ValueError("Fontes da lixeira inválidas.")
        expected = Path(entry["relative"]).with_suffix(".documentacao.json").as_posix()
        for record in records:
            if (
                record["relative"] != expected
                or record["trash_file"] != entry["id"] + ".source.json"
            ):
                raise ValueError("Fonte fora da documentação selecionada.")
            target = self.workspace.catalog_editor.site_path(root, record["relative"])
            source = self.workspace.directory / "page-trash" / record["trash_file"]
            if (
                source.parent.is_symlink()
                or source.is_symlink()
                or not source.is_file()
                or self.workspace.digest(source) != record["digest"]
            ):
                raise ValueError("A fonte da lixeira foi alterada ou não existe.")
            result.append((target, source, record["digest"]))
        return result

    def restore(self, entry):
        root = self.workspace.root(entry["root"])
        destination = self.workspace.page(root, entry["relative"], require_exists=False)
        source_file = self.workspace.trash_file(entry)
        if destination.exists():
            raise ValueError("Já existe uma página neste caminho. Renomeie-a antes de restaurar.")
        companions = self.companions(root, entry)
        if any(target.exists() for target, _, _ in companions):
            raise ConflictError("Já existe uma fonte neste caminho. Ela foi preservada.")
        catalog = None
        if entry.get("cards"):
            path = self.workspace.catalog_editor.site_path(root, entry["catalog_path"])
            if not path.is_file():
                raise ValueError(
                    "Restaure o arquivo do catálogo antes de restaurar esta documentação."
                )
            raw = path.read_bytes()
            source = CatalogSource(raw.decode("utf-8-sig"))
            for item in source.entries.values():
                try:
                    linked = self.workspace.catalog_editor.reference(
                        root,
                        root / entry["catalog_page"],
                        item["link"],
                        {".html", ".htm"},
                        exists=False,
                    )[1]
                except ValueError:
                    continue
                if linked == destination.resolve():
                    raise ConflictError(
                        "O catálogo já tem um cadastro para esta página. Resolva o conflito antes de restaurar."
                    )
            for card in sorted(entry["cards"], key=lambda item: item.get("index", 0)):
                source = insert_card(source, card)
            catalog = {
                "path": path,
                "relative": entry["catalog_path"],
                "page": entry["catalog_page"],
                "raw": raw,
                "changed": (
                    ("\ufeff" if raw.startswith(b"\xef\xbb\xbf") else "") + source.text
                ).encode("utf-8"),
            }
        before = deepcopy(self.workspace.state)
        destination.parent.mkdir(parents=True, exist_ok=True)
        created = []
        try:
            for target, source, _ in [(destination, source_file, entry["digest"]), *companions]:
                with target.open("xb") as stream:
                    stream.write(source.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
                created.append(target)
            self.write_catalog(catalog)
            self.workspace.state["trash"].remove(entry)
            self.clear_undo(root, catalog)
            self.workspace.persist()
        except Exception:
            for target in created:
                target.unlink()
            if catalog and catalog["path"].read_bytes() == catalog["changed"]:
                atomic_write(catalog["path"], catalog["raw"].decode("utf-8"))
            self.workspace.state.clear()
            self.workspace.state.update(before)
            self.workspace.persist()
            raise
        source_file.unlink()
        for _, source, _ in companions:
            source.unlink()
        return {"root": str(root), "path": entry["relative"]}
