"""Convert parsed notebooks and metadata into Notion block payloads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from notion_notebook.figure_database_manager import ExtractedFigure
from notion_notebook.git_utils import NotebookMetadata
from notion_notebook.notebook_parser import CellOutput, NotebookCell, ParsedNotebook
from notion_notebook.utils import (
    blocks_from_text_paragraphs,
    chunk_rich_text,
    create_code_block,
    create_error_block,
    export_heading_text,
)

PENDING_UPLOAD_BLOCK_TYPE = "pending_upload"

_IMAGE_ORDER = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
)

_MIME_TO_FMT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "png",
    "image/webp": "webp",
    "image/svg+xml": "png",
}


@dataclass
class NotionBlock:
    """Structured block description used before sending to the Notion API.

    Parameters
    ----------
    block_type
        Logical kind (``paragraph``, ``code``, ``pending_upload``, etc.).
    content
        Raw Notion API block dict when ``block_type`` is not pending; pending
        uploads use :data:`PENDING_UPLOAD_BLOCK_TYPE` with a ``ref`` index.
    """

    block_type: str
    content: dict[str, Any]


class NotionConverter:
    """Build Notion block dictionaries and figure rows from parsed notebooks."""

    def __init__(
        self,
        *,
        image_format_preference: str = "png",
        include_ai_summaries: bool = True,
    ) -> None:
        """Initialize converter options.

        Parameters
        ----------
        image_format_preference
            When multiple MIME types exist on an output, prefer this family
            (``png``, ``jpg``, or ``webp``) by reordering candidates.
        include_ai_summaries
            Reserved for parity with the exporter; figure rows always include
            an AI Summary column when the database is created.
        """
        self._image_pref = image_format_preference.lower().strip()
        self._include_ai = include_ai_summaries

    def blocks_from_notebook(
        self,
        parsed: ParsedNotebook,
        metadata: NotebookMetadata,
        notebook_filename: str,
    ) -> tuple[list[dict[str, Any]], list[ExtractedFigure]]:
        """Convert a parsed notebook into API block dicts and extracted figures.

        Parameters
        ----------
        parsed
            Parsed notebook cells and outputs.
        metadata
            Git and path metadata for the metadata callout.
        notebook_filename
            Basename including ``.ipynb`` for the export heading text.

        Returns
        -------
        tuple
            ``(blocks, figures)`` where ``blocks`` may contain internal
            ``pending_upload`` entries with ``ref`` indexing into ``figures``.
        """
        _ = self._include_ai
        figures: list[ExtractedFigure] = []
        blocks: list[dict[str, Any]] = []
        blocks.append(self.metadata_to_block(metadata))
        blocks.append(
            {
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": export_heading_text(notebook_filename)},
                        }
                    ],
                },
            }
        )
        blocks.append({"type": "divider", "divider": {}})
        for cell in parsed.cells:
            blocks.extend(self._blocks_for_cell(cell, figures))
        return blocks, figures

    def metadata_to_block(self, metadata: NotebookMetadata) -> dict[str, Any]:
        """Create the metadata callout block for the Notion page.

        Parameters
        ----------
        metadata
            Source fields for the callout body.

        Returns
        -------
        dict
            A Notion ``callout`` block dictionary.
        """
        lines = [
            "Notebook Metadata",
            "",
            f"Last Sync: {metadata.last_sync.astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]
        if metadata.github_remote:
            lines.append(f"GitHub Remote: {metadata.github_remote}")
        lines.append(f"Notebook Path: {metadata.notebook_path}")
        body = "\n".join(lines)
        return {
            "type": "callout",
            "callout": {
                "rich_text": chunk_rich_text(body),
                "icon": {"type": "emoji", "emoji": "📌"},
            },
        }

    def _blocks_for_cell(
        self,
        cell: NotebookCell,
        figures: list[ExtractedFigure],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if cell.cell_type == "markdown":
            src = cell.source.strip()
            if src:
                out.extend(create_code_block("markdown", src))
        elif cell.cell_type == "raw":
            src = cell.source.strip()
            if src:
                out.extend(blocks_from_text_paragraphs(src))
        elif cell.cell_type == "code":
            src = cell.source
            if src.strip():
                lang = _code_cell_language(cell)
                out.extend(create_code_block(lang, src))
            img_idx = [0]

            def bump() -> int:
                img_idx[0] += 1
                return img_idx[0]

            for co in cell.outputs:
                out.extend(
                    self._outputs_to_blocks(
                        co,
                        cell.index,
                        cell.source,
                        figures,
                        bump,
                    )
                )
        return out

    def _outputs_to_blocks(
        self,
        output: CellOutput,
        cell_index: int,
        cell_source: str,
        figures: list[ExtractedFigure],
        next_fig: Any,
    ) -> list[dict[str, Any]]:
        from notion_notebook.utils import extract_mime_binary

        blocks: list[dict[str, Any]] = []
        ot = output.output_type
        if ot == "stream":
            if output.content.strip():
                blocks.extend(blocks_from_text_paragraphs(output.content))
        elif ot == "error":
            if output.content.strip():
                blocks.append(create_error_block(output.content))
        elif ot in ("display_data", "execute_result"):
            order = self._mime_order()
            for mime in order:
                if mime not in output.mime_blobs:
                    continue
                raw = extract_mime_binary(mime, output.mime_blobs.get(mime))
                if not raw:
                    continue
                fi = next_fig()
                fmt = _MIME_TO_FMT.get(mime, "png")
                title = _extract_title(cell_source)
                fig = ExtractedFigure(
                    cell_index=cell_index,
                    figure_index=fi,
                    image_data=raw,
                    image_format=fmt,
                    code=cell_source[:20000],
                    title=title,
                    timestamp=datetime.now(UTC),
                )
                ref = len(figures)
                figures.append(fig)
                blocks.append(
                    {
                        "type": PENDING_UPLOAD_BLOCK_TYPE,
                        "ref": ref,
                    }
                )
            plain = output.content
            if plain.strip():
                blocks.extend(blocks_from_text_paragraphs(plain))
        return blocks

    def _mime_order(self) -> tuple[str, ...]:
        pref = self._image_pref
        if pref in ("jpg", "jpeg"):
            pri = "image/jpeg"
        elif pref == "webp":
            pri = "image/webp"
        else:
            pri = "image/png"
        rest = [m for m in _IMAGE_ORDER if m != pri]
        return (pri, *rest)


def _code_cell_language(cell: NotebookCell) -> str:
    meta = cast(dict[str, Any], cell.metadata)
    vs = meta.get("vscode")
    if isinstance(vs, dict):
        vsc = cast(dict[str, Any], vs)
        lid_raw = vsc.get("languageId")
        if isinstance(lid_raw, str):
            lid = lid_raw.strip().lower()
            if lid:
                return lid
    if meta.get("pygments_lexer") == "ipython3":
        return "python"
    return "python"


def _extract_title(source: str) -> str | None:
    m = re.search(r"plt\.title\s*\(\s*['\"]([^'\"]+)['\"]", source)
    if m:
        return m.group(1)
    m = re.search(r"set_title\s*\(\s*['\"]([^'\"]+)['\"]", source)
    if m:
        return m.group(1)
    return None
