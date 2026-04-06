"""Shared helpers for Notion block payloads and binary output decoding."""

from __future__ import annotations

import base64
import re
from typing import Any

RT_MAX = 1900
CODE_RICH_TEXT_MAX_SEGMENTS = 90

EXPORT_REGION_MARKER_TEXT = "[notion-notebook] EXPORT_REGION_BEGIN v1"

FIGURES_DATABASE_TITLE = "Figures"


def normalize_page_id(page_id_or_url: str) -> str:
    """Strip a Notion URL or id string to the 32-character hex page id.

    Parameters
    ----------
    page_id_or_url
        Raw id, UUID with hyphens, or a ``notion.so`` URL containing the id.

    Returns
    -------
    str
        Lowercase hex string without hyphens.

    Raises
    ------
    ValueError
        When no 32-character hex id can be extracted.
    """
    s = page_id_or_url.strip()
    if "notion.so" in s or "notion.site" in s:
        m = re.search(r"([0-9a-f]{32})", s, re.I)
        if m:
            return m.group(1).lower()
    s = s.replace("-", "")
    if len(s) == 32 and re.fullmatch(r"[0-9a-f]+", s, re.I):
        return s.lower()
    raise ValueError(f"Could not normalize Notion page id from: {page_id_or_url!r}")


def extract_mime_binary(mime_type: str, raw_data: Any) -> bytes | None:
    """Decode Jupyter output payload data for ``mime_type`` to raw bytes.

    Parameters
    ----------
    mime_type
        MIME key from ``output.data`` (for example ``image/png``).
    raw_data
        Base64 string, list of strings, ``bytes``, or UTF-8 text for SVG.

    Returns
    -------
    bytes or None
        Decoded bytes, or ``None`` when ``raw_data`` cannot be decoded.
    """
    if raw_data is None:
        return None
    if mime_type == "image/svg+xml" and isinstance(raw_data, str):
        return raw_data.encode("utf-8")
    if isinstance(raw_data, str):
        return base64.b64decode(raw_data, validate=False)
    if isinstance(raw_data, (bytes, bytearray, memoryview)):
        return bytes(raw_data)
    if isinstance(raw_data, list):
        return base64.b64decode("".join(raw_data), validate=False)
    return None


def chunk_rich_text(text: str, max_chunk_size: int = RT_MAX) -> list[dict[str, Any]]:
    """Split ``text`` into Notion ``rich_text`` segment dicts under the size limit.

    Parameters
    ----------
    text
        Full UTF-8 text to place in ``rich_text`` segments.
    max_chunk_size
        Maximum characters per segment (Notion enforces roughly 2000; default 1900).

    Returns
    -------
    list of dict
        Items suitable for ``paragraph``, ``callout``, or ``code`` ``rich_text`` arrays.
    """
    chunks: list[dict[str, Any]] = []
    i = 0
    while i < len(text):
        part = text[i : i + max_chunk_size]
        chunks.append({"type": "text", "text": {"content": part}})
        i += max_chunk_size
    return chunks


def create_code_block(language: str, code: str) -> list[dict[str, Any]]:
    """Build one or more Notion ``code`` block dicts, chunking when needed.

    Parameters
    ----------
    language
        Prism language id (for example ``python``, ``markdown``).
    code
        Full source text.

    Returns
    -------
    list of dict
        API-ready block objects with ``type`` ``code``.
    """
    segs = chunk_rich_text(code)
    out: list[dict[str, Any]] = []
    for i in range(0, len(segs), CODE_RICH_TEXT_MAX_SEGMENTS):
        batch = segs[i : i + CODE_RICH_TEXT_MAX_SEGMENTS]
        out.append({"type": "code", "code": {"language": language, "rich_text": batch}})
    return out


def create_error_block(error_text: str) -> dict[str, Any]:
    """Build a callout block that surfaces stderr/traceback-style text.

    Parameters
    ----------
    error_text
        Full error or traceback string.

    Returns
    -------
    dict
        A Notion ``callout`` block dictionary.
    """
    return {
        "type": "callout",
        "callout": {
            "rich_text": chunk_rich_text(error_text),
            "icon": {"type": "emoji", "emoji": "⚠️"},
        },
    }


def blocks_from_text_paragraphs(text: str) -> list[dict[str, Any]]:
    """Build ``paragraph`` blocks from plain text, chunking rich_text as needed.

    Parameters
    ----------
    text
        Arbitrary plain text (for example stream output).

    Returns
    -------
    list of dict
        One or more ``paragraph`` blocks.
    """
    segs = chunk_rich_text(text)
    out: list[dict[str, Any]] = []
    for i in range(0, len(segs), CODE_RICH_TEXT_MAX_SEGMENTS):
        batch = segs[i : i + CODE_RICH_TEXT_MAX_SEGMENTS]
        out.append({"type": "paragraph", "paragraph": {"rich_text": batch}})
    return out


def child_database_title_plain(block: dict[str, Any]) -> str:
    """Return trimmed display title for a ``child_database`` block when present.

    Parameters
    ----------
    block
        Notion API block object with ``type`` ``child_database``.

    Returns
    -------
    str
        Title string for comparison, or empty when missing or not a child database.
    """
    cd = block.get("child_database")
    if not isinstance(cd, dict):
        return ""
    t = cd.get("title")
    if isinstance(t, str):
        return t.strip()
    if isinstance(t, list):
        return "".join(
            str(p.get("plain_text", ""))
            for p in t
            if isinstance(p, dict)
        ).strip()
    return ""


def child_database_title_equals(block: dict[str, Any], expected: str) -> bool:
    """Return True when ``block`` is a ``child_database`` whose title matches ``expected``.

    Parameters
    ----------
    block
        Notion block dict.
    expected
        Expected title after strip (for example :data:`FIGURES_DATABASE_TITLE`).

    Returns
    -------
    bool
    """
    if block.get("type") != "child_database":
        return False
    return child_database_title_plain(block) == expected.strip()


def figures_database_child_index(children: list[dict[str, Any]], title: str | None = None) -> int | None:
    """Return the index of the top-level ``child_database`` whose title matches the figures table.

    Parameters
    ----------
    children
        Ordered top-level page blocks from ``blocks.children.list``.
    title
        Database title to match; defaults to :data:`FIGURES_DATABASE_TITLE`.

    Returns
    -------
    int or None
        Index of the matching block, or ``None`` when no such database exists.
    """
    want = (title or FIGURES_DATABASE_TITLE).strip()
    for i, b in enumerate(children):
        if child_database_title_equals(b, want):
            return i
    return None


def plain_text_from_rich_block(block: dict[str, Any], key: str) -> str:
    """Concatenate plain text from a block's ``rich_text`` field when present.

    Parameters
    ----------
    block
        A Notion block object.
    key
        Inner key (``paragraph``, ``heading_2``, ``callout``, etc.).

    Returns
    -------
    str
        Joined text content, or empty string when missing.
    """
    inner = block.get(key)
    if not isinstance(inner, dict):
        return ""
    parts = inner.get("rich_text") or []
    if not isinstance(parts, list):
        return ""
    out = []
    for p in parts:
        if isinstance(p, dict) and p.get("plain_text") is not None:
            out.append(str(p.get("plain_text")))
        elif isinstance(p, dict) and p.get("type") == "text":
            t = (p.get("text") or {}).get("content")
            if t:
                out.append(str(t))
    return "".join(out)


def export_heading_text(notebook_filename: str) -> str:
    """Return the canonical export section ``heading_2`` text for a notebook file.

    Parameters
    ----------
    notebook_filename
        Basename including ``.ipynb`` (for example ``analysis.ipynb``).

    Returns
    -------
    str
        Value ``Notebook export ({notebook_filename})``.
    """
    return f"Notebook export ({notebook_filename})"
