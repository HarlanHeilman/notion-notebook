import json
from pathlib import Path

NEW_SRC = r"""from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import nbformat
from nbconvert import MarkdownExporter

NOTEBOOK_EXPORT_HEADING = "Notebook export (notion-connection.ipynb)"
RT_MAX = 1900

_IMAGE_ORDER = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
)

_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


def _resolve_notebook_path() -> Path:
    cwd = Path.cwd()
    for base in (cwd, cwd.parent, cwd.parent.parent):
        p = base / "notebooks" / "notion-connection.ipynb"
        if p.is_file():
            return p.resolve()
    p = cwd / "notion-connection.ipynb"
    if p.is_file():
        return p.resolve()
    raise FileNotFoundError(
        "Could not find notebooks/notion-connection.ipynb; run from repo root or notebooks/"
    )


def _plain_from_heading(block: dict[str, Any]) -> str:
    if block.get("type") != "heading_2":
        return ""
    h2 = cast(dict[str, Any], block.get("heading_2") or {})
    parts = h2.get("rich_text") or []
    return "".join(
        cast(str, p.get("plain_text") or "") for p in cast(list[dict[str, Any]], parts)
    ).strip()


def _first_top_level_child_database_index(children: list[dict[str, Any]]) -> int | None:
    for i, b in enumerate(children):
        if b.get("type") == "child_database":
            return i
    return None


def _delete_export_before_database(
    notion: Any, page_id: str, heading_exact: str, first_db_idx: int | None
) -> None:
    children = cast(
        list[dict[str, Any]],
        collect_paginated_api(notion.blocks.children.list, block_id=page_id, page_size=100),
    )
    if first_db_idx is None:
        first_db_idx = len(children)
    for i, block in enumerate(children):
        if i >= first_db_idx:
            break
        if _plain_from_heading(block) == heading_exact:
            for j in range(first_db_idx - 1, i - 1, -1):
                bid = cast(str, children[j]["id"])
                notion.blocks.delete(bid)
            return


def _rich_text_chunks(text: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    i = 0
    while i < len(text):
        part = text[i : i + RT_MAX]
        chunks.append({"type": "text", "text": {"content": part}})
        i += RT_MAX
    return chunks


def _blocks_from_code(language: str, source: str) -> list[dict[str, Any]]:
    segs = _rich_text_chunks(source)
    max_segs = 90
    out: list[dict[str, Any]] = []
    for i in range(0, len(segs), max_segs):
        out.append(
            {
                "type": "code",
                "code": {"language": language, "rich_text": segs[i : i + max_segs]},
            }
        )
    return out


def _blocks_from_text_paragraphs(text: str) -> list[dict[str, Any]]:
    segs = _rich_text_chunks(text)
    max_segs = 90
    out: list[dict[str, Any]] = []
    for i in range(0, len(segs), max_segs):
        out.append({"type": "paragraph", "paragraph": {"rich_text": segs[i : i + max_segs]}})
    return out


def _code_cell_language(cell: Any) -> str:
    meta = cell.metadata or {}
    vs = meta.get("vscode")
    if isinstance(vs, dict) and isinstance(vs.get("languageId"), str):
        lid = vs["languageId"].strip().lower()
        if lid:
            return lid
    if meta.get("pygments_lexer") == "ipython3":
        return "python"
    return "python"


def _decode_mime_binary(mime: str, raw: Any) -> bytes | None:
    if raw is None:
        return None
    if mime == "image/svg+xml" and isinstance(raw, str):
        return raw.encode("utf-8")
    if isinstance(raw, str):
        return base64.b64decode(raw, validate=False)
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return bytes(raw)
    if isinstance(raw, list):
        return base64.b64decode("".join(raw), validate=False)
    return None


def _upload_image_block(notion: Any, raw: bytes, mime: str, filename: str) -> dict[str, Any]:
    created = cast(
        dict[str, Any],
        notion.file_uploads.create(filename=filename, content_type=mime),
    )
    uid = cast(str, created["id"])
    cast(
        dict[str, Any],
        notion.file_uploads.send(uid, file=(filename, raw, mime)),
    )
    return {
        "type": "image",
        "image": {
            "type": "file_upload",
            "file_upload": {"id": uid},
        },
    }


def _outputs_to_notion_blocks(
    notion: Any,
    outputs: list[dict[str, Any]],
    cell_index: int,
    img_counter: list[int],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for o in outputs:
        ot = o.get("output_type")
        if ot == "stream":
            t = o.get("text", "")
            text = t if isinstance(t, str) else "".join(t)
            if text.strip():
                blocks.extend(_blocks_from_text_paragraphs(text))
        elif ot == "error":
            tb = o.get("traceback")
            if isinstance(tb, list):
                blocks.extend(_blocks_from_text_paragraphs("\n".join(tb)))
        elif ot in ("display_data", "execute_result"):
            data = cast(dict[str, Any], o.get("data") or {})
            for mime in _IMAGE_ORDER:
                if mime not in data:
                    continue
                b = _decode_mime_binary(mime, data[mime])
                if not b:
                    continue
                img_counter[0] += 1
                ext = _MIME_EXT.get(mime, ".png")
                fname = f"cell{cell_index}-out{img_counter[0]}{ext}"
                try:
                    blocks.append(_upload_image_block(notion, b, mime, fname))
                except Exception as exc:
                    blocks.extend(
                        _blocks_from_text_paragraphs(
                            f"(image upload failed: {type(exc).__name__}: {exc})"
                        )
                    )
            plain = data.get("text/plain")
            if plain is not None:
                t = plain if isinstance(plain, str) else "".join(plain)
                if t.strip():
                    blocks.extend(_blocks_from_text_paragraphs(t))
    return blocks


def _notion_blocks_from_notebook(notion: Any, nb: nbformat.NotebookNode) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    img_counter = [0]
    for ci, cell in enumerate(nb.cells):
        if cell.cell_type == "markdown":
            src = cell.source if isinstance(cell.source, str) else "".join(cell.source)
            src = src.strip()
            if not src:
                continue
            out.extend(_blocks_from_code("markdown", src))
        elif cell.cell_type == "code":
            src = cell.source if isinstance(cell.source, str) else "".join(cell.source)
            if src.strip():
                lang = _code_cell_language(cell)
                out.extend(_blocks_from_code(lang, src))
            out.extend(_outputs_to_notion_blocks(notion, cell.get("outputs", []), ci, img_counter))
        elif cell.cell_type == "raw":
            src = cell.source if isinstance(cell.source, str) else "".join(cell.source)
            src = src.strip()
            if src:
                out.extend(_blocks_from_text_paragraphs(src))
    return out


def _export_children_payload(
    notion: Any,
    notebook_path: Path,
    nb_node: nbformat.NotebookNode,
    md_export: str,
    exported_at: str,
) -> list[dict[str, Any]]:
    meta = (
        f"Source: {notebook_path}\n"
        f"Exported (UTC): {exported_at}\n"
        f"Format: nbconvert MarkdownExporter (hash); cells -> Notion blocks (code, text, images)\n"
        f"SHA256 (markdown export): {sha256(md_export.encode('utf-8')).hexdigest()}"
    )
    head: list[dict[str, Any]] = [
        {
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": NOTEBOOK_EXPORT_HEADING}}],
            },
        },
        {
            "type": "paragraph",
            "paragraph": {
                "rich_text": _rich_text_chunks(meta),
            },
        },
        {"type": "divider", "divider": {}},
    ]
    head.extend(_notion_blocks_from_notebook(notion, nb_node))
    return head


try:
    _tp = task_page_for_db
except NameError as exc:
    raise RuntimeError("Run the managed-database cell so task_page_for_db is defined") from exc

notebook_path = _resolve_notebook_path()
nb_node = nbformat.read(notebook_path.open(encoding="utf-8"), as_version=4)
md_export, _ = MarkdownExporter().from_notebook_node(nb_node)
exported_at = datetime.now(UTC).replace(microsecond=0).isoformat()

_top = cast(
    list[dict[str, Any]],
    collect_paginated_api(notion.blocks.children.list, block_id=_tp, page_size=100),
)
_first_db = _first_top_level_child_database_index(_top)

_delete_export_before_database(notion, _tp, NOTEBOOK_EXPORT_HEADING, _first_db)

children_payload = _export_children_payload(notion, notebook_path, nb_node, md_export, exported_at)
_bs = 100
_after: str | None = None
for _off in range(0, len(children_payload), _bs):
    _batch = children_payload[_off : _off + _bs]
    if _off == 0:
        _resp = cast(
            dict[str, Any],
            notion.blocks.children.append(_tp, children=_batch, position={"type": "start"}),
        )
    else:
        assert _after is not None
        _resp = cast(
            dict[str, Any],
            notion.blocks.children.append(
                _tp,
                children=_batch,
                position={"type": "after_block", "after_block": {"id": _after}},
            ),
        )
    _results = cast(list[dict[str, Any]], _resp.get("results") or [])
    if _results:
        _after = cast(str, _results[-1]["id"])
print(f"Prepended notebook export ({len(md_export)} chars markdown via nbconvert) to task page {_tp}")
"""


def main() -> None:
    root = Path(__file__).resolve().parent
    nb_path = root / "notion-connection.ipynb"
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    lines = NEW_SRC.splitlines(keepends=True)
    for c in nb["cells"]:
        if c.get("id") == "7761efea":
            c["source"] = lines
            break
    else:
        raise SystemExit("cell 7761efea not found")
    nb_path.write_text(
        json.dumps(nb, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
