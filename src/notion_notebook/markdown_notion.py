"""Convert notebook Markdown cells into native Notion block payloads."""

from __future__ import annotations

from typing import Any, cast

import mistune

from notion_notebook.utils import blocks_from_text_paragraphs, create_code_block

RT_MAX = 1900

_DEFAULT_ANNOTATIONS: dict[str, Any] = {
    "bold": False,
    "italic": False,
    "strikethrough": False,
    "underline": False,
    "code": False,
    "color": "default",
}


def markdown_to_notion_blocks(markdown_source: str) -> list[dict[str, Any]]:
    """Parse CommonMark-style *markdown_source* into Notion ``block`` objects.

    Headings map to ``heading_1`` through ``heading_3`` (deeper levels use
    ``heading_3``). Lists, task items, quotes, thematic breaks, fenced code,
    tables, and inline emphasis, links, and images are mapped to the closest
    Notion block types. Unsupported or unknown AST nodes fall back to plain
    paragraphs so export never drops content silently.

    Parameters
    ----------
    markdown_source
        Raw Markdown cell text (including Jupyter math or extensions not
        handled here; those fragments are passed through as plain text where
        possible).

    Returns
    -------
    list of dict
        API-ready Notion block dictionaries suitable for ``blocks.children.append``.
    """
    src = markdown_source.strip()
    if not src:
        return []
    md = mistune.create_markdown(
        renderer="ast",
        plugins=["strikethrough", "table", "url", "task_lists"],
    )
    ast = cast(list[dict[str, Any]], md(src))
    out: list[dict[str, Any]] = []
    for node in ast:
        out.extend(_block_node_to_notion(node))
    return out


def _placeholder_rich() -> list[dict[str, Any]]:
    return [_segment(" ")]


def _segment(
    content: str,
    *,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    strikethrough: bool = False,
    link_url: str | None = None,
) -> dict[str, Any]:
    text: dict[str, Any] = {"content": content}
    if link_url:
        text["link"] = {"url": link_url}
    ann = dict(_DEFAULT_ANNOTATIONS)
    ann["bold"] = bold
    ann["italic"] = italic
    ann["code"] = code
    ann["strikethrough"] = strikethrough
    return {"type": "text", "text": text, "annotations": ann}


def _chunk_rich(
    raw: str,
    *,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    strikethrough: bool = False,
    link_url: str | None = None,
) -> list[dict[str, Any]]:
    if not raw:
        return []
    parts: list[dict[str, Any]] = []
    i = 0
    while i < len(raw):
        part = raw[i : i + RT_MAX]
        parts.append(
            _segment(
                part,
                bold=bold,
                italic=italic,
                code=code,
                strikethrough=strikethrough,
                link_url=link_url,
            )
        )
        i += RT_MAX
    return parts


def _inline_to_rich_text(
    nodes: list[dict[str, Any]],
    *,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    strikethrough: bool = False,
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for n in nodes:
        t = n.get("type")
        if t == "text":
            segments.extend(
                _chunk_rich(
                    str(n.get("raw", "")),
                    bold=bold,
                    italic=italic,
                    code=code,
                    strikethrough=strikethrough,
                )
            )
        elif t == "strong":
            segments.extend(
                _inline_to_rich_text(
                    n.get("children", []),
                    bold=True,
                    italic=italic,
                    code=code,
                    strikethrough=strikethrough,
                )
            )
        elif t == "emphasis":
            segments.extend(
                _inline_to_rich_text(
                    n.get("children", []),
                    bold=bold,
                    italic=True,
                    code=code,
                    strikethrough=strikethrough,
                )
            )
        elif t == "codespan":
            segments.extend(
                _chunk_rich(
                    str(n.get("raw", "")),
                    bold=bold,
                    italic=italic,
                    code=True,
                    strikethrough=strikethrough,
                )
            )
        elif t == "strikethrough":
            segments.extend(
                _inline_to_rich_text(
                    n.get("children", []),
                    bold=bold,
                    italic=italic,
                    code=code,
                    strikethrough=True,
                )
            )
        elif t == "link":
            url = str((n.get("attrs") or {}).get("url", "") or "")
            inner = _inline_to_rich_text(
                n.get("children", []),
                bold=bold,
                italic=italic,
                code=code,
                strikethrough=strikethrough,
            )
            if not url:
                segments.extend(inner)
            elif not inner:
                segments.extend(_chunk_rich(url, link_url=url))
            else:
                for seg in inner:
                    txt = seg.get("text")
                    if isinstance(txt, dict):
                        txt["link"] = {"url": url}
                    segments.append(seg)
        elif t == "image":
            url = str((n.get("attrs") or {}).get("url", "") or "")
            alt = _inline_plain_text(n.get("children", []))
            label = f"{alt} ({url})" if alt else url
            segments.extend(_chunk_rich(label, link_url=url or None))
        elif t == "linebreak":
            segments.extend(_chunk_rich("\n", bold=bold, italic=italic, code=code, strikethrough=strikethrough))
        else:
            segments.extend(_chunk_rich(str(n), bold=bold, italic=italic, code=code, strikethrough=strikethrough))
    return segments


def _inline_plain_text(nodes: list[dict[str, Any]]) -> str:
    parts: list[str] = []

    def walk(ns: list[dict[str, Any]]) -> None:
        for n in ns:
            t = n.get("type")
            if t == "text":
                parts.append(str(n.get("raw", "")))
            elif t in ("strong", "emphasis", "codespan", "strikethrough", "link", "image"):
                walk(n.get("children", []))

    walk(nodes)
    return "".join(parts)


def _heading_key(level: int) -> str:
    lv = min(max(level, 1), 3)
    return f"heading_{lv}"


def _block_node_to_notion(node: dict[str, Any]) -> list[dict[str, Any]]:
    nt = node.get("type")
    if nt in (None, "blank_line"):
        return []
    if nt == "paragraph":
        return _paragraph_from_ast(node)
    if nt == "heading":
        level = int((node.get("attrs") or {}).get("level", 1))
        rt = _inline_to_rich_text(node.get("children", []))
        key = _heading_key(level)
        return [{"type": key, key: {"rich_text": rt or _placeholder_rich(), "is_toggleable": False}}]
    if nt == "list":
        return _list_node_to_blocks(node)
    if nt == "block_code":
        raw = str(node.get("raw", ""))
        info = str((node.get("attrs") or {}).get("info", "") or "").strip()
        lang = (info.split()[0] if info else "plain")[:100]
        return create_code_block(lang or "plain", raw.rstrip("\n"))
    if nt == "block_quote":
        inner: list[dict[str, Any]] = []
        for ch in node.get("children", []):
            inner.extend(_block_node_to_notion(ch))
        if not inner:
            return []
        if len(inner) == 1 and inner[0].get("type") == "paragraph":
            rt = inner[0]["paragraph"]["rich_text"]
            return [{"type": "quote", "quote": {"rich_text": rt, "color": "default"}}]
        return [{"type": "quote", "quote": {"rich_text": _placeholder_rich(), "children": inner}}]
    if nt == "thematic_break":
        return [{"type": "divider", "divider": {}}]
    if nt == "table":
        return _table_to_notion(node)
    return blocks_from_text_paragraphs(f"[unsupported markdown block: {nt}]")


def _paragraph_from_ast(node: dict[str, Any]) -> list[dict[str, Any]]:
    ch = node.get("children", [])
    if len(ch) == 1 and ch[0].get("type") == "image":
        im = ch[0]
        url = str((im.get("attrs") or {}).get("url", "") or "")
        if url:
            return [
                {
                    "type": "image",
                    "image": {"type": "external", "external": {"url": url}},
                }
            ]
    rt = _inline_to_rich_text(ch)
    if not rt:
        return []
    return [{"type": "paragraph", "paragraph": {"rich_text": rt}}]


def _list_node_to_blocks(node: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ordered = bool((node.get("attrs") or {}).get("ordered", False))
    for item in node.get("children", []):
        it = item.get("type")
        if it == "list_item":
            out.append(_list_item_block(item, ordered))
        elif it == "task_list_item":
            out.append(_task_list_item_block(item))
        elif it == "list":
            out.extend(_list_node_to_blocks(item))
    return out


def _list_item_block(item: dict[str, Any], ordered: bool) -> dict[str, Any]:
    rich: list[dict[str, Any]] = []
    nested: list[dict[str, Any]] = []
    for c in item.get("children", []):
        ct = c.get("type")
        if ct == "block_text":
            rich = _inline_to_rich_text(c.get("children", []))
        elif ct == "list":
            nested = _list_node_to_blocks(c)
    key = "numbered_list_item" if ordered else "bulleted_list_item"
    inner: dict[str, Any] = {"rich_text": rich or _placeholder_rich()}
    if nested:
        inner["children"] = nested
    return {"type": key, key: inner}


def _task_list_item_block(item: dict[str, Any]) -> dict[str, Any]:
    checked = bool((item.get("attrs") or {}).get("checked", False))
    rich: list[dict[str, Any]] = []
    nested: list[dict[str, Any]] = []
    for c in item.get("children", []):
        ct = c.get("type")
        if ct == "block_text":
            rich = _inline_to_rich_text(c.get("children", []))
        elif ct == "list":
            nested = _list_node_to_blocks(c)
    inner: dict[str, Any] = {"rich_text": rich or _placeholder_rich(), "checked": checked}
    if nested:
        inner["children"] = nested
    return {"type": "to_do", "to_do": inner}


def _table_to_notion(node: dict[str, Any]) -> list[dict[str, Any]]:
    rows_cells: list[list[dict[str, Any]]] = []
    has_head = False
    for section in node.get("children", []):
        st = section.get("type")
        if st == "table_head":
            has_head = True
            row = section.get("children", [])
            if row:
                rows_cells.append(row)
        elif st == "table_body":
            for tr in section.get("children", []):
                if tr.get("type") == "table_row":
                    rows_cells.append(tr.get("children", []))
    if not rows_cells:
        return blocks_from_text_paragraphs("[empty table]")
    width = max(len(r) for r in rows_cells)
    notion_rows: list[dict[str, Any]] = []
    for row in rows_cells:
        cells_out: list[list[dict[str, Any]]] = []
        for cell in row:
            if cell.get("type") != "table_cell":
                continue
            rt = _inline_to_rich_text(cell.get("children", []))
            cells_out.append(rt or _placeholder_rich())
        while len(cells_out) < width:
            cells_out.append(_placeholder_rich())
        notion_rows.append(
            {
                "type": "table_row",
                "table_row": {"cells": cells_out[:width]},
            }
        )
    tbl: dict[str, Any] = {
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": has_head,
            "has_row_header": False,
        },
    }
    if notion_rows:
        tbl["children"] = notion_rows
    return [tbl]
