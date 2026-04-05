"""Notion API orchestration for page validation, block sync, and uploads."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, cast

from notion_client import Client
from notion_client.errors import APIResponseError
from notion_client.helpers import collect_paginated_api

from notion_notebook.figure_database_manager import ExtractedFigure
from notion_notebook.notion_converter import PENDING_UPLOAD_BLOCK_TYPE
from notion_notebook.utils import export_heading_text, plain_text_from_rich_block

BLOCK_BATCH = 100
_MAX_RETRIES = 4


@dataclass
class SyncBlocksResult:
    """Outcome of replacing the export block range on a page.

    Parameters
    ----------
    success
        True when no blocking error occurred.
    blocks_created
        Number of Notion blocks appended after deletion.
    blocks_deleted_old
        Number of blocks removed from the previous export.
    images_uploaded
        Successful image file uploads during pending resolution.
    errors
        Non-fatal issues (for example skipped images).
    """

    success: bool
    blocks_created: int
    blocks_deleted_old: int
    images_uploaded: int
    errors: list[str] = field(default_factory=list)


def find_child_database_id_by_title(
    notion: Any,
    page_id: str,
    title: str,
) -> str | None:
    """Return the database id for a top-level ``child_database`` block title match.

    Parameters
    ----------
    notion
        Notion API client.
    page_id
        Parent page id.
    title
        Expected child database title (exact strip match).

    Returns
    -------
    str or None
        Block id (same as database id for child databases) when found.
    """
    children = list(
        collect_paginated_api(
            notion.blocks.children.list,
            block_id=page_id,
            page_size=100,
        )
    )
    for b in children:
        if b.get("type") != "child_database":
            continue
        if _child_database_title_equals(b, title):
            return str(b["id"])
    return None


def _child_database_title_equals(block: dict[str, Any], expected: str) -> bool:
    cd = block.get("child_database")
    if not isinstance(cd, dict):
        return False
    t = cd.get("title")
    if isinstance(t, str):
        return t.strip() == expected
    if isinstance(t, list):
        plain = "".join(
            str(p.get("plain_text", ""))
            for p in t
            if isinstance(p, dict)
        ).strip()
        return plain == expected
    return False


class NotionPageSync:
    """Validate pages and replace the export block range idempotently."""

    def __init__(
        self,
        token: str,
        page_id: str,
        *,
        verbose: bool = False,
        max_image_size_mb: float = 5.0,
    ) -> None:
        """Attach to a Notion page for block sync operations.

        Parameters
        ----------
        token
            Notion integration bearer token.
        page_id
            Target page id or URL fragment (normalized internally).
        verbose
            When True, print diagnostic lines to stderr for debugging.
        max_image_size_mb
            Skip uploads larger than this threshold and record a warning.
        """
        from notion_notebook.utils import normalize_page_id

        self._client = Client(auth=token)
        self._page_id = normalize_page_id(page_id)
        self._verbose = verbose
        self._max_bytes = max(0.0, max_image_size_mb) * 1024 * 1024

    @property
    def client(self) -> Client:
        """The underlying ``notion_client.Client`` instance."""
        return self._client

    @property
    def page_id(self) -> str:
        """Normalized page id."""
        return self._page_id

    def validate_page(self) -> bool:
        """Verify the page exists and is readable by the integration.

        Returns
        -------
        bool
            True on success.

        Raises
        ------
        APIResponseError
            When the API returns an error (for example 404 or 403).
        """
        self._with_retry(lambda: self._client.pages.retrieve(self._page_id))
        return True

    def sync_export_blocks(
        self,
        blocks: list[dict[str, Any]],
        figures: list[ExtractedFigure],
        notebook_filename: str,
    ) -> SyncBlocksResult:
        """Delete the previous export region and append resolved ``blocks`` at the managed position.

        Parameters
        ----------
        blocks
            Block payloads, possibly containing ``pending_upload`` placeholders.
        figures
            Figure rows aligned with ``ref`` indices in pending placeholders.
        notebook_filename
            Basename including ``.ipynb`` used to locate the export heading.

        Returns
        -------
        SyncBlocksResult
        """
        errors: list[str] = []
        resolved, img_count, perr = self._resolve_pending_uploads(blocks, figures)
        errors.extend(perr)
        heading = export_heading_text(notebook_filename)
        first_position = self._export_first_insert_position(heading)
        deleted = self._delete_export_section(heading)
        created = self._append_blocks_in_order(resolved, first_position=first_position)
        return SyncBlocksResult(
            success=True,
            blocks_created=created,
            blocks_deleted_old=deleted,
            images_uploaded=img_count,
            errors=errors,
        )

    def upload_image(self, image_bytes: bytes, mime_type: str, filename: str) -> str:
        """Upload bytes via Notion file upload APIs and return the upload id.

        Parameters
        ----------
        image_bytes
            Raw file bytes.
        mime_type
            Content type sent to Notion (for example ``image/png``).
        filename
            Filename hint for the upload.

        Returns
        -------
        str
            ``file_upload`` id suitable for image and files properties.

        Raises
        ------
        APIResponseError
            When the upload fails after retries.
        """
        if len(image_bytes) > self._max_bytes:
            raise ValueError(f"image exceeds max size ({self._max_bytes} bytes)")
        created = self._with_retry(
            lambda: self._client.file_uploads.create(
                filename=filename,
                content_type=mime_type,
            )
        )
        uid = str(created["id"])
        self._with_retry(
            lambda: self._client.file_uploads.send(
                uid,
                file=(filename, image_bytes, mime_type),
            )
        )
        return uid

    def _resolve_pending_uploads(
        self,
        blocks: list[dict[str, Any]],
        figures: list[ExtractedFigure],
    ) -> tuple[list[dict[str, Any]], int, list[str]]:
        out: list[dict[str, Any]] = []
        uploads = 0
        errors: list[str] = []
        for b in blocks:
            if b.get("type") != PENDING_UPLOAD_BLOCK_TYPE:
                out.append(b)
                continue
            ref = b.get("ref")
            if not isinstance(ref, int) or ref < 0 or ref >= len(figures):
                errors.append(f"Invalid pending figure ref {ref!r}.")
                out.extend(
                    [
                        {
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": "(missing figure data)"},
                                    }
                                ]
                            },
                        }
                    ]
                )
                continue
            fig = figures[ref]
            mime = fig.mime_type()
            fname = f"cell{fig.cell_index}-fig{fig.figure_index}.{_ext_for_mime(mime)}"
            try:
                if len(fig.image_data) > self._max_bytes:
                    raise ValueError("figure exceeds max_image_size_mb")
                uid = self.upload_image(fig.image_data, mime, fname)
                uploads += 1
            except Exception as e:
                errors.append(f"Image upload failed: {e!s}")
                out.extend(
                    [
                        {
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": f"(image upload failed: {e})"},
                                    }
                                ]
                            },
                        }
                    ]
                )
                continue
            out.append(
                {
                    "type": "image",
                    "image": {
                        "type": "file_upload",
                        "file_upload": {"id": uid},
                    },
                }
            )
        return out, uploads, errors

    def _export_first_insert_position(self, heading_plain: str) -> dict[str, Any]:
        """Return the Notion ``position`` payload for the first append batch.

        When the managed export heading sits below user blocks, new content is
        inserted after the last user block so free-form Notion content can stay
        at the top. When there is no heading yet, inserts after the last block
        before the first top-level ``child_database`` (typically ``Figures``)
        so the database remains at the bottom. Otherwise uses ``start``.
        """
        children = list(
            collect_paginated_api(
                self._client.blocks.children.list,
                block_id=self._page_id,
                page_size=100,
            )
        )
        first_db = _first_top_level_child_database_index(children)
        if first_db is None:
            first_db = len(children)
        heading_idx = None
        for i, block in enumerate(children):
            if i >= first_db:
                break
            if block.get("type") == "heading_2":
                plain = plain_text_from_rich_block(cast(dict[str, Any], block), "heading_2")
                if plain.strip() == heading_plain:
                    heading_idx = i
                    break
        if heading_idx is not None:
            start_idx = _expand_delete_start_backwards(children, heading_idx)
            if start_idx > 0:
                bid = str(children[start_idx - 1]["id"])
                return {"type": "after_block", "after_block": {"id": bid}}
            return {"type": "start"}
        if first_db > 0:
            bid = str(children[first_db - 1]["id"])
            return {"type": "after_block", "after_block": {"id": bid}}
        return {"type": "start"}

    def _delete_export_section(self, heading_plain: str) -> int:
        children = list(
            collect_paginated_api(
                self._client.blocks.children.list,
                block_id=self._page_id,
                page_size=100,
            )
        )
        first_db = _first_top_level_child_database_index(children)
        if first_db is None:
            first_db = len(children)
        heading_idx = None
        for i, block in enumerate(children):
            if i >= first_db:
                break
            if block.get("type") == "heading_2":
                plain = plain_text_from_rich_block(cast(dict[str, Any], block), "heading_2")
                if plain.strip() == heading_plain:
                    heading_idx = i
                    break
        if heading_idx is None:
            return 0
        start_idx = _expand_delete_start_backwards(children, heading_idx)
        n = 0
        for j in range(first_db - 1, start_idx - 1, -1):
            bid = str(children[j]["id"])
            try:
                self._with_retry(lambda b=bid: self._client.blocks.delete(b))
                n += 1
            except APIResponseError:
                pass
        return n

    def _append_blocks_in_order(
        self,
        blocks: list[dict[str, Any]],
        *,
        first_position: dict[str, Any] | None = None,
    ) -> int:
        total = 0
        after: str | None = None
        pos0 = first_position if first_position is not None else {"type": "start"}
        for off in range(0, len(blocks), BLOCK_BATCH):
            batch = blocks[off : off + BLOCK_BATCH]
            if off == 0:
                resp = cast(
                    dict[str, Any],
                    self._with_retry(
                        lambda p=pos0: self._client.blocks.children.append(
                            self._page_id,
                            children=batch,
                            position=p,
                        )
                    ),
                )
            else:
                assert after is not None
                resp = cast(
                    dict[str, Any],
                    self._with_retry(
                        lambda: self._client.blocks.children.append(
                            self._page_id,
                            children=batch,
                            position={"type": "after_block", "after_block": {"id": after}},
                        )
                    ),
                )
            results = cast(list[dict[str, Any]], resp.get("results") or [])
            if results:
                after = str(results[-1]["id"])
            total += len(batch)
        return total

    def _with_retry(self, fn: Any) -> Any:
        delay = 0.5
        last: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return fn()
            except APIResponseError as e:
                last = e
                code = getattr(e, "code", None)
                if code in ("rate_limited", "conflict_error") or (
                    hasattr(e, "status") and getattr(e, "status", 0) == 429
                ):
                    time.sleep(delay + random.random() * 0.2)
                    delay = min(delay * 2, 8.0)
                    continue
                raise
            except OSError as e:
                last = e
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
        if last:
            raise last
        return None


def _first_top_level_child_database_index(children: list[dict[str, Any]]) -> int | None:
    for i, b in enumerate(children):
        if b.get("type") == "child_database":
            return i
    return None


def _expand_delete_start_backwards(children: list[dict[str, Any]], heading_idx: int) -> int:
    start = heading_idx
    j = heading_idx - 1
    while j >= 0:
        b = children[j]
        bt = b.get("type")
        if bt == "divider":
            start = j
            j -= 1
            continue
        if bt == "callout":
            plain = plain_text_from_rich_block(b, "callout")
            if plain.strip().startswith("Notebook Metadata"):
                start = j
                j -= 1
                continue
        break
    return start


def _ext_for_mime(mime: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }.get(mime, "png")
