"""IPython magic commands for notebook export workflows."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from notion_notebook.git_utils import GitContext
from notion_notebook.jupyter_hooks import JupyterHooks
from notion_notebook.local_exporter import LocalNotebookExporter

_ACTIVE_LOCAL_EXPORTER: LocalNotebookExporter | None = None


@dataclass
class NotebookMagicResult:
    """Result payload returned by notebook magic handlers.

    Parameters
    ----------
    action
        The normalized action executed by the magic command.
    message
        Human-readable status describing the operation outcome.
    """

    action: str
    message: str


def _default_local_dirs() -> tuple[str, str]:
    """Return default output directories for local exporter mode.

    Returns
    -------
    tuple of str
        Default `(notebook_output_dir, figure_output_dir)` values.
    """
    notebook_path = JupyterHooks.get_notebook_path()
    if notebook_path:
        root = GitContext.find_git_root(Path(notebook_path))
        if root is not None:
            base = root / "docs" / "save"
            return (str(base / "notebooks"), str(base / "figures"))
    base = Path.cwd() / "docs" / "save"
    return (str(base / "notebooks"), str(base / "figures"))


def _parse_local_exporter_args(args: list[str]) -> tuple[str, str]:
    """Parse optional `%notebook local-exporter` arguments.

    Parameters
    ----------
    args
        Arguments after `local-exporter`.

    Returns
    -------
    tuple of str
        Parsed `(notebook_output_dir, figure_output_dir)` values.

    Raises
    ------
    ValueError
        Raised when an unknown or incomplete option is provided.
    """
    md_dir, fig_dir = _default_local_dirs()
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--md":
            if i + 1 >= len(args):
                raise ValueError("Missing value for --md")
            md_dir = args[i + 1]
            i += 2
            continue
        if arg == "--fig":
            if i + 1 >= len(args):
                raise ValueError("Missing value for --fig")
            fig_dir = args[i + 1]
            i += 2
            continue
        raise ValueError("Unsupported option. Use --md <path> and/or --fig <path>.")
    return md_dir, fig_dir


def handle_notebook_magic(line: str) -> NotebookMagicResult:
    """Execute a `%notebook` line-magic command.

    Parameters
    ----------
    line
        Raw argument string after `%notebook`.

    Returns
    -------
    NotebookMagicResult
        Structured result indicating the action and status message.

    Raises
    ------
    ValueError
        Raised when the command is missing or unsupported.
    """
    args = shlex.split(line or "")
    if not args:
        raise ValueError("Usage: %notebook local-exporter")
    command = args[0].strip().lower()
    if command != "local-exporter":
        raise ValueError("Unsupported notebook command. Use: %notebook local-exporter")
    md_dir, fig_dir = _parse_local_exporter_args(args[1:])
    exporter = LocalNotebookExporter(
        notebook_output_dir=str(Path(md_dir)),
        figure_output_dir=str(Path(fig_dir)),
    )
    exporter.start()
    global _ACTIVE_LOCAL_EXPORTER
    _ACTIVE_LOCAL_EXPORTER = exporter
    return NotebookMagicResult(
        action="local-exporter",
        message=f"Local exporter started (markdown={md_dir}, figures={fig_dir}).",
    )


def register_notebook_magic(ip: Any) -> None:
    """Register `%notebook` line magic on an IPython shell.

    Parameters
    ----------
    ip
        IPython shell instance that provides `register_magic_function`.
    """

    def _notebook_magic(line: str) -> str:
        result = handle_notebook_magic(line)
        return result.message

    ip.register_magic_function(_notebook_magic, "line", "notebook")


def ensure_ipython_magic_registered() -> None:
    """Register `%notebook` magic when running inside IPython."""
    try:
        from IPython import get_ipython
    except ImportError:
        return
    ip = get_ipython()
    if ip is None:
        return
    register_notebook_magic(ip)
