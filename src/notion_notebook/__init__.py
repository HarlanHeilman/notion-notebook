"""Export Jupyter notebook content to Notion pages with figures tracking."""

from notion_notebook.exporter import NotebookExporter, SyncResult
from notion_notebook.figure_database_manager import ExtractedFigure, FigureDatabaseManager
from notion_notebook.git_utils import GitContext, NotebookMetadata
from notion_notebook.notebook_parser import NotebookParser, ParsedNotebook

__all__ = [
    "ExtractedFigure",
    "FigureDatabaseManager",
    "GitContext",
    "NotebookExporter",
    "NotebookMetadata",
    "NotebookParser",
    "ParsedNotebook",
    "SyncResult",
]


def main() -> None:
    """Console script entrypoint for ``notion-notebook``."""
    from notion_notebook.exporter import main as _main

    _main()
