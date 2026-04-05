"""Discover git roots and remotes for notebook path metadata."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class NotebookMetadata:
    """Notebook location and sync-time git context for Notion export headers.

    Parameters
    ----------
    last_sync
        UTC timestamp when metadata was assembled (sync time).
    notebook_path
        Path relative to the git root, POSIX-style, when inside a repo.
    github_remote
        ``remote.origin.url`` when available (https or ssh).
    notebook_name
        Filename without ``.ipynb`` suffix.
    file_path
        Absolute path to the ``.ipynb`` file.
    """

    last_sync: datetime
    notebook_path: str
    github_remote: str | None
    notebook_name: str
    file_path: Path


class GitContext:
    """Static helpers to resolve git roots and remotes from notebook paths."""

    @staticmethod
    def find_git_root(start_path: Path) -> Path | None:
        """Walk parents from ``start_path`` until a ``.git`` directory exists.

        Parameters
        ----------
        start_path
            File or directory to begin the walk (typically a notebook path).

        Returns
        -------
        pathlib.Path or None
            Directory containing ``.git``, or ``None`` when not inside a repository.
        """
        cur = start_path.resolve()
        if cur.is_file():
            cur = cur.parent
        for p in [cur, *cur.parents]:
            if (p / ".git").exists():
                return p
        return None

    @staticmethod
    def get_git_remote_url(git_root: Path) -> str | None:
        """Return ``git config remote.origin.url`` for ``git_root``.

        Parameters
        ----------
        git_root
            Repository root containing ``.git``.

        Returns
        -------
        str or None
            Origin URL, or ``None`` when unset or ``git`` is unavailable.
        """
        try:
            out = subprocess.run(
                ["git", "-C", str(git_root), "config", "--get", "remote.origin.url"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        url = (out.stdout or "").strip()
        return url or None

    @staticmethod
    def get_relative_path(notebook_path: Path, git_root: Path) -> str:
        """Compute ``notebook_path`` relative to ``git_root`` using POSIX separators.

        Parameters
        ----------
        notebook_path
            Absolute path to the ``.ipynb`` file.
        git_root
            Repository root directory.

        Returns
        -------
        str
            Relative path; if resolution fails, returns ``notebook_path.name``.
        """
        try:
            return notebook_path.resolve().relative_to(git_root.resolve()).as_posix()
        except ValueError:
            return notebook_path.name

    @staticmethod
    def get_notebook_metadata(notebook_path: Path) -> NotebookMetadata:
        """Assemble :class:`NotebookMetadata` for a notebook on disk.

        Parameters
        ----------
        notebook_path
            Path to the ``.ipynb`` file (need not exist for path fields).

        Returns
        -------
        NotebookMetadata
            ``github_remote`` is ``None`` when outside git or when origin is unset.
            ``notebook_path`` is the basename when not under a git root.
        """
        p = notebook_path.resolve()
        name = p.stem
        root = GitContext.find_git_root(p)
        if root is None:
            return NotebookMetadata(
                last_sync=datetime.now(UTC),
                notebook_path=p.name,
                github_remote=None,
                notebook_name=name,
                file_path=p,
            )
        rel = GitContext.get_relative_path(p, root)
        remote = GitContext.get_git_remote_url(root)
        return NotebookMetadata(
            last_sync=datetime.now(UTC),
            notebook_path=rel,
            github_remote=remote,
            notebook_name=name,
            file_path=p,
        )
