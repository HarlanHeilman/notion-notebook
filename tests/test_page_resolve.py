from unittest.mock import MagicMock, patch

import pytest

from notion_notebook.page_resolve import (
    resolve_container_path_and_leaf,
    resolve_database_and_row_by_title,
    resolve_page_by_title_path,
)


def test_resolve_page_by_title_path_single_segment() -> None:
    with patch("notion_notebook.page_resolve.collect_paginated_api") as cp:
        cp.return_value = [
            {
                "id": "a" * 32,
                "type": "child_page",
                "child_page": {"title": "Leaf"},
            }
        ]
        out = resolve_page_by_title_path("secret", "b" * 32, ("Leaf",))
    assert out == "a" * 32


def test_resolve_page_by_title_path_not_found() -> None:
    with patch("notion_notebook.page_resolve.collect_paginated_api") as cp:
        cp.return_value = []
        with pytest.raises(ValueError, match="No child page"):
            resolve_page_by_title_path("secret", "b" * 32, ("Missing",))


def test_resolve_page_by_title_path_empty_segments() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        resolve_page_by_title_path("secret", "b" * 32, ())


def test_resolve_database_and_row_by_title() -> None:
    notion = MagicMock()
    notion.search.return_value = {
        "results": [
            {
                "object": "data_source",
                "id": "0" * 32,
                "title": [{"plain_text": "Demmo", "type": "text"}],
                "parent": {"type": "database_id", "database_id": "d" * 32},
            }
        ],
        "next_cursor": None,
    }
    notion.databases.retrieve.return_value = {
        "data_sources": [{"id": "ds1"}],
    }
    notion.data_sources.retrieve.return_value = {
        "properties": {"Task name": {"type": "title"}},
    }
    notion.data_sources.query.return_value = {
        "results": [{"id": "e" * 32}],
        "next_cursor": None,
    }
    with patch("notion_notebook.page_resolve.Client", return_value=notion):
        out = resolve_database_and_row_by_title("t", "Demmo", "My row")
    assert out == "e" * 32


def test_resolve_database_and_row_by_explicit_database_id() -> None:
    notion = MagicMock()
    notion.databases.retrieve.return_value = {
        "data_sources": [{"id": "ds1"}],
    }
    notion.data_sources.retrieve.return_value = {
        "properties": {"Name": {"type": "title"}},
    }
    notion.data_sources.query.return_value = {
        "results": [{"id": "e" * 32}],
        "next_cursor": None,
    }
    with patch("notion_notebook.page_resolve.Client", return_value=notion):
        out = resolve_database_and_row_by_title(
            "t",
            "",
            "My row",
            database_id="d" * 32,
        )
    assert out == "e" * 32
    notion.search.assert_not_called()


def test_resolve_container_path_database_leaf() -> None:
    notion = MagicMock()
    notion.search.return_value = {
        "results": [
            {
                "object": "page",
                "id": "p" * 32,
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [{"plain_text": "Research Projects", "type": "text"}],
                    }
                },
            }
        ]
    }
    notion.blocks.children.list.return_value = {
        "has_more": False,
        "results": [
            {
                "id": "d" * 32,
                "type": "child_database",
                "child_database": {"title": "All Projects"},
            }
        ],
    }
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds1"}]}
    notion.data_sources.retrieve.return_value = {
        "properties": {"Name": {"type": "title"}},
    }
    notion.data_sources.query.return_value = {
        "results": [{"id": "f" * 32}],
        "next_cursor": None,
    }
    with patch("notion_notebook.page_resolve.collect_paginated_api") as cp:
        cp.side_effect = [
            [
                {
                    "id": "d" * 32,
                    "type": "child_database",
                    "child_database": {"title": "All Projects"},
                }
            ],
        ]
        with patch("notion_notebook.page_resolve.Client", return_value=notion):
            out = resolve_container_path_and_leaf(
                "t",
                ("Research Projects", "All Projects"),
                "Leaf task",
            )
    assert out == "f" * 32
