"""Figures child database lifecycle and row upserts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from notion_client.helpers import collect_paginated_api


@dataclass
class ExtractedFigure:
    """One raster figure extracted from a code cell output.

    Parameters
    ----------
    cell_index
        Notebook cell index containing the figure.
    figure_index
        One-based index among image outputs in that cell for this sync.
    image_data
        Raw image bytes in ``image_format`` encoding.
    image_format
        File format: ``png``, ``jpg``, or ``webp``.
    code
        Full source of the parent code cell.
    title
        Parsed ``plt.title`` text when detectable; otherwise ``None``.
    timestamp
        UTC time assigned at extraction.
    """

    cell_index: int
    figure_index: int
    image_data: bytes
    image_format: str
    code: str
    title: str | None
    timestamp: datetime

    def mime_type(self) -> str:
        """Return the MIME type string for this figure's format."""
        return {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }.get(self.image_format.lower(), "image/png")


@dataclass
class SyncFiguresResult:
    """Summary of a figures database sync attempt.

    Parameters
    ----------
    success
        True when no fatal errors occurred.
    rows_upserted
        Number of figure rows created or updated.
    images_uploaded
        Successful file uploads to Notion for figure files properties.
    errors
        Human-readable failure messages; sync may be partial when non-empty.
    """

    success: bool
    rows_upserted: int
    images_uploaded: int
    errors: list[str] = field(default_factory=list)


class FigureDatabaseManager:
    """Manage a ``Figures`` child database and rows for notebook exports."""

    FIGURES_TITLE = "Figures"
    NAME_PROP = "Name"
    IMAGE_PROP = "Image"
    CELL_INDEX_PROP = "Cell Index"
    CODE_PROP = "Code"
    TIMESTAMP_PROP = "Timestamp"
    AI_SUMMARY_PROP = "AI Summary"

    def __init__(self, notion: Any, page_id: str, *, verbose: bool = False) -> None:
        """Store the Notion client and parent page id for database operations.

        Parameters
        ----------
        notion
            ``notion_client.Client`` instance.
        page_id
            Normalized parent page id containing (or receiving) the figures database.
        verbose
            When True, log progress to stderr.
        """
        self._notion = notion
        self._page_id = page_id
        self._verbose = verbose

    def ensure_figures_database(self) -> str:
        """Create a ``Figures`` child database under the page when missing.

        Returns
        -------
        str
            Database id (UUID string) for the figures database.

        Notes
        -----
        Searches top-level page children for a ``child_database`` titled
        :attr:`FIGURES_TITLE`. If none exists, creates one via the API and
        applies a minimal schema via ``data_sources.update``.
        """
        children = list(
            collect_paginated_api(
                self._notion.blocks.children.list,
                block_id=self._page_id,
                page_size=100,
            )
        )
        existing = self._figures_database_id_from_title(children)
        if existing:
            return existing
        created = self._notion.databases.create(
            parent={"type": "page_id", "page_id": self._page_id},
            title=[
                {
                    "type": "text",
                    "text": {"content": self.FIGURES_TITLE},
                }
            ],
            properties={
                self.NAME_PROP: {"title": {}},
                self.IMAGE_PROP: {"files": {}},
                self.CELL_INDEX_PROP: {"number": {}},
                self.CODE_PROP: {"rich_text": {}},
                self.TIMESTAMP_PROP: {"date": {}},
                self.AI_SUMMARY_PROP: {"rich_text": {}},
            },
        )
        return str(created["id"])

    def _figures_database_id_from_title(self, children: list[dict[str, Any]]) -> str | None:
        for b in children:
            if b.get("type") != "child_database":
                continue
            cd = b.get("child_database") or {}
            title = cd.get("title")
            if isinstance(title, str) and title.strip() == self.FIGURES_TITLE:
                return str(b["id"])
        return None

    def sync_figures(
        self,
        figures: list[ExtractedFigure],
        figures_db_id: str,
    ) -> SyncFiguresResult:
        """Create or update rows keyed by cell index for each figure.

        Parameters
        ----------
        figures
            Extracted figures for the current notebook export.
        figures_db_id
            Target database id from :meth:`ensure_figures_database`.

        Returns
        -------
        SyncFiguresResult
        """
        errors: list[str] = []
        rows = 0
        uploads = 0
        if not figures:
            return SyncFiguresResult(success=True, rows_upserted=0, images_uploaded=0, errors=[])
        ds_id = self._primary_data_source_id(figures_db_id)
        if not ds_id:
            errors.append("Could not resolve data source for figures database.")
            return SyncFiguresResult(success=False, rows_upserted=0, images_uploaded=0, errors=errors)
        for fig in figures:
            try:
                uid = self._upload_file(
                    fig.image_data,
                    fig.mime_type(),
                    f"fig-c{fig.cell_index}-{fig.figure_index}",
                )
                uploads += 1
            except Exception as e:
                errors.append(f"Figure upload failed (cell {fig.cell_index}): {e!s}")
                continue
            props = self._row_properties(fig, uid)
            page_id = self._find_row_for_cell(ds_id, fig.cell_index)
            try:
                if page_id:
                    self._notion.pages.update(page_id, properties=props)
                else:
                    self._notion.pages.create(
                        parent={"database_id": figures_db_id},
                        properties=props,
                    )
                rows += 1
            except Exception as e:
                errors.append(f"Row upsert failed (cell {fig.cell_index}): {e!s}")
        return SyncFiguresResult(
            success=len(errors) == 0,
            rows_upserted=rows,
            images_uploaded=uploads,
            errors=errors,
        )

    def trigger_ai_summaries(self, figures_db_id: str) -> None:
        """Queue AI summary generation for figure rows.

        Parameters
        ----------
        figures_db_id
            Database id (unused for API no-op).

        Notes
        -----
        Notion does not expose a public API to trigger AI property fill. This
        method is a documented no-op; product-side AI may still populate the
        ``AI Summary`` field when configured in the workspace.
        """
        _ = figures_db_id

    def _primary_data_source_id(self, database_id: str) -> str | None:
        meta = self._notion.databases.retrieve(database_id)
        sources = meta.get("data_sources") or []
        if not sources:
            return None
        return str(sources[0]["id"])

    def _find_row_for_cell(self, data_source_id: str, cell_index: int) -> str | None:
        filt = {
            "property": self.CELL_INDEX_PROP,
            "number": {"equals": float(cell_index)},
        }
        resp = self._notion.data_sources.query(data_source_id, filter=filt, page_size=5)
        results = resp.get("results") or []
        if not results:
            return None
        return str(results[0]["id"])

    def _row_properties(self, fig: ExtractedFigure, file_upload_id: str) -> dict[str, Any]:
        name = fig.title or f"Figure {fig.cell_index}_{fig.figure_index}"
        date_s = fig.timestamp.astimezone(UTC).date().isoformat()
        return {
            self.NAME_PROP: {"title": [{"text": {"content": name[:2000]}}]},
            self.IMAGE_PROP: {
                "files": [
                    {
                        "type": "file_upload",
                        "file_upload": {"id": file_upload_id},
                    }
                ]
            },
            self.CELL_INDEX_PROP: {"number": float(fig.cell_index)},
            self.CODE_PROP: {
                "rich_text": [{"text": {"content": fig.code[:2000]}}],
            },
            self.TIMESTAMP_PROP: {"date": {"start": date_s}},
            self.AI_SUMMARY_PROP: {"rich_text": []},
        }

    def _upload_file(self, raw: bytes, content_type: str, filename: str) -> str:
        created = self._notion.file_uploads.create(filename=filename, content_type=content_type)
        uid = str(created["id"])
        self._notion.file_uploads.send(uid, file=(filename, raw, content_type))
        return uid

