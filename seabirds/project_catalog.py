"""Edita somente os dados do catálogo JavaScript, sem executar código do site."""

import hashlib
import html
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

import esprima

from .filesystem import atomic_write
from .storage import ConflictError

CATALOG_FILENAME = "projetos-conteudo.js"
PROJECT_FIELDS = ("titulo", "imagem", "descricao", "link")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".ico"}


def literal(value):
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


class CatalogSource:
    def __init__(self, text):
        self.text = text
        self.newline = "\r\n" if "\r\n" in text else "\n"
        try:
            tree = esprima.parseScript(text, {"range": True, "tokens": True})
        except (esprima.Error, RecursionError) as exc:
            raise ValueError(
                "O catálogo contém JavaScript inválido ou não suportado. Corrija o arquivo antes de salvar pelo formulário."
            ) from exc
        declarations = [
            item
            for statement in tree.body
            if statement.type == "VariableDeclaration"
            for item in statement.declarations
            if item.id.type == "Identifier" and item.id.name == "dadosCategorias"
        ]
        if (
            len(declarations) != 1
            or not declarations[0].init
            or declarations[0].init.type != "ArrayExpression"
        ):
            raise ValueError(
                "O arquivo precisa declarar dadosCategorias como uma lista de categorias e projetos."
            )
        self.array = declarations[0].init
        self.commas = [
            token.range[0]
            for token in tree.tokens
            if token.value == "," and token.type == "Punctuator"
        ]
        self.categories = []
        self.entries = {}
        for category_index, node in enumerate(self.array.elements):
            fields = self.properties(node)
            name = self.string(fields.get("categoria"))
            projects = fields.get("projetos")
            if not projects or projects.type != "ArrayExpression":
                raise ValueError("Cada categoria precisa conter uma lista projetos.")
            category = {
                "name": html.unescape(name),
                "node": node,
                "array": projects,
                "projects": [],
            }
            for index, project in enumerate(projects.elements):
                props = self.properties(project)
                values = {key: html.unescape(self.string(props.get(key))) for key in PROJECT_FIELDS}
                entry = {
                    "id": f"{category_index}:{index}",
                    **values,
                    "node": project,
                    "fields": props,
                    "category": category,
                }
                category["projects"].append(entry)
                self.entries[entry["id"]] = entry
            self.categories.append(category)

    @staticmethod
    def properties(node):
        if not node or node.type != "ObjectExpression":
            raise ValueError("Use objetos literais no catálogo, sem expressões calculadas.")
        fields = {}
        for prop in node.properties:
            if prop.type != "Property" or prop.computed or prop.method or prop.kind != "init":
                raise ValueError(
                    "O formulário aceita propriedades simples nos objetos do catálogo."
                )
            key = prop.key.name if prop.key.type == "Identifier" else prop.key.value
            if key in fields:
                raise ValueError("Uma propriedade do catálogo está repetida: " + str(key))
            fields[key] = prop.value
        return fields

    @staticmethod
    def string(node):
        if not node or node.type != "Literal" or not isinstance(node.value, str):
            raise ValueError(
                "Categoria, título, imagem, descrição e link precisam ser textos no catálogo."
            )
        return node.value

    def indent(self, offset):
        line = self.text[self.text.rfind("\n", 0, offset) + 1 : offset]
        return re.match(r"[ \t]*", line).group()

    def item_indent(self, array):
        return (
            self.indent(array.elements[0].range[0])
            if array.elements
            else self.indent(array.range[0]) + "    "
        )

    def append(self, array, rendered):
        close = array.range[1] - 1
        line_start = self.text.rfind("\n", 0, close) + 1
        alone = not self.text[line_start:close].strip()
        edits = []
        separator = ""
        if array.elements:
            last = array.elements[-1].range[1]
            if not any(last <= comma < close for comma in self.commas):
                if last == close:
                    separator = ","
                else:
                    edits.append((last, last, ","))
        insertion = (
            rendered + self.newline
            if alone
            else self.newline + rendered + self.newline + self.indent(close)
        )
        edits.append(
            (line_start if alone else close, line_start if alone else close, separator + insertion)
        )
        return edits

    def remove(self, entry):
        array = entry["category"]["array"]
        nodes = array.elements
        node = entry["node"]
        index = nodes.index(node)
        start, end = node.range
        if index < len(nodes) - 1:
            end = next(
                comma + 1 for comma in self.commas if end <= comma < nodes[index + 1].range[0]
            )
        elif index:
            start = next(
                comma for comma in self.commas if nodes[index - 1].range[1] <= comma < start
            )
        else:
            trailing = [comma for comma in self.commas if end <= comma < array.range[1] - 1]
            if trailing:
                end = trailing[0] + 1
        return (start, end, "")

    def edited_entry(self, entry, values, indent):
        if not entry:
            return self.newline.join(
                [
                    indent + "{",
                    *[
                        indent
                        + "    "
                        + key
                        + ": "
                        + literal(values[key])
                        + ("," if index < 3 else "")
                        for index, key in enumerate(PROJECT_FIELDS)
                    ],
                    indent + "}",
                ]
            )
        start, end = entry["node"].range
        raw = self.text[start:end]
        for key in sorted(
            PROJECT_FIELDS, key=lambda key: entry["fields"][key].range[0], reverse=True
        ):
            left, right = entry["fields"][key].range
            raw = raw[: left - start] + literal(values[key]) + raw[right - start :]
        old_indent = self.indent(start)
        lines = raw.splitlines()
        return self.newline.join(
            [
                indent + lines[0],
                *[
                    indent + (line[len(old_indent) :] if line.startswith(old_indent) else line)
                    for line in lines[1:]
                ],
            ]
        )

    def change(self, category_name, values, entry_id="", remove=False):
        entry = self.entries.get(entry_id) if entry_id else None
        if entry_id and not entry:
            raise ValueError("O cadastro não existe mais. Recarregue o catálogo.")
        if remove:
            edits = [self.remove(entry)]
        else:
            category = (
                entry["category"]
                if entry and entry["category"]["name"].casefold() == category_name.casefold()
                else next(
                    (
                        cat
                        for cat in self.categories
                        if cat["name"].casefold() == category_name.casefold()
                    ),
                    None,
                )
            )
            if entry and category is entry["category"]:
                edits = [
                    (*entry["fields"][key].range, literal(values[key])) for key in PROJECT_FIELDS
                ]
            else:
                edits = [self.remove(entry)] if entry else []
                if category:
                    rendered = self.edited_entry(entry, values, self.item_indent(category["array"]))
                    edits += self.append(category["array"], rendered)
                else:
                    indent = self.item_indent(self.array)
                    rendered = self.newline.join(
                        [
                            indent + "{",
                            indent
                            + "    categoria: "
                            + literal(html.escape(category_name, quote=True))
                            + ",",
                            indent + "    projetos: [",
                            self.edited_entry(entry, values, indent + "        "),
                            indent + "    ]",
                            indent + "}",
                        ]
                    )
                    edits += self.append(self.array, rendered)
        text = self.text
        for start, end, replacement in sorted(
            edits, key=lambda edit: (edit[0], edit[1]), reverse=True
        ):
            text = text[:start] + replacement + text[end:]
        CatalogSource(text)  # Recusa gravar um resultado que deixou de ser um catálogo válido.
        return text

    def public(self):
        return [
            {
                "categoria": cat["name"],
                "projetos": [
                    {key: entry[key] for key in ("id", *PROJECT_FIELDS)}
                    for entry in cat["projects"]
                ],
            }
            for cat in self.categories
        ]


class ProjectCatalog:
    def __init__(self, files):
        self.files = files

    @staticmethod
    def site_path(root, relative):
        name = PurePosixPath(relative)
        if (
            not relative
            or name.is_absolute()
            or "\\" in relative
            or any(part in {"..", "."} or part.startswith(".") for part in name.parts)
        ):
            raise ValueError("Informe um caminho relativo dentro da raiz do site.")
        path = root / relative
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError("O arquivo aponta para fora da raiz do site.")
        return path

    def paths(self, root, path, page):
        catalog = self.site_path(root, path)
        listing = self.site_path(root, page)
        if catalog.name != CATALOG_FILENAME:
            raise ValueError("Selecione o arquivo projetos-conteudo.js do site.")
        if listing.suffix.lower() not in {".html", ".htm"} or not listing.is_file():
            raise ValueError(
                "Informe a página HTML existente que exibe o catálogo, por exemplo paginas/projetos.html."
            )
        if not catalog.is_file() or catalog.stat().st_size > 2_000_000:
            raise ValueError(
                "Catálogo não encontrado ou maior que 2 MB. Confira a pasta do site e o caminho do arquivo."
            )
        return catalog, listing

    @staticmethod
    def reference(root, listing, value, extensions, exists=True):
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Informe um caminho de arquivo válido para o link ou a imagem.")
        # Caminhos físicos enviados pelo seletor/documento são convertidos para URLs do site.
        physical = Path(value)
        if physical.is_absolute() and physical.resolve().is_relative_to(root):
            target = physical.resolve()
        else:
            if "\\" in value:
                raise ValueError("Use barras / nos links do site.")
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
                raise ValueError(
                    "Use links e imagens locais do site, sem protocolo, parâmetros ou fragmentos."
                )
            decoded = unquote(parsed.path)
            if "\\" in decoded:
                raise ValueError("Use barras / nos links do site.")
            target = (
                root / decoded.lstrip("/") if decoded.startswith("/") else listing.parent / decoded
            ).resolve()
        if not target.is_relative_to(root) or any(
            part.startswith(".") for part in target.relative_to(root).parts
        ):
            raise ValueError("O link ou a imagem aponta para fora da raiz do site.")
        if target.suffix.lower() not in extensions or (exists and not target.is_file()):
            raise ValueError(
                "O HTML ou a imagem não existe no site ou tem um formato inválido. Gere o HTML e selecione uma imagem existente antes de salvar."
            )
        import os

        relative = Path(os.path.relpath(target, listing.parent)).as_posix()
        return quote(relative, safe="/-._~"), target

    def read(self, root, path, page, draft=None):
        catalog, listing = self.paths(root, path, page)
        raw = catalog.read_bytes()
        source = CatalogSource(raw.decode("utf-8-sig"))
        prefill = {}
        draft = draft or {}
        if draft.get("output_path"):
            prefill["link"] = self.reference(
                root,
                listing,
                draft["output_path"].replace("\\", "/"),
                {".html", ".htm"},
                exists=False,
            )[0]
            prefill["titulo"] = draft.get("title", "")
        if draft.get("image_path"):
            try:
                prefill["imagem"] = self.reference(
                    root, listing, draft["image_path"].replace("\\", "/"), IMAGE_EXTENSIONS
                )[0]
            except ValueError:
                pass  # Uma sugestão indisponível não impede escolher outra capa no formulário.
        return {
            "path": path,
            "page": page,
            "version": hashlib.sha256(raw).hexdigest(),
            "categories": source.public(),
            "prefill": prefill,
        }

    def write(self, root, path, page, version, data, entry_id="", remove=False):
        catalog, listing = self.paths(root, path, page)
        raw = catalog.read_bytes()
        if hashlib.sha256(raw).hexdigest() != version:
            raise ConflictError(
                "O catálogo mudou desde a abertura. Recarregue antes de salvar; sua edição foi preservada no formulário."
            )
        source = CatalogSource(raw.decode("utf-8-sig"))
        if not remove:
            category = data["categoria"].strip()
            if not category or len(category) > 100 or any(ord(char) < 32 for char in category):
                raise ValueError("Informe uma categoria válida.")
            values = {key: data[key].strip() for key in PROJECT_FIELDS}
            if not values["titulo"] or not values["descricao"]:
                raise ValueError("Preencha o título e a descrição do cadastro.")
            values["link"], target = self.reference(
                root, listing, values["link"], {".html", ".htm"}
            )
            values["imagem"] = self.reference(root, listing, values["imagem"], IMAGE_EXTENSIONS)[0]
            for entry in source.entries.values():
                try:
                    other = self.reference(
                        root, listing, entry["link"], {".html", ".htm"}, exists=False
                    )[1]
                except ValueError:
                    continue
                if entry["id"] != entry_id and target == other:
                    raise ValueError(
                        "Esta página já está no catálogo. Use Editar no cadastro existente."
                    )
            values = {key: html.escape(value, quote=True) for key, value in values.items()}
            changed = source.change(category, values, entry_id)
        else:
            if not entry_id or entry_id not in source.entries:
                raise ValueError("Selecione um cadastro existente para remover.")
            changed = source.change("", {}, entry_id, remove=True)
        backup = self.files.backup(catalog)
        if catalog.read_bytes() != raw:
            raise ConflictError(
                "O catálogo mudou durante a gravação. Recarregue antes de tentar novamente."
            )
        atomic_write(catalog, ("\ufeff" if raw.startswith(b"\xef\xbb\xbf") else "") + changed)
        return {
            **self.read(root, path, page),
            "backup": backup,
            "saved_link": "" if remove else html.unescape(values["link"]),
        }

    def undo(self, root, path, page, version, backup):
        catalog, _ = self.paths(root, path, page)
        raw = catalog.read_bytes()
        if hashlib.sha256(raw).hexdigest() != version:
            raise ConflictError(
                "O catálogo mudou. Recarregue antes de desfazer a última alteração."
            )
        previous = Path(backup)
        if (
            not previous.resolve().is_relative_to((self.files.data_dir / "file-backups").resolve())
            or previous.name != CATALOG_FILENAME
            or not previous.is_file()
        ):
            raise ValueError("A cópia anterior do catálogo não está disponível.")
        restored = previous.read_bytes().decode("utf-8")
        CatalogSource(restored.lstrip("\ufeff"))
        current_backup = self.files.backup(catalog)
        if catalog.read_bytes() != raw:
            raise ConflictError(
                "O catálogo mudou durante a restauração. Recarregue antes de tentar novamente."
            )
        atomic_write(catalog, restored)
        return {**self.read(root, path, page), "backup": current_backup}
