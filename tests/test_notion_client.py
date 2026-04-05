from typing import Any, cast
from unittest.mock import MagicMock, patch

from notion_notebook.figure_database_manager import ExtractedFigure
from notion_notebook.notion_client import NotionPageSync, _expand_delete_start_backwards
from notion_notebook.notion_converter import PENDING_UPLOAD_BLOCK_TYPE
from notion_notebook.utils import export_heading_text


def test_expand_delete_includes_metadata() -> None:
    children = [
        {"id": "m", "type": "callout", "callout": {"rich_text": []}},
        {"id": "h", "type": "heading_2", "heading_2": {"rich_text": []}},
    ]
    start = _expand_delete_start_backwards(children, 1)
    assert start == 1


def test_sync_resolves_pending_uploads() -> None:
    from datetime import UTC, datetime

    fig = ExtractedFigure(
        cell_index=0,
        figure_index=1,
        image_data=b"\x89PNG\r\n\x1a\n",
        image_format="png",
        code="x",
        title=None,
        timestamp=datetime.now(UTC),
    )
    blocks = [
        {"type": "paragraph", "paragraph": {"rich_text": []}},
        {"type": PENDING_UPLOAD_BLOCK_TYPE, "ref": 0},
    ]
    sync = NotionPageSync("secret", "a" * 32, max_image_size_mb=10.0)
    sc = cast(Any, sync)
    sc.upload_image = MagicMock(return_value="upload-1")
    resolved, nimg, errs = sync._resolve_pending_uploads(blocks, [fig])
    assert nimg == 1
    assert not errs
    assert resolved[-1]["type"] == "image"
    assert resolved[-1]["image"]["file_upload"]["id"] == "upload-1"


def test_delete_export_section_deletes_range() -> None:
    heading = export_heading_text("n.ipynb")
    children = [
        {"id": "1", "type": "paragraph", "paragraph": {"rich_text": []}},
        {
            "id": "2",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": heading}}],
            },
        },
        {"id": "3", "type": "paragraph", "paragraph": {"rich_text": []}},
        {"id": "4", "type": "child_database", "child_database": {"title": "Figures"}},
    ]
    client = MagicMock()
    client.blocks.delete = MagicMock(return_value={})
    sync = NotionPageSync.__new__(NotionPageSync)
    sync._client = client
    sync._page_id = "x" * 32
    sync._max_bytes = 1e9
    cast(Any, sync)._with_retry = lambda fn: fn()
    with patch("notion_notebook.notion_client.collect_paginated_api", return_value=children):
        n = NotionPageSync._delete_export_section(sync, heading)
    assert n == 2
    assert client.blocks.delete.call_count == 2


def test_export_first_insert_position_after_user_content() -> None:
    heading = export_heading_text("n.ipynb")
    children = [
        {"id": "u0", "type": "paragraph", "paragraph": {"rich_text": []}},
        {
            "id": "h",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": heading}}],
            },
        },
        {"id": "x", "type": "paragraph", "paragraph": {"rich_text": []}},
        {"id": "db", "type": "child_database", "child_database": {"title": "Figures"}},
    ]
    client = MagicMock()
    sync = NotionPageSync.__new__(NotionPageSync)
    sync._client = client
    sync._page_id = "a" * 32
    cast(Any, sync)._with_retry = lambda fn: fn()
    with patch("notion_notebook.notion_client.collect_paginated_api", return_value=children):
        pos = NotionPageSync._export_first_insert_position(sync, heading)
    assert pos == {"type": "after_block", "after_block": {"id": "u0"}}


def test_export_first_insert_position_before_db_without_heading() -> None:
    children = [
        {"id": "u0", "type": "paragraph", "paragraph": {"rich_text": []}},
        {"id": "db", "type": "child_database", "child_database": {"title": "Figures"}},
    ]
    client = MagicMock()
    sync = NotionPageSync.__new__(NotionPageSync)
    sync._client = client
    sync._page_id = "a" * 32
    cast(Any, sync)._with_retry = lambda fn: fn()
    with patch("notion_notebook.notion_client.collect_paginated_api", return_value=children):
        pos = NotionPageSync._export_first_insert_position(sync, "Notebook export (n.ipynb)")
    assert pos == {"type": "after_block", "after_block": {"id": "u0"}}
