"""Figures inline child database lifecycle and append-only figure rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from notion_client.helpers import collect_paginated_api

from notion_notebook.utils import FIGURES_DATABASE_TITLE, child_database_title_equals


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
        Number of figure rows appended (each sync run adds new rows; no in-place
        replacement by cell index).
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

    FIGURES_TITLE = FIGURES_DATABASE_TITLE
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
        :attr:`FIGURES_TITLE`. If none exists, creates an **inline** embedded
        database on the page (``is_inline=True``) with
        ``initial_data_source`` so the UI shows a table on the page, not a
        linked full-page database. Applies any missing columns via
        ``data_sources.update`` when needed.
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
            db_id = existing
        else:
            created = self._notion.databases.create(
                parent={"type": "page_id", "page_id": self._page_id},
                title=[
                    {
                        "type": "text",
                        "text": {"content": self.FIGURES_TITLE},
                    }
                ],
                is_inline=True,
                initial_data_source={
                    "properties": {
                        self.NAME_PROP: {"title": {}},
                        self.IMAGE_PROP: {"files": {}},
                        self.CELL_INDEX_PROP: {"number": {}},
                        self.CODE_PROP: {"rich_text": {}},
                        self.TIMESTAMP_PROP: {"date": {}},
                        self.AI_SUMMARY_PROP: {"rich_text": {}},
                    }
                },
            )
            db_id = str(created["id"])
        ds_id = self._primary_data_source_id(db_id)
        if ds_id:
            self.ensure_figures_schema(ds_id)
        return db_id

    def ensure_figures_schema(self, data_source_id: str) -> None:
        """Add missing figure-row columns on the primary data source.

        Notion applies schema for new databases on the data source; older
        ``databases.create`` payloads may only surface ``Name`` until
        ``data_sources.update`` runs. Idempotent: skips properties that already
        exist.

        Parameters
        ----------
        data_source_id
            Primary data source id from :meth:`_primary_data_source_id`.
        """
        ds = self._notion.data_sources.retrieve(data_source_id)
        props: dict[str, Any] = dict(ds.get("properties") or {})
        need = {
            self.IMAGE_PROP: {"files": {}},
            self.CELL_INDEX_PROP: {"number": {}},
            self.CODE_PROP: {"rich_text": {}},
            self.TIMESTAMP_PROP: {"date": {}},
            self.AI_SUMMARY_PROP: {"rich_text": {}},
        }
        to_add = {k: v for k, v in need.items() if k not in props}
        if to_add:
            self._notion.data_sources.update(data_source_id, properties=to_add)

    def _figures_database_id_from_title(self, children: list[dict[str, Any]]) -> str | None:
        for b in children:
            if child_database_title_equals(b, self.FIGURES_TITLE):
                return str(b["id"])
        return None

    def sync_figures(
        self,
        figures: list[ExtractedFigure],
        figures_db_id: str,
    ) -> SyncFiguresResult:
        """Append one new row per figure for this export run.

        Each sync creates new rows so repeated executions preserve a history of
        plots (same cell index can appear on many rows). Does not update or
        delete prior rows.

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
            try:
                self._notion.pages.create(
                    parent={
                        "type": "data_source_id",
                        "data_source_id": ds_id,
                    },
                    properties=props,
                )
                rows += 1
            except Exception as e:
                errors.append(f"Row create failed (cell {fig.cell_index}): {e!s}")
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

    def _row_properties(self, fig: ExtractedFigure, file_upload_id: str) -> dict[str, Any]:
        base = fig.title or f"Figure {fig.cell_index}_{fig.figure_index}"
        ts = fig.timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        name = f"{base} [{ts}]"
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

