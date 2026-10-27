"""Ferramentas em lote geram um ZIP; nunca alteram os arquivos originais."""

import io
import re
from pathlib import PurePosixPath
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from bs4 import BeautifulSoup

TEXT_EXTENSIONS = {".txt", ".html", ".htm", ".md", ".csv", ".json", ".xml"}


def format_html(source: str) -> str:
    blocks = {}
    prefix = f"SEABIRDS{uuid4().hex}"

    def protect(match):
        key = f"{prefix}{len(blocks)}END"
        blocks[key] = match.group(0)
        return key

    protected = re.sub(
        r"<(pre|script|style|textarea)\b[^>]*>.*?</\1\s*>", protect, source, flags=re.I | re.S
    )
    preserve = {
        "p",
        "a",
        "span",
        "strong",
        "em",
        "b",
        "i",
        "code",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "title",
    }
    output = BeautifulSoup(protected, "html.parser", preserve_whitespace_tags=preserve).prettify()
    for key, value in blocks.items():
        output = output.replace(key, value)
    return output


def transform_files(files, operation, old="", new="") -> bytes:
    if operation not in {"replace", "format"}:
        raise ValueError("Operação inválida.")
    if operation == "replace" and not old:
        raise ValueError("Preencha o texto a procurar.")
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for index, (filename, raw) in enumerate(files, start=1):
            name = re.split(r"[/\\]", filename)[-1]
            suffix = PurePosixPath(name).suffix.lower()
            if suffix not in TEXT_EXTENSIONS or (
                operation == "format" and suffix not in {".html", ".htm"}
            ):
                raise ValueError(f"Tipo de arquivo não suportado: {name}")
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError(f"O arquivo {name} precisa estar em UTF-8.") from exc
            text = text.replace(old, new) if operation == "replace" else format_html(text)
            archive.writestr(f"{index:03d}-{name}", text)
    return output.getvalue()
