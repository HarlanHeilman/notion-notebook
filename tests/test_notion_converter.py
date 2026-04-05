from datetime import UTC, datetime
from pathlib import Path

from notion_notebook.git_utils import NotebookMetadata
from notion_notebook.notebook_parser import NotebookParser
from notion_notebook.notion_converter import NotionConverter, PENDING_UPLOAD_BLOCK_TYPE


def test_blocks_include_metadata_and_heading() -> None:
    root = Path(__file__).resolve().parent
    p = root / "fixtures" / "simple.ipynb"
    parsed = NotebookParser().parse(p)
    meta = NotebookMetadata(
        last_sync=datetime.now(UTC),
        notebook_path="fixtures/simple.ipynb",
        github_remote=None,
        notebook_name="simple",
        file_path=p.resolve(),
    )
    conv = NotionConverter()
    blocks, figures = conv.blocks_from_notebook(parsed, meta, "simple.ipynb")
    assert blocks[0]["type"] == "callout"
    assert blocks[1]["type"] == "heading_2"
    assert not figures


def test_pending_for_png_output() -> None:
    parsed = NotebookParser().parse(
        Path(__file__).resolve().parent / "fixtures" / "with_image.ipynb"
    )
    meta = NotebookMetadata(
        last_sync=datetime.now(UTC),
        notebook_path="x.ipynb",
        github_remote=None,
        notebook_name="x",
        file_path=Path("/tmp/x.ipynb"),
    )
    conv = NotionConverter()
    blocks, figures = conv.blocks_from_notebook(parsed, meta, "with_image.ipynb")
    pending = [b for b in blocks if b.get("type") == PENDING_UPLOAD_BLOCK_TYPE]
    assert len(pending) == len(figures)
    assert figures[0].image_format == "png"
