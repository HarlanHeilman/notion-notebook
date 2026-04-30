"""Export Jupyter notebook content to Notion pages with figures tracking."""

from notion_notebook.config import parse_page_path_value
from notion_notebook.exporter import NotebookExporter, SyncResult
from notion_notebook.figure_database_manager import ExtractedFigure, FigureDatabaseManager
from notion_notebook.git_utils import GitContext, NotebookMetadata
from notion_notebook.ipython_magic import (
    NotebookMagicResult,
    ensure_ipython_magic_registered,
    register_notebook_magic,
)
from notion_notebook.local_exporter import LocalNotebookExporter, LocalSyncResult
from notion_notebook.notebook_parser import NotebookParser, ParsedNotebook
from notion_notebook.page_resolve import (
    resolve_container_path_and_leaf,
    resolve_database_and_row_by_title,
    resolve_page_by_title_path,
)

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
    "register_notebook_magic",
]

ensure_ipython_magic_registered()


def main() -> None:
    """Console script entrypoint for ``notion-notebook``."""
    from notion_notebook.exporter import main as _main

    _main()
