from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from notion_notebook.figure_database_manager import ExtractedFigure, FigureDatabaseManager


def test_extracted_figure_mime() -> None:
    f = ExtractedFigure(
        cell_index=1,
        figure_index=1,
        image_data=b"x",
        image_format="webp",
        code="c",
        title=None,
        timestamp=datetime.now(UTC),
    )
    assert f.mime_type() == "image/webp"


def test_ensure_figures_database_finds_existing() -> None:
    notion = MagicMock()
    blocks = [
        {
            "id": "db1",
            "type": "child_database",
            "child_database": {"title": "Figures"},
        }
    ]
    with patch(
        "notion_notebook.figure_database_manager.collect_paginated_api",
        return_value=blocks,
    ):
        m = FigureDatabaseManager(notion, "p" * 32)
        db_id = m.ensure_figures_database()
    assert db_id == "db1"
    notion.databases.create.assert_not_called()
