"""Orchestrate parsing, conversion, and Notion sync for Jupyter notebooks."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from notion_client.errors import APIResponseError

from notion_notebook.config import Config
from notion_notebook.exceptions import ConfigurationError, NotebookPathError
from notion_notebook.extracted_figure import ExtractedFigure
from notion_notebook.figure_database_manager import FigureDatabaseManager
from notion_notebook.git_utils import GitContext
from notion_notebook.jupyter_hooks import JupyterHooks, NotebookWatcher
from notion_notebook.notebook_parser import NotebookParser, ParsedNotebook
from notion_notebook.notion_client import NotionPageSync, SyncBlocksResult
from notion_notebook.notion_converter import NotionConverter
from notion_notebook.utils import normalize_page_id


def _figure_sync_key(fig: ExtractedFigure) -> str:
    """Return a stable id for deduplicating figure rows across sync runs."""
    digest = hashlib.sha256(
        f"{fig.cell_index}\0{fig.figure_index}\0".encode("utf-8") + fig.image_data
    ).hexdigest()
    return digest


def _cell_sources_sha256(parsed: ParsedNotebook) -> str:
    """Return a hash of all cell sources so output-only notebook writes are ignored."""
    payload = json.dumps([c.source for c in parsed.cells], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class SyncResult:
    """Summary of one notebook-to-Notion sync attempt.

    Parameters
    ----------
    success
        False when a fatal error prevented completing the export.
    timestamp
        UTC time when the sync finished.
    cells_processed
        Number of notebook cells considered.
    figures_found
        Number of extracted raster figures.
    blocks_created
        Notion blocks appended for the export body (after pending resolution).
    images_uploaded
        Successful image file uploads for inline images and figure rows.
    errors
        Warnings and non-fatal failures (image skips, partial API errors).
    """

    success: bool
    timestamp: datetime
    cells_processed: int
    figures_found: int
    blocks_created: int
    images_uploaded: int
    errors: list[str] = field(default_factory=list)


class NotebookExporter:
    """Validate configuration, watch the notebook file, and sync to Notion."""

    def __init__(
        self,
        notion_token: str,
        notion_page_id: str | None = None,
        *,
        notion_page_root: str | None = None,
        notion_page_path: str | list[str] | tuple[str, ...] | None = None,
        notion_database_title: str | None = None,
        notion_row_title: str | None = None,
        notion_container_path: str | list[str] | tuple[str, ...] | None = None,
        notion_leaf_title: str | None = None,
        notion_database_id: str | None = None,
        notebook_name: str = "auto",
        notebook_path: str | None = None,
        auto_sync_on_save: bool = True,
        auto_sync_interval: int | None = None,
        image_format: str = "png",
        include_ai_summaries: bool = True,
        debounce_seconds: float = 2.0,
        verbose: bool = False,
        max_image_size_mb: float = 5.0,
        config_file: str | Path | None = None,
    ) -> None:
        """Build an exporter using merged config and explicit overrides.

        Parameters
        ----------
        notion_token
            Notion integration token (overrides env and config file).
        notion_page_id
            Target page id or URL; omit when using ``notion_page_root`` and
            ``notion_page_path``.
        notion_page_root
            Root page id or URL for hierarchical resolution.
        notion_page_path
            Title path under the root (slash-separated string, sequence, or JSON).
        notion_database_title
            Database title for row lookup (with ``notion_row_title``).
        notion_row_title
            Row title within that database.
        notion_container_path
            Search-first container path (with ``notion_leaf_title``).
        notion_leaf_title
            Final child page or database row title.
        notion_database_id
            Database id or URL with ``notion_row_title`` (skips database title search).
        notebook_name
            When ``\"auto\"``, the basename of the resolved notebook path is used
            for export headings; otherwise this string must include ``.ipynb``.
        notebook_path
            Absolute path to the notebook; when ``None``, resolved at ``start()``
            via :meth:`~notion_notebook.jupyter_hooks.JupyterHooks.get_notebook_path`.
        auto_sync_on_save
            When True, start a debounced file watcher after :meth:`start`.
        auto_sync_interval
            Optional seconds between periodic :meth:`manual_sync` calls; uses a
            background thread when set.
        image_format
            Preferred figure MIME family for multi-output cells (``png``, ``jpg``, ``webp``).
        include_ai_summaries
            Passed to :class:`~notion_notebook.notion_converter.NotionConverter`.
        debounce_seconds
            Quiet period for the file watcher before syncing.
        verbose
            When True, print tracebacks and diagnostics to stderr.
        max_image_size_mb
            Maximum image size for Notion uploads.
        config_file
            Optional JSON path merged before explicit token and page id.
        """
        self._cfg = Config.merge(
            notion_token=notion_token,
            notion_page_id=notion_page_id,
            notion_page_root=notion_page_root,
            notion_page_path=notion_page_path,
            notion_database_title=notion_database_title,
            notion_row_title=notion_row_title,
            notion_container_path=notion_container_path,
            notion_leaf_title=notion_leaf_title,
            notion_database_id=notion_database_id,
            file_path=config_file,
            auto_sync_on_save=auto_sync_on_save,
            image_format=image_format,
            max_image_size_mb=max_image_size_mb,
            debounce_seconds=debounce_seconds,
        )
        self._cached_page_id: str | None = None
        self._notebook_name_mode = notebook_name
        self._explicit_notebook_path = notebook_path
        self._auto_sync_interval = auto_sync_interval
        self._include_ai = include_ai_summaries
        self._verbose = verbose
        self._watcher: NotebookWatcher | None = None
        self._timer: threading.Timer | None = None
        self._stop_interval = threading.Event()
        self._sync_state_lock = threading.Lock()
        self._last_cell_sources_hash: str | None = None
        self._synced_figure_keys: set[str] = set()
        self._parser = NotebookParser()
        self._converter = NotionConverter(
            image_format_preference=self._cfg.image_format,
            include_ai_summaries=self._include_ai,
        )

    def _resolved_page_id(self) -> str:
        """Return the target page id, resolving title path on first use."""
        if self._cached_page_id is not None:
            return self._cached_page_id
        from notion_notebook.page_resolve import (
            resolve_container_path_and_leaf,
            resolve_database_and_row_by_title,
            resolve_page_by_title_path,
        )

        cfg = self._cfg
        if cfg.default_page_id:
            pid = normalize_page_id(cfg.default_page_id)
        elif (cfg.database_title and cfg.row_title) or (
            cfg.database_id and cfg.row_title
        ):
            pid = resolve_database_and_row_by_title(
                cfg.notion_token,
                cfg.database_title or "",
                cfg.row_title,
                database_id=cfg.database_id,
            )
        elif cfg.container_path and cfg.leaf_title:
            pid = resolve_container_path_and_leaf(
                cfg.notion_token,
                cfg.container_path,
                cfg.leaf_title,
            )
        else:
            root = cfg.page_root or ""
            pid = resolve_page_by_title_path(cfg.notion_token, root, cfg.page_path)
        self._cached_page_id = pid
        return pid

    def start(self) -> None:
        """Validate the Notion page, resolve the notebook path, and begin automation.

        Raises
        ------
        ConfigurationError
            When the page id or token is unusable.
        NotebookPathError
            When the notebook path cannot be resolved.
        APIResponseError
            When Notion rejects the integration for the target page.
        """
        page_id = self._resolved_page_id()
        sync = NotionPageSync(
            self._cfg.notion_token,
            page_id,
            verbose=self._verbose,
            max_image_size_mb=self._cfg.max_image_size_mb,
        )
        sync.validate_page()
        nb_path = self._resolve_notebook_path_str()
        self._active_notebook_path = nb_path
        if self._cfg.auto_sync_on_save:
            self._watcher = NotebookWatcher(
                nb_path,
                self._safe_manual_sync,
                debounce_seconds=self._cfg.debounce_seconds,
            )
            self._watcher.start()
        JupyterHooks.register_save_hook(self._safe_manual_sync)
        if self._auto_sync_interval and self._auto_sync_interval > 0:
            self._stop_interval.clear()
            threading.Thread(target=self._interval_loop, daemon=True).start()

    def _interval_loop(self) -> None:
        interval = float(self._auto_sync_interval or 0)
        while not self._stop_interval.wait(timeout=interval):
            self._safe_manual_sync()

    def _resolve_notebook_path_str(self) -> str:
        if self._explicit_notebook_path:
            p = Path(self._explicit_notebook_path).expanduser().resolve()
            if not p.is_file():
                raise NotebookPathError(f"Notebook not found: {p}")
            return str(p)
        found = JupyterHooks.get_notebook_path()
        if not found:
            raise NotebookPathError(
                "Could not resolve notebook path; pass notebook_path= or set NOTION_NOTEBOOK_PATH."
            )
        return str(Path(found).resolve())

    def _safe_manual_sync(self) -> None:
        try:
            self.manual_sync()
        except Exception:
            if self._verbose:
                traceback.print_exc(file=sys.stderr)

    def manual_sync(self) -> SyncResult:
        """Parse the notebook, push blocks and figures to Notion, and return a summary.

        Replaces the managed export block range only when the concatenation of all
        cell sources changes, so filesystem events that only refresh outputs (for
        example after running a plotting cell) update the ``Figures`` table without
        deleting and re-uploading the inline export body. New figure rows are appended
        for image outputs whose bytes have not been synced successfully in this
        process; figure dedupe state resets when the exporter process restarts.

        Returns
        -------
        SyncResult
            ``success`` is False when a fatal error occurs; partial failures appear
            in ``errors`` without raising into the kernel.
        """
        errors: list[str] = []
        ts = datetime.now(UTC)
        try:
            nb_path = getattr(self, "_active_notebook_path", None) or self._resolve_notebook_path_str()
        except NotebookPathError as e:
            return SyncResult(
                success=False,
                timestamp=ts,
                cells_processed=0,
                figures_found=0,
                blocks_created=0,
                images_uploaded=0,
                errors=[str(e)],
            )
        page_id = self._resolved_page_id()
        fname = Path(nb_path).name
        if self._notebook_name_mode == "auto":
            name_for_heading = fname
        else:
            name_for_heading = str(self._notebook_name_mode).strip()
        try:
            parsed = self._parser.parse(nb_path)
            meta = GitContext.get_notebook_metadata(Path(nb_path))
            blocks, figures = self._converter.blocks_from_notebook(parsed, meta, name_for_heading)
            sources_hash = _cell_sources_sha256(parsed)
            sync = NotionPageSync(
                self._cfg.notion_token,
                page_id,
                verbose=self._verbose,
                max_image_size_mb=self._cfg.max_image_size_mb,
            )
            with self._sync_state_lock:
                sources_changed = self._last_cell_sources_hash != sources_hash
            if sources_changed:
                br = sync.sync_export_blocks(blocks, figures, name_for_heading)
                errors.extend(br.errors)
                with self._sync_state_lock:
                    self._last_cell_sources_hash = sources_hash
            else:
                br = SyncBlocksResult(
                    success=True,
                    blocks_created=0,
                    blocks_deleted_old=0,
                    images_uploaded=0,
                    errors=[],
                )
            new_figs: list[ExtractedFigure] = []
            with self._sync_state_lock:
                for fig in figures:
                    if _figure_sync_key(fig) not in self._synced_figure_keys:
                        new_figs.append(fig)
            fmgr = FigureDatabaseManager(sync.client, page_id, verbose=self._verbose)
            db_id = fmgr.ensure_figures_database()
            if new_figs:
                fr = fmgr.sync_figures(new_figs, db_id)
                errors.extend(fr.errors)
                if fr.success:
                    with self._sync_state_lock:
                        for fig in new_figs:
                            self._synced_figure_keys.add(_figure_sync_key(fig))
                fmgr.trigger_ai_summaries(db_id)
                imgs = br.images_uploaded + fr.images_uploaded
            else:
                imgs = br.images_uploaded
            return SyncResult(
                success=True,
                timestamp=datetime.now(UTC),
                cells_processed=len(parsed.cells),
                figures_found=len(figures),
                blocks_created=br.blocks_created,
                images_uploaded=imgs,
                errors=errors,
            )
        except (APIResponseError, ConfigurationError, OSError, ValueError) as e:
            errors.append(str(e))
            return SyncResult(
                success=False,
                timestamp=datetime.now(UTC),
                cells_processed=0,
                figures_found=0,
                blocks_created=0,
                images_uploaded=0,
                errors=errors,
            )

    def stop(self) -> None:
        """Stop the file watcher and periodic sync thread."""
        self._stop_interval.set()
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


def main() -> None:
    """CLI entrypoint: print usage (optional integration token via env)."""
    print(
        "notion-notebook: import NotebookExporter from notion_notebook in a notebook "
        "or pass NOTION_TOKEN and NOTION_PAGE_ID for programmatic use.",
        file=sys.stderr,
    )
