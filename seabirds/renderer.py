"""Conversão Markdown com as extensões e classes usadas pelo template original."""

import re
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from xml.etree import ElementTree

import markdown
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor
from markdown_it import MarkdownIt
from markdown_it.rules_inline import text as original_text

from .models import DocumentInput, RenderOptions

TEMPLATES = Path(__file__).parent / "templates"
ASSET_PATTERN = re.compile(r"(?<![\w/])assets/([a-f0-9]{32}\.png)")


def safe_link(url: str) -> bool:
    normalized = "".join(c for c in url.strip() if ord(c) > 32)
    try:
        return urlsplit(normalized).scheme.lower() in ("", "http", "https", "mailto")
    except ValueError:
        return False


def parser(options: RenderOptions) -> MarkdownIt:
    md = MarkdownIt("js-default", {"html": options.raw_html}).enable("table")

    def legacy_link(state, silent):
        match = re.match(r"\{\{link:\s*([^|\n]+?)\s*\|\s*([^}\n]+?)\s*\}\}", state.src[state.pos :])
        if not match:
            return False
        if not silent:
            url, text = match.groups()
            token = state.push("html_inline", "", 0)
            if safe_link(url):
                css = ' class="botao-link"' if options.links else ""
                token.content = f'<a href="{escape(url.strip(), quote=True)}"{css} target="_blank" rel="noopener noreferrer">{escape(text.strip())}</a>'
            else:
                token.content = escape(text.strip())
        state.pos += len(match.group(0))
        return True

    md.inline.ruler.before("text", "legacy_link", legacy_link)

    # The text rule normally consumes braces; terminate text at a legacy marker too.
    # Registering before text is sufficient at token boundaries; a dedicated rule
    # splits ordinary text before the next {{link: marker.
    def split_text(state, silent):
        start = state.src.find("{{link:", state.pos)
        if start > state.pos:
            end = state.pos
            while end < start and state.src[end] not in "\\`*_[]!<&~\n":
                end += 1
            if end == start:
                if not silent:
                    state.pending += state.src[state.pos : start]
                state.pos = start
                return True
        return original_text(state, silent)

    md.inline.ruler.at("text", split_text)

    def legacy_highlight(state):
        for index, token in enumerate(state.tokens):
            if (
                token.type == "inline"
                and index
                and state.tokens[index - 1].type == "paragraph_open"
            ):
                if token.content.startswith("|"):
                    state.tokens[index - 1].attrSet("class", "distaque-pipe")
                    token.content = re.sub(r"^\|\s?", "", token.content, flags=re.M)
                    token.children = []
                    md.inline.parse(token.content, md, state.env, token.children)

    md.core.ruler.after("inline", "legacy_highlight", legacy_highlight)

    def fence(tokens, idx, renderer_options, env):
        token = tokens[idx]
        language = token.info.strip().split(maxsplit=1)[0] if token.info.strip() else ""
        table_enabled = (language == "table" and options.tables) or (
            language == "tablecard" and options.table_cards
        )
        if table_enabled:
            table = (
                MarkdownIt("js-default", {"html": options.raw_html})
                .enable("table")
                .render(token.content)
            )
            if "<table>" in table:
                css = "code-card table-card" if language == "tablecard" else "tabela-container"
                button = (
                    '<button class="copy-button" type="button" onclick="copiarCodigo(this)"><i class="fa-solid fa-copy"></i> Copiar</button>'
                    if options.copy_buttons and language == "tablecard"
                    else ""
                )
                return f'<div class="{css}">{button}{table}</div>\n'
        attr = f' class="language-{escape(language, quote=True)}"' if language else ""
        code = f"<pre><code{attr}>{escape(token.content)}</code></pre>"
        if options.code_cards:
            button = (
                '<button class="copy-button" type="button" onclick="copiarCodigo(this)"><i class="fa-solid fa-copy"></i> Copiar</button>'
                if options.copy_buttons
                else ""
            )
            return f'<div class="code-card">{button}{code}</div>\n'
        return code + "\n"

    md.renderer.rules["fence"] = fence
    return md


def render_content(
    source: str,
    options: RenderOptions | None = None,
    image_web_path: str | None = None,
    owned_image_paths: set[str] | None = None,
) -> str:
    options = options or RenderOptions()
    md = parser(options)
    if options.raw_html:
        return render_compatible(source, options, md, image_web_path, owned_image_paths or set())
    tokens = md.parse(source)
    if image_web_path is not None:
        for token in tokens:
            for child in token.children or []:
                if child.type == "image":
                    if child.attrGet("src") in (owned_image_paths or set()):
                        continue
                    filename = (child.attrGet("src") or "").split("/")[-1]
                    if re.fullmatch(r"img-\d+\.png", filename):
                        child.attrSet("src", image_web_path.rstrip("/") + "/" + filename)
    return md.renderer.render(tokens, md.options, {})


def render_compatible(source, options, token_parser, image_web_path, owned_image_paths):
    """Keep Python-Markdown Extra from the desktop app, including its HTML support.

    Token maps protect fenced code before custom expansion. Random HTML comments
    let Markdown process the surrounding document without rewriting code/cards.
    """
    converter = markdown.Markdown(extensions=["extra", "sane_lists"], tab_length=2)
    stashed = {}
    replacements = []
    tokens = token_parser.parse(source)
    for index, token in enumerate(tokens):
        if token.type == "fence":
            html = token_parser.renderer.rules["fence"](tokens, index, token_parser.options, {})
        elif (
            token.type == "paragraph_open"
            and index + 1 < len(tokens)
            and (
                token.attrGet("class") == "distaque-pipe"
                or tokens[index + 1].content.startswith("|")
            )
        ):
            content = re.sub(r"^\|\s?", "", tokens[index + 1].content, flags=re.M)
            html = '<p class="distaque-pipe">' + token_parser.renderInline(content) + "</p>"
        else:
            continue
        if token.map:
            placeholder = f"<!--SEABIRDS{uuid4().hex}-->"
            stashed[placeholder] = html
            replacements.append((*token.map, placeholder))
    lines = source.splitlines(keepends=True)
    for start, end, placeholder in sorted(replacements, reverse=True):
        indent = re.match(r"^\s*", lines[start]).group(0).replace("\n", "")
        lines[start:end] = [indent + placeholder + "\n"]

    class LegacyLink(InlineProcessor):
        def handleMatch(self, match, data):
            url, text = match.group(1).strip(), match.group(2).strip()
            node = ElementTree.Element("a" if safe_link(url) else "span")
            if node.tag == "a":
                node.set("href", url)
                node.set("target", "_blank")
                node.set("rel", "noopener noreferrer")
                if options.links:
                    node.set("class", "botao-link")
            node.text = markdown.util.AtomicString(text)
            return node, match.start(0), match.end(0)

    class ImagePaths(Treeprocessor):
        def run(self, root):
            if image_web_path is None:
                return root
            for image in root.iter("img"):
                if image.get("src") in owned_image_paths:
                    continue
                name = image.get("src", "").split("/")[-1]
                if re.fullmatch(r"img-\d+\.png", name):
                    image.set("src", image_web_path.rstrip("/") + "/" + name)
            return root

    converter.inlinePatterns.register(
        LegacyLink(r"\{\{link:\s*([^|\n]+?)\s*\|\s*([^}\n]+?)\s*\}\}", converter),
        "seabirds-link",
        175,
    )
    converter.treeprocessors.register(ImagePaths(converter), "seabirds-images", 5)
    result = converter.convert("".join(lines))
    for placeholder, html in stashed.items():
        result = result.replace(placeholder, html)
    return result


def render_document(document: DocumentInput) -> str:
    content = render_content(
        document.markdown,
        document.options,
        document.generation.image_web_path,
        {image.web_path for image in document.generation.images},
    )
    template = document.template or (TEMPLATES / "document.html").read_text(encoding="utf-8")
    title = escape(document.title)
    # Replace the template's title before inserting content, so text/code is untouched.
    if re.search(r"<title\b[^>]*>.*?</title\s*>", template, flags=re.I | re.S):
        template = re.sub(
            r"<title\b[^>]*>.*?</title\s*>",
            lambda _: "<title>{{title}}</title>",
            template,
            flags=re.I | re.S,
        )
    return re.sub(
        r"\{\{(title|content)\}\}",
        lambda match: title if match.group(1) == "title" else content,
        template,
    )
