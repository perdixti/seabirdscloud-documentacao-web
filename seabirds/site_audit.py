"""Valida referências locais sem consultar URLs externas nem executar scripts."""

import os
from html.parser import HTMLParser
from itertools import islice
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .operations import progress
from .page_deletion import CSS_URL, PageDeletion
from .project_catalog import CatalogSource


class References(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.refs, self.base = [], ""
        self.limited = False
        self.feed(text)
        for match in islice(CSS_URL.finditer(text), 5001):
            self.add(match.group(1), "recurso")

    def add(self, value, kind):
        if value.startswith(("data:", "http:", "https:", "mailto:", "javascript:")):
            return
        if len(self.refs) >= 5000 or len(value) > 8192:
            self.limited = True
            return
        self.refs.append((value, kind))

    def handle_starttag(self, tag, attributes):
        if len(self.refs) >= 5000:
            self.limited = True
            return
        attrs = dict(attributes)
        if tag == "base":
            self.base = attrs.get("href", "")
        for key in ["href", "src", "poster", "data-src"]:
            if attrs.get(key) and tag != "base":
                self.add(attrs[key], "link" if tag == "a" else "recurso")
        for key in ["srcset", "data-srcset"]:
            for item in attrs.get(key, "").split(",", 5000):
                if item.strip():
                    self.add(item.strip().split(maxsplit=1)[0], "imagem")


class Findings(list):
    def __init__(self):
        super().__init__()
        self.errors = self.warnings = self.total = 0

    def append(self, item):
        self.total += 1
        self.errors += item["severity"] == "error"
        self.warnings += item["severity"] == "warning"
        if len(self) < 1000:
            super().append(item)


class SiteAudit:
    def __init__(self, workspace):
        self.workspace = workspace

    def run(self, value):
        with self.workspace.lock:
            root = self.workspace.root(value)
            files, issues, inventory = [], Findings(), set()
            templates = []
            reference_count = 0
            for parent, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = [
                    name
                    for name in dirs
                    if not name.startswith(".")
                    and name not in {"node_modules", "__pycache__"}
                    and not (Path(parent) / name).is_symlink()
                ]
                for name in names:
                    path = Path(parent) / name
                    if not name.startswith(".") and not path.is_symlink():
                        inventory.add(path.relative_to(root).as_posix())
                        if path.suffix.lower() in {".html", ".htm", ".css"}:
                            files.append(path)
            if len(files) > 5000 or sum(path.stat().st_size for path in files) > 50 * 1024 * 1024:
                raise ValueError(
                    "A verificação aceita até 5000 arquivos/50 MB. Escolha um site menor."
                )
            folded = {}
            for name in inventory:
                folded.setdefault(name.casefold(), []).append(name)

            def check(source, reference, base):
                nonlocal reference_count
                reference_count += 1
                if reference_count > 50000:
                    raise ValueError("A verificação excedeu 50 mil referências locais.")
                parsed = urlsplit(reference.replace("\\", "/"))
                if parsed.scheme or parsed.netloc or not parsed.path:
                    return None
                decoded = unquote(parsed.path)
                target = Path(
                    os.path.abspath(
                        root / decoded.lstrip("/") if decoded.startswith("/") else base / decoded
                    )
                )
                if not target.is_relative_to(root):
                    issues.append(
                        {
                            "severity": "error",
                            "path": source,
                            "reference": reference,
                            "message": "Referência fora da raiz do site.",
                        }
                    )
                    return None
                name = target.relative_to(root).as_posix()
                if decoded.endswith("/"):
                    name = name.rstrip("/") + "/index.html" if name != "." else "index.html"
                if name in inventory:
                    return name
                alternatives = folded.get(name.casefold(), [])
                if alternatives:
                    issues.append(
                        {
                            "severity": "error",
                            "path": source,
                            "reference": reference,
                            "message": "Maiúsculas/minúsculas diferentes. No Linux, use: "
                            + alternatives[0],
                        }
                    )
                else:
                    issues.append(
                        {
                            "severity": "error",
                            "path": source,
                            "reference": reference,
                            "message": "Arquivo local não encontrado.",
                        }
                    )
                return None

            for index, path in enumerate(files):
                progress(
                    "Conferindo referências: " + path.relative_to(root).as_posix(),
                    5 + int(index / max(len(files), 1) * 80),
                )
                relative = path.relative_to(root).as_posix()
                try:
                    if path.stat().st_size > 10 * 1024 * 1024:
                        raise ValueError("Arquivo maior que 10 MB.")
                    text = PageDeletion.text(path.read_bytes())
                    if "{{content}}" in text and (
                        path.stem.casefold() in {"template", "templete"}
                        or any(
                            part.casefold() in {"templates", "template"}
                            for part in path.relative_to(root).parts[:-1]
                        )
                    ):
                        templates.append(relative)
                        continue
                    refs = References(text)
                    if refs.limited:
                        issues.append(
                            {
                                "severity": "error",
                                "path": relative,
                                "reference": "",
                                "message": "Análise parcial: mais de 5000 referências ou uma URL local excessivamente longa.",
                            }
                        )
                    base = path.parent
                    if refs.base:
                        parsed = urlsplit(refs.base)
                        if parsed.scheme or parsed.netloc:
                            continue
                        decoded = unquote(parsed.path)
                        base = (
                            root / decoded.lstrip("/")
                            if decoded.startswith("/")
                            else base / decoded
                        )
                        if not decoded.endswith("/"):
                            base = base.parent
                    for reference, _ in refs.refs:
                        check(relative, reference, base)
                except (OSError, ValueError) as exc:
                    issues.append(
                        {
                            "severity": "error",
                            "path": relative,
                            "reference": "",
                            "message": "Não foi possível analisar: " + str(exc),
                        }
                    )
            catalog_path, listing = self.workspace.catalog_options(root)
            catalog = self.workspace.catalog_editor.site_path(root, catalog_path)
            linked = set()
            if catalog.exists():
                try:
                    source = CatalogSource(catalog.read_bytes().decode("utf-8-sig"))
                    for entry in source.entries.values():
                        name = check(catalog_path, entry["link"], (root / listing).parent)
                        check(catalog_path, entry["imagem"], (root / listing).parent)
                        if name:
                            if name in linked:
                                issues.append(
                                    {
                                        "severity": "warning",
                                        "path": catalog_path,
                                        "reference": entry["link"],
                                        "message": "Página cadastrada mais de uma vez.",
                                    }
                                )
                            linked.add(name)
                    for path in files:
                        name = path.relative_to(root).as_posix()
                        if (
                            name.startswith("projetos/")
                            and path.suffix.lower() in {".html", ".htm"}
                            and name not in linked
                        ):
                            issues.append(
                                {
                                    "severity": "warning",
                                    "path": name,
                                    "reference": "",
                                    "message": "Documentação sem cadastro no catálogo.",
                                }
                            )
                except (ValueError, OSError) as exc:
                    issues.append(
                        {
                            "severity": "error",
                            "path": catalog_path,
                            "reference": "",
                            "message": str(exc),
                        }
                    )
            return {
                "root": str(root),
                "checked_files": len(files) - len(templates),
                "templates_skipped": templates,
                "errors": issues.errors,
                "warnings": issues.warnings,
                "issues": issues[:1000],
                "truncated": issues.total > 1000,
            }
