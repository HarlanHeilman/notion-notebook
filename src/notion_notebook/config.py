"""Load and merge exporter configuration from env, files, and explicit arguments."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG_PATH = Path.home() / ".notion_matplotlib" / "config.json"


@dataclass
class Config:
    """Resolved settings used by :class:`~notion_notebook.exporter.NotebookExporter`.

    Parameters
    ----------
    notion_token
        Notion integration secret token.
    default_page_id
        Target page id when none is passed to the exporter.
    auto_sync_on_save
        When True, register a file watcher to sync after saves.
    image_format
        Preferred raster format for figure extraction: ``png``, ``jpg``, or ``webp``.
    max_image_size_mb
        Skip uploads larger than this many megabytes; smaller images still upload.
    debounce_seconds
        Minimum delay after a filesystem event before running a sync.

    Notes
    -----
    Callers normally obtain instances via :meth:`merge` rather than constructing
    ``Config`` with every field set.
    """

    notion_token: str
    default_page_id: str | None = None
    auto_sync_on_save: bool = True
    image_format: str = "png"
    max_image_size_mb: float = 5.0
    debounce_seconds: float = 2.0

    @staticmethod
    def load_from_env() -> dict[str, Any]:
        """Read optional ``NOTION_TOKEN`` and ``NOTION_PAGE_ID`` from the process environment.

        Returns
        -------
        dict
            Keys ``notion_token`` and ``default_page_id`` when variables are set.

        Notes
        -----
        Does not validate token shape; missing variables are omitted from the mapping.
        """
        out: dict[str, Any] = {}
        t = os.environ.get("NOTION_TOKEN")
        if t:
            out["notion_token"] = t
        p = os.environ.get("NOTION_PAGE_ID")
        if p:
            out["default_page_id"] = p.strip()
        return out

    @staticmethod
    def load_from_file(path: str | Path | None = None) -> dict[str, Any]:
        """Load JSON configuration from disk if the file exists.

        Parameters
        ----------
        path
            File to read; defaults to ``~/.notion_matplotlib/config.json``.

        Returns
        -------
        dict
            Parsed top-level object with keys mapped to :class:`Config` fields where
            names match (``notion_token``, ``default_page_id``, ``auto_sync_on_save``,
            ``image_format``, ``max_image_size_mb``, ``debounce_seconds``).

        Notes
        -----
        Returns an empty dict when the file is missing. Does not catch JSON errors;
        malformed files raise :exc:`json.JSONDecodeError`.
        """
        p = Path(path).expanduser() if path is not None else _DEFAULT_CONFIG_PATH
        if not p.is_file():
            return {}
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return dict(raw)

    @classmethod
    def merge(
        cls,
        *,
        notion_token: str | None = None,
        notion_page_id: str | None = None,
        file_path: str | Path | None = None,
        auto_sync_on_save: bool | None = None,
        image_format: str | None = None,
        max_image_size_mb: float | None = None,
        debounce_seconds: float | None = None,
    ) -> Config:
        """Merge explicit arguments over environment, then optional JSON file.

        Parameters
        ----------
        notion_token
            Highest-precedence token when provided.
        notion_page_id
            Highest-precedence page id when provided.
        file_path
            JSON path; defaults to ``~/.notion_matplotlib/config.json``.

        Returns
        -------
        Config

        Raises
        ------
        ConfigurationError
            When no token can be resolved after merging all sources.
        """
        from notion_notebook.exceptions import ConfigurationError

        merged: dict[str, Any] = {}
        merged.update(cls.load_from_env())
        merged.update({k: v for k, v in cls.load_from_file(file_path).items() if v is not None})
        if notion_token:
            merged["notion_token"] = notion_token
        if notion_page_id:
            merged["default_page_id"] = notion_page_id.strip()
        if auto_sync_on_save is not None:
            merged["auto_sync_on_save"] = auto_sync_on_save
        if image_format is not None:
            merged["image_format"] = image_format
        if max_image_size_mb is not None:
            merged["max_image_size_mb"] = max_image_size_mb
        if debounce_seconds is not None:
            merged["debounce_seconds"] = debounce_seconds
        token = merged.get("notion_token")
        if not token or not isinstance(token, str):
            raise ConfigurationError(
                "notion_token is required (constructor, NOTION_TOKEN, or config file)."
            )
        return cls(
            notion_token=token,
            default_page_id=merged.get("default_page_id"),
            auto_sync_on_save=bool(merged.get("auto_sync_on_save", True)),
            image_format=str(merged.get("image_format", "png")),
            max_image_size_mb=float(merged.get("max_image_size_mb", 5.0)),
            debounce_seconds=float(merged.get("debounce_seconds", 2.0)),
        )
