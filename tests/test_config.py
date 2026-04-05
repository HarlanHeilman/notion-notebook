import pytest

from notion_notebook.config import Config, parse_page_path_value
from notion_notebook.exceptions import ConfigurationError


def test_parse_page_path_slash() -> None:
    assert parse_page_path_value("A/B/C") == ("A", "B", "C")


def test_parse_page_path_json_array() -> None:
    assert parse_page_path_value('["One", "Two"]') == ("One", "Two")


def test_parse_page_path_sequence() -> None:
    assert parse_page_path_value(["x", "y"]) == ("x", "y")


def test_config_merge_accepts_root_and_path() -> None:
    c = Config.merge(
        notion_token="tok",
        notion_page_root="https://www.notion.so/w/X-1234567890abcdef1234567890abcdef",
        notion_page_path="Area/Task",
    )
    assert c.default_page_id is None
    assert c.page_root is not None
    assert c.page_path == ("Area", "Task")


def test_config_merge_database_row() -> None:
    c = Config.merge(
        notion_token="tok",
        notion_database_title="Notion Notebook Demmo",
        notion_row_title="Simple Example With No plotting",
    )
    assert c.database_title == "Notion Notebook Demmo"
    assert c.row_title == "Simple Example With No plotting"
    assert c.default_page_id is None


def test_config_merge_container_and_leaf() -> None:
    c = Config.merge(
        notion_token="tok",
        notion_container_path="Research Projects/All Projects",
        notion_leaf_title="Figure (XRR Comparison for each model)",
    )
    assert c.container_path == ("Research Projects", "All Projects")
    assert c.leaf_title == "Figure (XRR Comparison for each model)"


def test_config_merge_id_wins_over_other_keys() -> None:
    c = Config.merge(
        notion_token="tok",
        notion_page_id="https://www.notion.so/x-1234567890abcdef1234567890abcdef",
        notion_database_title="Should be cleared",
        notion_row_title="Row",
    )
    assert c.default_page_id is not None
    assert c.database_title is None
    assert c.row_title is None


def test_config_merge_partial_database_raises() -> None:
    with pytest.raises(ConfigurationError, match="row_title"):
        Config.merge(
            notion_token="tok",
            notion_database_title="OnlyDb",
        )


def test_config_merge_database_id_and_row() -> None:
    c = Config.merge(
        notion_token="tok",
        notion_database_id="33994372421b80c69d83de274672c2da",
        notion_row_title="A task",
    )
    assert c.database_id is not None
    assert c.row_title == "A task"
    assert c.database_title is None


def test_config_merge_partial_container_raises() -> None:
    with pytest.raises(ConfigurationError, match="container_path and leaf_title"):
        Config.merge(
            notion_token="tok",
            notion_leaf_title="Only leaf",
        )
