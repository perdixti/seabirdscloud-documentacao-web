import pytest
from bs4 import BeautifulSoup

from seabirds.models import DocumentInput, RenderOptions
from seabirds.renderer import render_content, render_document


def test_markdown_nested_lists_and_tables():
    result = render_content("- Pai\n  - Filho\n\n| Chave | Valor |\n| --- | --- |\n| a | **b** |")
    assert result.count("<ul>") == 2
    assert "<table>" in result
    assert "<strong>b</strong>" in result


@pytest.mark.parametrize("raw_html", [True, False])
@pytest.mark.parametrize("first,second", [("ol", "ul"), ("ul", "ol")])
def test_ordered_and_unordered_lists_remain_separate(raw_html, first, second):
    sources = {"ol": "1. aaaa\n2. aaaa\n3. aaaa", "ul": "- aaaa\n- aaaa\n- aaaa"}
    html = render_content(
        sources[first] + "\n\n" + sources[second], RenderOptions(raw_html=raw_html)
    )
    soup = BeautifulSoup(html, "html.parser")
    lists = soup.find_all(["ol", "ul"], recursive=False)
    assert [node.name for node in lists] == [first, second]
    assert [len(node.find_all("li", recursive=False)) for node in lists] == [3, 3]


def test_nested_mixed_lists_keep_their_parent_and_separate_following_list():
    html = render_content("1. Pai\n  - Filho\n  - Outro filho\n2. Segundo pai\n\n- Lista separada")
    soup = BeautifulSoup(html, "html.parser")
    assert [node.name for node in soup.find_all(["ol", "ul"], recursive=False)] == ["ol", "ul"]
    assert len(soup.ol.find_all("li", recursive=False)) == 2
    assert len(soup.ol.li.ul.find_all("li", recursive=False)) == 2


def test_custom_links_and_unsafe_schemes():
    result = render_content("Texto **antes** e {{link: https://example.com?a=1&b=2 | Acesso}}")
    assert 'class="botao-link"' in result
    assert 'href="https://example.com?a=1&amp;b=2"' in result
    assert 'rel="noopener noreferrer"' in result
    assert "<a " not in render_content("{{link: javascript:alert(1) | Ruim}}")
    assert "<a " not in render_content("{{link: java\tscript:alert(1) | Ruim}}")


def test_fences_do_not_expand_custom_syntax_or_html():
    result = render_content(
        '```html\n<img onerror="alert(1)">\n{{link: https://example.com | Exemplo}}\n```'
    )
    assert "&lt;img" in result
    assert "{{link:" in result
    assert "<a " not in result
    assert "language-html" in result


def test_raw_html_and_markdown_xss_are_inert():
    result = render_content(
        "<script>alert(1)</script>\n\n![x](javascript:alert)\n\n[x](javascript:alert)",
        RenderOptions(raw_html=False),
    )
    assert "<script>" not in result
    assert 'href="javascript:' not in result
    assert 'src="javascript:' not in result


def test_raw_html_is_compatible_with_the_original_editor():
    assert '<div class="aviso">Conteúdo</div>' in render_content(
        '<div class="aviso">Conteúdo</div>'
    )


def test_image_web_path_and_copy_handler_match_legacy_template():
    from seabirds.models import GenerationSettings

    document = DocumentInput(
        markdown="![captura](local/img-12.png)\n\n```bash\necho ok\n```",
        generation=GenerationSettings(image_web_path="../../imagens/tutorial"),
    )
    html = render_document(document)
    assert 'src="../../imagens/tutorial/img-12.png"' in html
    assert 'alt="captura"' in html
    assert 'onclick="copiarCodigo(this)"' in html


def test_legacy_tables_and_switches():
    source = "```tablecard\n| A | B |\n| --- | --- |\n| **1** | 2 |\n```"
    result = render_content(source)
    assert '<div class="code-card table-card">' in result
    assert "<table>" in result
    assert "<strong>1</strong>" in result
    disabled = render_content(source, RenderOptions(table_cards=False, copy_buttons=False))
    assert "<table>" not in disabled
    assert "copy-button" not in disabled


def test_malformed_table_stays_readable():
    assert "<pre>" in render_content("```table\ntexto sem tabela\n```")


def test_pipe_highlight_does_not_break_standard_tables():
    assert 'class="distaque-pipe"' in render_content("| Uma **observação**")
    assert 'class="distaque-pipe"' not in render_content("| A |\n| --- |\n| B |")


def test_template_title_and_content_are_literal():
    document = DocumentInput(
        title="<x> \\1", markdown="`{{title}}`", template="<title>Antigo</title>{{content}}"
    )
    result = render_document(document)
    assert "<title>&lt;x&gt; \\1</title>" in result
    assert "<code>{{title}}</code>" in result


def test_title_placeholder_is_not_recursively_expanded():
    result = render_document(DocumentInput(title="{{content}}", markdown="# Conteúdo"))
    assert "<title>{{content}}</title>" in result


def test_python_markdown_extra_features_are_preserved():
    source = """## Título {#identificador}

Termo
:   Definição

Texto com nota[^1].

[^1]: Nota original.

<div markdown="1">
**Markdown dentro do HTML**
</div>
"""
    html = render_content(source)
    assert 'id="identificador"' in html
    assert "<dl>" in html and "<dd>Definição</dd>" in html
    assert 'class="footnote"' in html
    assert "<strong>Markdown dentro do HTML</strong>" in html
