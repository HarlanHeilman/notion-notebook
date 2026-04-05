from pathlib import Path

from notion_notebook.git_utils import GitContext


def test_find_git_root_in_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nb = tmp_path / "a.ipynb"
    nb.write_text("{}", encoding="utf-8")
    root = GitContext.find_git_root(nb)
    assert root == tmp_path.resolve()


def test_find_git_root_outside(tmp_path: Path) -> None:
    nb = tmp_path / "a.ipynb"
    nb.write_text("{}", encoding="utf-8")
    assert GitContext.find_git_root(nb) is None


def test_get_relative_path(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "notebooks"
    sub.mkdir()
    nb = sub / "a.ipynb"
    nb.write_text("{}", encoding="utf-8")
    rel = GitContext.get_relative_path(nb.resolve(), tmp_path.resolve())
    assert rel == "notebooks/a.ipynb"


def test_get_notebook_metadata(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nb = tmp_path / "n.ipynb"
    nb.write_text("{}", encoding="utf-8")
    m = GitContext.get_notebook_metadata(nb)
    assert m.notebook_name == "n"
    assert m.notebook_path == "n.ipynb"
    assert m.file_path.resolve() == nb.resolve()
