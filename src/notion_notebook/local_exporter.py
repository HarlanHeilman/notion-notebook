"""Orchestrate parse-and-export from notebooks to local markdown and figure files."""

from __future__ import annotations

import hashlib
import threading
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from notion_notebook.config import LocalConfig
from notion_notebook.exceptions import ConfigurationError, NotebookPathError
from notion_notebook.figure_database_manager import ExtractedFigure
from notion_notebook.git_utils import GitContext
from notion_notebook.jupyter_hooks import JupyterHooks, NotebookWatcher
from notion_notebook.notebook_parser import NotebookParser, ParsedNotebook
from notion_notebook.notion_converter import NotionConverter
from notion_notebook.utils import plain_text_from_rich_block


def _figure_file_name(fig: ExtractedFigure) -> str:
    """Return a deterministic figure filename for stable local exports."""
    digest = hashlib.sha256(fig.image_data).hexdigest()[:16]
    return f"cell{fig.cell_index:04d}-fig{fig.figure_index:03d}-{digest}.{fig.image_format}"


def _cell_sources_sha256(parsed: ParsedNotebook) -> str:
    """Return a hash of all cell sources to avoid output-only markdown rewrites."""
    payload = "\0".join(c.source for c in parsed.cells).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class LocalSyncResult:
    """Summary of one notebook-to-local sync attempt.

    Parameters
    ----------
    success
        False when a fatal error prevented export completion.
    timestamp
        UTC time when sync finished.
    cells_processed
        Number of notebook cells considered.
    figures_found
        Number of extracted raster figures.
    markdown_path
        Absolute markdown file path when successful.
    figures_written
        Number of figure files written on this sync.
    errors
        Non-fatal warnings and fatal messages when present.
    """

    success: bool
    timestamp: datetime
    cells_processed: int
    figures_found: int
    markdown_path: str | None
    figures_written: int
    errors: list[str] = field(default_factory=list)


class LocalNotebookExporter:
    """Validate local config, watch notebook files, and export to local markdown."""

    def __init__(
        self,
        *,
        notebook_output_dir: str | Path,
        figure_output_dir: str | Path,
        notebook_name: str = "auto",
        notebook_path: str | None = None,
        auto_sync_on_save: bool = True,
        auto_sync_interval: int | None = None,
        image_format: str = "png",
        include_ai_summaries: bool = True,
        debounce_seconds: float = 2.0,
        config_file: str | Path | None = None,
    ) -> None:
        """Build a local exporter with merged configuration.

        Parameters
        ----------
        notebook_output_dir
            Directory where markdown files are written.
        figure_output_dir
            Directory where extracted figure assets are written.
        notebook_name
            When ``"auto"``, notebook basename is used in metadata heading.
        notebook_path
            Absolute notebook path. When ``None``, resolved at runtime.
        auto_sync_on_save
            When True, register a debounced file watcher after :meth:`start`.
        auto_sync_interval
            Optional seconds between periodic :meth:`manual_sync` calls.
        image_format
            Preferred figure MIME family for multi-output cells.
        include_ai_summaries
            Passed through to :class:`~notion_notebook.notion_converter.NotionConverter`.
        debounce_seconds
            Quiet period for the file watcher before syncing.
        config_file
            Optional JSON path merged before explicit arguments.
        """
        self._cfg = LocalConfig.merge(
            notebook_output_dir=notebook_output_dir,
            figure_output_dir=figure_output_dir,
            auto_sync_on_save=auto_sync_on_save,
            image_format=image_format,
            debounce_seconds=debounce_seconds,
            file_path=config_file,
        )
        self._notebook_name_mode = notebook_name
        self._explicit_notebook_path = notebook_path
        self._auto_sync_interval = auto_sync_interval
        self._include_ai = include_ai_summaries
        self._watcher: NotebookWatcher | None = None
        self._stop_interval = threading.Event()
        self._sync_state_lock = threading.Lock()
        self._last_cell_sources_hash: str | None = None
        self._parser = NotebookParser()
        self._converter = NotionConverter(
            image_format_preference=self._cfg.image_format,
            include_ai_summaries=self._include_ai,
        )

    def start(self) -> None:
        """Resolve notebook path and start watcher/interval automation."""
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
            traceback.print_exc()

    def manual_sync(self) -> LocalSyncResult:
        """Parse the notebook and write markdown and figure assets to local paths."""
        errors: list[str] = []
        ts = datetime.now(UTC)
        try:
            nb_path = getattr(self, "_active_notebook_path", None) or self._resolve_notebook_path_str()
        except NotebookPathError as exc:
            return LocalSyncResult(
                success=False,
                timestamp=ts,
                cells_processed=0,
                figures_found=0,
                markdown_path=None,
                figures_written=0,
                errors=[str(exc)],
            )
        try:
            parsed = self._parser.parse(nb_path)
            meta = GitContext.get_notebook_metadata(Path(nb_path))
            if self._notebook_name_mode == "auto":
                notebook_filename = Path(nb_path).name
            else:
                notebook_filename = str(self._notebook_name_mode).strip()
            blocks, figures = self._converter.blocks_from_notebook(parsed, meta, notebook_filename)
            markdown_file = self._cfg.notebook_output_dir / f"{Path(nb_path).stem}.md"
            figure_rel_dir = f"{Path(nb_path).stem}_figures"
            figure_dir = self._cfg.figure_output_dir / figure_rel_dir
            figure_map = self._write_figures(figures, figure_dir)
            sources_hash = _cell_sources_sha256(parsed)
            with self._sync_state_lock:
                sources_changed = self._last_cell_sources_hash != sources_hash
            if sources_changed:
                markdown = self._blocks_to_markdown(blocks, figure_map, figure_rel_dir)
                markdown_file.parent.mkdir(parents=True, exist_ok=True)
                markdown_file.write_text(markdown, encoding="utf-8")
                with self._sync_state_lock:
                    self._last_cell_sources_hash = sources_hash
            return LocalSyncResult(
                success=True,
                timestamp=datetime.now(UTC),
                cells_processed=len(parsed.cells),
                figures_found=len(figures),
                markdown_path=str(markdown_file),
                figures_written=len(figure_map),
                errors=errors,
            )
        except (ConfigurationError, OSError, ValueError) as exc:
            errors.append(str(exc))
            return LocalSyncResult(
                success=False,
                timestamp=datetime.now(UTC),
                cells_processed=0,
                figures_found=0,
                markdown_path=None,
                figures_written=0,
                errors=errors,
            )

    def stop(self) -> None:
        """Stop file watcher and periodic sync thread."""
        self._stop_interval.set()
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None

    def _write_figures(self, figures: list[ExtractedFigure], figure_dir: Path) -> dict[int, str]:
        figure_dir.mkdir(parents=True, exist_ok=True)
        mapping: dict[int, str] = {}
        for i, fig in enumerate(figures):
            name = _figure_file_name(fig)
            out = figure_dir / name
            out.write_bytes(fig.image_data)
            mapping[i] = name
        return mapping

    def _blocks_to_markdown(
        self,
        blocks: list[dict[str, Any]],
        figure_map: dict[int, str],
        figure_rel_dir: str,
    ) -> str:
        lines: list[str] = []
        for block in blocks:
            btype = str(block.get("type") or "")
            if btype == "heading_2":
                lines.append(f"## {plain_text_from_rich_block(block, 'heading_2')}")
                lines.append("")
            elif btype == "paragraph":
                lines.append(plain_text_from_rich_block(block, "paragraph"))
                lines.append("")
            elif btype == "callout":
                text = plain_text_from_rich_block(block, "callout")
                lines.append("> " + text.replace("\n", "\n> "))
                lines.append("")
            elif btype == "divider":
                lines.append("---")
                lines.append("")
            elif btype == "code":
                code = plain_text_from_rich_block(block, "code")
                lang = ""
                code_inner = block.get("code")
                if isinstance(code_inner, dict):
                    lang_raw = code_inner.get("language")
                    if isinstance(lang_raw, str):
                        lang = lang_raw
                lines.append(f"```{lang}".rstrip())
                lines.append(code)
                lines.append("```")
                lines.append("")
            elif btype == "pending_upload":
                ref = block.get("ref")
                if isinstance(ref, int) and ref in figure_map:
                    fig_rel_path = f"{figure_rel_dir}/{figure_map[ref]}"
                    lines.append(f"![Figure]({fig_rel_path})")
                    lines.append("")
        return "\n".join(lines).rstrip() + "\n"
