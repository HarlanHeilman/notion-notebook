from pathlib import Path

from notion_notebook.notebook_parser import NotebookParser


def test_parse_simple_notebook() -> None:
    root = Path(__file__).resolve().parent
    p = root / "fixtures" / "simple.ipynb"
    nb = NotebookParser().parse(p)
    assert nb.name == "simple"
    assert len(nb.cells) == 2
    assert nb.cells[0].cell_type == "markdown"
    assert nb.cells[1].cell_type == "code"
    assert nb.cells[1].outputs[0].output_type == "stream"
