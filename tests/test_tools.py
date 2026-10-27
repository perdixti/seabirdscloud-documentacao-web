import io
from zipfile import ZipFile

import pytest

from seabirds.tools import format_html, transform_files


def test_format_preserves_preformatted_content_and_inline_spacing():
    code = "<pre><code>  a &lt; b\n    x = 1\n</code></pre>"
    result = format_html(
        f"<!doctype html><html><body><p>Olá <strong>mundo</strong>!</p>{code}</body></html>"
    )
    assert code in result
    assert "<p>Olá <strong>mundo</strong>!</p>" in result


def test_batch_multiline_replace_and_name_collisions():
    result = transform_files([("a/x.md", b"a\nb"), ("b/x.md", b"a\nb")], "replace", "a\nb", "novo")
    with ZipFile(io.BytesIO(result)) as archive:
        assert len(set(archive.namelist())) == 2
        assert all(archive.read(name) == b"novo" for name in archive.namelist())


@pytest.mark.parametrize(
    "files,operation,old",
    [
        ([("x.exe", b"hello")], "replace", "a"),
        ([("x.md", b"hello")], "format", ""),
        ([("x.md", b"\xff")], "replace", "a"),
        ([("x.md", b"hello")], "replace", ""),
    ],
)
def test_batch_validation(files, operation, old):
    with pytest.raises(ValueError):
        transform_files(files, operation, old)
