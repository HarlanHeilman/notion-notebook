from pathlib import Path

import pytest

from notion_notebook.ipython_magic import handle_notebook_magic, register_notebook_magic


def test_handle_notebook_magic_starts_local_exporter(mocker) -> None:
    mocker.patch("notion_notebook.ipython_magic.JupyterHooks.get_notebook_path", return_value=None)
    exporter_cls = mocker.patch("notion_notebook.ipython_magic.LocalNotebookExporter")
    exporter = exporter_cls.return_value
    result = handle_notebook_magic("local-exporter")
    exporter_cls.assert_called_once_with(
        notebook_output_dir=str(Path.cwd() / "docs" / "save" / "notebooks"),
        figure_output_dir=str(Path.cwd() / "docs" / "save" / "figures"),
    )
    exporter.start.assert_called_once()
    assert result.action == "local-exporter"


def test_handle_notebook_magic_invalid_command_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported notebook command"):
        handle_notebook_magic("unknown")


def test_handle_notebook_magic_supports_md_and_fig_flags(mocker) -> None:
    exporter_cls = mocker.patch("notion_notebook.ipython_magic.LocalNotebookExporter")
    exporter = exporter_cls.return_value
    handle_notebook_magic("local-exporter --md /tmp/md --fig /tmp/fig")
    exporter_cls.assert_called_once_with(
        notebook_output_dir="/tmp/md",
        figure_output_dir="/tmp/fig",
    )
    exporter.start.assert_called_once()


def test_register_notebook_magic_registers_line_magic() -> None:
    class FakeIPython:
        def __init__(self) -> None:
            self.calls: list[tuple[object, str, str]] = []

        def register_magic_function(self, func, kind: str, name: str) -> None:
            self.calls.append((func, kind, name))

    ip = FakeIPython()
    register_notebook_magic(ip)
    assert len(ip.calls) == 1
    _, kind, name = ip.calls[0]
    assert kind == "line"
    assert name == "notebook"
