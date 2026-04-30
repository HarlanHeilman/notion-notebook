from pathlib import Path

from notion_notebook.local_exporter import LocalNotebookExporter


def _fixture(name: str) -> str:
    return str(Path(__file__).resolve().parent / "fixtures" / name)


def test_local_export_writes_markdown_and_no_figures(tmp_path) -> None:
    md_dir = tmp_path / "markdown"
    fig_dir = tmp_path / "figures"
    exporter = LocalNotebookExporter(
        notebook_output_dir=md_dir,
        figure_output_dir=fig_dir,
        notebook_path=_fixture("simple.ipynb"),
        auto_sync_on_save=False,
    )
    result = exporter.manual_sync()
    assert result.success
    assert result.markdown_path is not None
    md_file = Path(result.markdown_path)
    assert md_file.is_file()
    text = md_file.read_text(encoding="utf-8")
    assert "Notebook export (simple.ipynb)" in text
    assert result.figures_found == 0


def test_local_export_writes_figures_and_links(tmp_path) -> None:
    md_dir = tmp_path / "markdown"
    fig_dir = tmp_path / "figures"
    exporter = LocalNotebookExporter(
        notebook_output_dir=md_dir,
        figure_output_dir=fig_dir,
        notebook_path=_fixture("with_image.ipynb"),
        auto_sync_on_save=False,
    )
    result = exporter.manual_sync()
    assert result.success
    assert result.markdown_path is not None
    md_file = Path(result.markdown_path)
    text = md_file.read_text(encoding="utf-8")
    assert "![Figure](" in text
    figure_subdir = fig_dir / "with_image_figures"
    assert figure_subdir.is_dir()
    assert any(figure_subdir.iterdir())
    assert result.figures_written > 0


def test_local_export_overwrites_single_markdown_file(tmp_path) -> None:
    md_dir = tmp_path / "markdown"
    fig_dir = tmp_path / "figures"
    exporter = LocalNotebookExporter(
        notebook_output_dir=md_dir,
        figure_output_dir=fig_dir,
        notebook_path=_fixture("simple.ipynb"),
        auto_sync_on_save=False,
    )
    first = exporter.manual_sync()
    second = exporter.manual_sync()
    assert first.success and second.success
    assert first.markdown_path == second.markdown_path
    assert len(list(md_dir.glob("*.md"))) == 1


def test_local_exporter_start_stop_lifecycle(tmp_path) -> None:
    exporter = LocalNotebookExporter(
        notebook_output_dir=tmp_path / "markdown",
        figure_output_dir=tmp_path / "figures",
        notebook_path=_fixture("simple.ipynb"),
        auto_sync_on_save=False,
    )
    exporter.start()
    result = exporter.manual_sync()
    exporter.stop()
    assert result.success
