"""Tests for Markdown to Notion block conversion."""

from notion_notebook.markdown_notion import markdown_to_notion_blocks


def test_markdown_heading_and_paragraph() -> None:
    blocks = markdown_to_notion_blocks("# Title\n\nHello **world**.")
    assert blocks[0]["type"] == "heading_1"
    assert blocks[0]["heading_1"]["rich_text"][0]["text"]["content"] == "Title"
    assert blocks[1]["type"] == "paragraph"
    segs = blocks[1]["paragraph"]["rich_text"]
    assert segs[0]["text"]["content"] == "Hello "
    assert segs[1]["annotations"]["bold"] is True
    assert segs[1]["text"]["content"] == "world"


def test_markdown_list_and_code() -> None:
    blocks = markdown_to_notion_blocks("- a\n- b\n\n```py\nx=1\n```")
    assert blocks[0]["type"] == "bulleted_list_item"
    assert blocks[1]["type"] == "bulleted_list_item"
    assert blocks[2]["type"] == "code"
    assert blocks[2]["code"]["language"] == "py"


def test_markdown_table() -> None:
    md = "| h1 | h2 |\n|----|----|\n| v1 | v2 |\n"
    blocks = markdown_to_notion_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "table"
    assert blocks[0]["table"]["table_width"] == 2
    assert blocks[0]["table"]["has_column_header"] is True
    children = blocks[0]["children"]
    assert len(children) == 2
    assert children[0]["type"] == "table_row"
    row0 = children[0]["table_row"]["cells"]
    assert row0[0][0]["text"]["content"] == "h1"


def test_markdown_task_list() -> None:
    blocks = markdown_to_notion_blocks("- [ ] todo\n- [x] done")
    assert blocks[0]["type"] == "to_do"
    assert blocks[0]["to_do"]["checked"] is False
    assert blocks[1]["type"] == "to_do"
    assert blocks[1]["to_do"]["checked"] is True


def test_markdown_empty() -> None:
    assert markdown_to_notion_blocks("   ") == []
    assert markdown_to_notion_blocks("") == []
