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
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds1"}]}
    notion.data_sources.retrieve.return_value = {
        "properties": {
            "Image": {},
            "Cell Index": {},
            "Code": {},
            "Timestamp": {},
            "AI Summary": {},
        }
    }
    with patch(
        "notion_notebook.figure_database_manager.collect_paginated_api",
        return_value=blocks,
    ):
        m = FigureDatabaseManager(notion, "p" * 32)
        db_id = m.ensure_figures_database()
    assert db_id == "db1"
    notion.databases.create.assert_not_called()
    notion.data_sources.update.assert_not_called()


def test_ensure_figures_schema_adds_missing_columns() -> None:
    notion = MagicMock()
    notion.data_sources.retrieve.return_value = {"properties": {"Name": {}}}
    m = FigureDatabaseManager(notion, "p" * 32)
    m.ensure_figures_schema("ds-1")
    notion.data_sources.update.assert_called_once()
    call_kw = notion.data_sources.update.call_args
    assert call_kw[0][0] == "ds-1"
    props = call_kw[1]["properties"]
    assert "Image" in props and "Cell Index" in props


def test_sync_figures_creates_row_with_data_source_parent() -> None:
    notion = MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds1"}]}
    notion.file_uploads.create.return_value = {"id": "up1"}
    fig = ExtractedFigure(
        cell_index=3,
        figure_index=1,
        image_data=b"x",
        image_format="png",
        code="c",
        title=None,
        timestamp=datetime.now(UTC),
    )
    m = FigureDatabaseManager(notion, "p" * 32)
    r = m.sync_figures([fig], "db1")
    assert r.rows_upserted == 1
    notion.pages.create.assert_called_once()
    parent = notion.pages.create.call_args.kwargs["parent"]
    assert parent["type"] == "data_source_id"
    assert parent["data_source_id"] == "ds1"


def test_ensure_figures_database_create_is_inline_with_initial_data_source() -> None:
    notion = MagicMock()
    notion.databases.create.return_value = {"id": "newdb"}
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds1"}]}
    notion.data_sources.retrieve.return_value = {"properties": {}}
    with patch(
        "notion_notebook.figure_database_manager.collect_paginated_api",
        return_value=[],
    ):
        m = FigureDatabaseManager(notion, "p" * 32)
        db_id = m.ensure_figures_database()
    assert db_id == "newdb"
    notion.databases.create.assert_called_once()
    kw = notion.databases.create.call_args.kwargs
    assert kw.get("is_inline") is True
    assert "initial_data_source" in kw
    assert "properties" in kw["initial_data_source"]


def test_sync_figures_appends_second_row_same_cell() -> None:
    notion = MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds1"}]}
    notion.file_uploads.create.return_value = {"id": "up1"}
    ts = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)
    fig1 = ExtractedFigure(
        cell_index=2,
        figure_index=1,
        image_data=b"a",
        image_format="png",
        code="c1",
        title="Plot A",
        timestamp=ts,
    )
    fig2 = ExtractedFigure(
        cell_index=2,
        figure_index=1,
        image_data=b"b",
        image_format="png",
        code="c2",
        title="Plot A",
        timestamp=ts,
    )
    m = FigureDatabaseManager(notion, "p" * 32)
    r = m.sync_figures([fig1, fig2], "db1")
    assert r.rows_upserted == 2
    assert notion.pages.create.call_count == 2
    notion.pages.update.assert_not_called()


def test_sync_figures_empty_returns_ok() -> None:
    notion = MagicMock()
    m = FigureDatabaseManager(notion, "p" * 32)
    r = m.sync_figures([], "db1")
    assert r.success and r.rows_upserted == 0
    notion.pages.create.assert_not_called()


def test_sync_figures_errors_when_no_data_source() -> None:
    notion = MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": []}
    fig = ExtractedFigure(
        cell_index=1,
        figure_index=1,
        image_data=b"x",
        image_format="png",
        code="c",
        title=None,
        timestamp=datetime.now(UTC),
    )
    m = FigureDatabaseManager(notion, "p" * 32)
    r = m.sync_figures([fig], "db1")
    assert not r.success
    assert r.errors
