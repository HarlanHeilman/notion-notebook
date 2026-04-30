"""Export Jupyter notebook content to Notion pages with figures tracking."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from notion_notebook.config import parse_page_path_value
from notion_notebook.extracted_figure import ExtractedFigure
from notion_notebook.git_utils import GitContext, NotebookMetadata
from notion_notebook.ipython_magic import (
    NotebookMagicResult,
    ensure_ipython_magic_registered,
    ensure_nbexp_magic_registered,
    register_nbexp_magic,
    register_notebook_magic,
)
from notion_notebook.local_exporter import LocalNotebookExporter, LocalSyncResult
from notion_notebook.notebook_parser import NotebookParser, ParsedNotebook

if TYPE_CHECKING:
    from notion_notebook.exporter import NotebookExporter, SyncResult
    from notion_notebook.figure_database_manager import FigureDatabaseManager

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "NotebookExporter": ("notion_notebook.exporter", "NotebookExporter"),
    "SyncResult": ("notion_notebook.exporter", "SyncResult"),
    "FigureDatabaseManager": ("notion_notebook.figure_database_manager", "FigureDatabaseManager"),
    "resolve_container_path_and_leaf": (
        "notion_notebook.page_resolve",
        "resolve_container_path_and_leaf",
    ),
    "resolve_database_and_row_by_title": (
        "notion_notebook.page_resolve",
        "resolve_database_and_row_by_title",
    ),
    "resolve_page_by_title_path": (
        "notion_notebook.page_resolve",
        "resolve_page_by_title_path",
    ),
}

__all__ = [
    "ExtractedFigure",
    "FigureDatabaseManager",
    "GitContext",
    "LocalNotebookExporter",
    "LocalSyncResult",
    "NotebookMagicResult",
    "NotebookExporter",
    "NotebookMetadata",
    "NotebookParser",
    "ParsedNotebook",
    "SyncResult",
    "parse_page_path_value",
    "resolve_container_path_and_leaf",
    "resolve_database_and_row_by_title",
    "resolve_page_by_title_path",
    "ensure_ipython_magic_registered",
    "ensure_nbexp_magic_registered",
    "register_nbexp_magic",
    "register_notebook_magic",
]


def __getattr__(name: str) -> Any:
    """Load Notion-dependent symbols only when accessed."""
    spec = _LAZY_EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = spec
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def __dir__() -> list[str]:
    return sorted(set(__all__))


ensure_nbexp_magic_registered()


def main() -> None:
    """Console script entrypoint for ``notion-notebook``."""
    from notion_notebook.exporter import main as _main

    _main()
