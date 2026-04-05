from notion_notebook.utils import (
    chunk_rich_text,
    export_heading_text,
    extract_mime_binary,
    normalize_page_id,
    plain_text_from_rich_block,
)


def test_normalize_page_id_hex() -> None:
    assert normalize_page_id("a" * 32) == "a" * 32


def test_normalize_page_id_uuid() -> None:
    s = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert normalize_page_id(s) == "aaaaaaaabbbbccccddddeeeeeeeeeeee"


def test_normalize_page_id_url() -> None:
    u = "https://www.notion.so/workspace/Test-1234567890abcdef1234567890abcdef"
    assert normalize_page_id(u) == "1234567890abcdef1234567890abcdef"


def test_extract_mime_binary_b64() -> None:
    import base64

    raw = b"abc"
    b64 = base64.b64encode(raw).decode("ascii")
    assert extract_mime_binary("image/png", b64) == raw


def test_chunk_rich_text_splits() -> None:
    text = "x" * 2000
    parts = chunk_rich_text(text, max_chunk_size=1900)
    assert len(parts) == 2
    assert parts[0]["text"]["content"] == "x" * 1900


def test_export_heading_text() -> None:
    assert export_heading_text("n.ipynb") == "Notebook export (n.ipynb)"


def test_plain_text_from_heading() -> None:
    b = {
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "Notebook export (x.ipynb)"}}],
        },
    }
    assert plain_text_from_rich_block(b, "heading_2") == "Notebook export (x.ipynb)"
