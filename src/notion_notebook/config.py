"""Load and merge exporter configuration from env, files, and explicit arguments."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG_PATH = Path.home() / ".notion_matplotlib" / "config.json"


def parse_page_path_value(raw: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Normalize ``NOTION_PAGE_PATH`` or JSON config to a tuple of title segments.

    Parameters
    ----------
    raw
        A slash-separated string (``"A/B/C"``), a JSON array string, or a
        sequence of strings.

    Returns
    -------
    tuple of str
        Non-empty segments after stripping.

    Raises
    ------
    ValueError
        When JSON is present but not a list of strings.
    """
    if raw is None:
        return ()
    if isinstance(raw, (list, tuple)):
        return tuple(str(x).strip() for x in raw if str(x).strip())
    s = str(raw).strip()
    if not s:
        return ()
    if s.startswith("["):
        data = json.loads(s)
        if not isinstance(data, list):
            raise ValueError("page_path JSON must be an array")
        return tuple(str(x).strip() for x in data if str(x).strip())
    return tuple(p.strip() for p in s.split("/") if p.strip())


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
    page_root
        Parent page id or URL when resolving the target via :mod:`page_resolve`.
    page_path
        Title path under ``page_root``; non-empty when using path resolution.
    database_title
        Database title for :func:`~notion_notebook.page_resolve.resolve_database_and_row_by_title`.
    database_id
        Optional database id or URL; use with ``row_title`` to skip title search.
    row_title
        Row title within that database (with ``database_title`` or ``database_id``).
    container_path
        Search-first path of page (and optional database) names for
        :func:`~notion_notebook.page_resolve.resolve_container_path_and_leaf`.
    leaf_title
        Final page or row title (with ``container_path``).

    Notes
    -----
    Callers normally obtain instances via :meth:`merge` rather than constructing
    ``Config`` with every field set.
    """

    notion_token: str
    default_page_id: str | None = None
    page_root: str | None = None
    page_path: tuple[str, ...] = ()
    database_title: str | None = None
    database_id: str | None = None
    row_title: str | None = None
    container_path: tuple[str, ...] = ()
    leaf_title: str | None = None
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
        r = os.environ.get("NOTION_PAGE_ROOT")
        if r:
            out["page_root"] = r.strip()
        pp = os.environ.get("NOTION_PAGE_PATH")
        if pp:
            out["page_path"] = parse_page_path_value(pp)
        dt = os.environ.get("NOTION_DATABASE_TITLE")
        if dt:
            out["database_title"] = dt.strip()
        rt = os.environ.get("NOTION_ROW_TITLE")
        if rt:
            out["row_title"] = rt.strip()
        cp = os.environ.get("NOTION_CONTAINER_PATH")
        if cp:
            out["container_path"] = parse_page_path_value(cp)
        lt = os.environ.get("NOTION_LEAF_TITLE")
        if lt:
            out["leaf_title"] = lt.strip()
        did = os.environ.get("NOTION_DATABASE_ID")
        if did:
            out["database_id"] = did.strip()
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
            names match (``notion_token``, ``default_page_id``, ``page_root``,
            ``page_path``, ``database_title``, ``row_title``, ``container_path``,
            ``leaf_title``, ``database_id``, ``auto_sync_on_save``, ``image_format``,
            ``max_image_size_mb``, ``debounce_seconds``).

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
        notion_page_root: str | None = None,
        notion_page_path: str | list[str] | tuple[str, ...] | None = None,
        notion_database_title: str | None = None,
        notion_row_title: str | None = None,
        notion_container_path: str | list[str] | tuple[str, ...] | None = None,
        notion_leaf_title: str | None = None,
        notion_database_id: str | None = None,
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
        notion_page_root
            Root page for title-path resolution when ``notion_page_id`` is unset.
        notion_page_path
            Path segments (slash-separated string, sequence, or JSON array string).
        notion_database_title
            Database title for row resolution (use with ``notion_row_title``).
        notion_row_title
            Row title within ``notion_database_title``.
        notion_container_path
            Container path for search-and-walk resolution (with ``notion_leaf_title``).
        notion_leaf_title
            Leaf page or row title (with ``notion_container_path``).
        notion_database_id
            Database id or URL with ``notion_row_title`` (skips database title search).
        file_path
            JSON path; defaults to ``~/.notion_matplotlib/config.json``.

        Returns
        -------
        Config

        Raises
        ------
        ConfigurationError
            When no token can be resolved after merging all sources, or when
            neither a page id nor a root plus path is available.
        """
        from notion_notebook.exceptions import ConfigurationError

        merged: dict[str, Any] = {}
        merged.update(cls.load_from_env())
        merged.update({k: v for k, v in cls.load_from_file(file_path).items() if v is not None})
        if notion_token:
            merged["notion_token"] = notion_token
        if notion_page_id:
            merged["default_page_id"] = notion_page_id.strip()
        if notion_page_root:
            merged["page_root"] = notion_page_root.strip()
        if notion_page_path is not None:
            merged["page_path"] = parse_page_path_value(notion_page_path)
        if notion_database_title:
            merged["database_title"] = notion_database_title.strip()
        if notion_row_title:
            merged["row_title"] = notion_row_title.strip()
        if notion_container_path is not None:
            merged["container_path"] = parse_page_path_value(notion_container_path)
        if notion_leaf_title:
            merged["leaf_title"] = notion_leaf_title.strip()
        if notion_database_id:
            merged["database_id"] = notion_database_id.strip()
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
        if merged.get("default_page_id"):
            merged["database_title"] = None
            merged["database_id"] = None
            merged["row_title"] = None
            merged["container_path"] = ()
            merged["leaf_title"] = None
            merged["page_root"] = None
            merged["page_path"] = ()
        elif (merged.get("database_title") and merged.get("row_title")) or (
            merged.get("database_id") and merged.get("row_title")
        ):
            merged["default_page_id"] = None
            merged["container_path"] = ()
            merged["leaf_title"] = None
            merged["page_root"] = None
            merged["page_path"] = ()
        elif merged.get("container_path") and merged.get("leaf_title"):
            merged["default_page_id"] = None
            merged["database_title"] = None
            merged["database_id"] = None
            merged["row_title"] = None
            merged["page_root"] = None
            merged["page_path"] = ()
        elif merged.get("page_root") and merged.get("page_path"):
            merged["default_page_id"] = None
            merged["database_title"] = None
            merged["database_id"] = None
            merged["row_title"] = None
            merged["container_path"] = ()
            merged["leaf_title"] = None

        page_id = merged.get("default_page_id")
        root = merged.get("page_root")
        path = tuple(merged.get("page_path") or ())
        db_title = merged.get("database_title")
        db_id = merged.get("database_id")
        row_t = merged.get("row_title")
        cpath = tuple(merged.get("container_path") or ())
        leaf_t = merged.get("leaf_title")

        has_id = bool(page_id)
        has_db_row = bool((db_title and row_t) or (db_id and row_t))
        has_container = bool(cpath and leaf_t)
        has_legacy = bool(root and path)
        n_modes = sum(1 for x in (has_id, has_db_row, has_container, has_legacy) if x)
        if n_modes > 1:
            raise ConfigurationError(
                "Specify exactly one page target: NOTION_PAGE_ID, or "
                "NOTION_DATABASE_TITLE + NOTION_ROW_TITLE, or "
                "NOTION_DATABASE_ID + NOTION_ROW_TITLE, or "
                "NOTION_CONTAINER_PATH + NOTION_LEAF_TITLE, or "
                "NOTION_PAGE_ROOT + NOTION_PAGE_PATH."
            )
        if db_id and not row_t:
            raise ConfigurationError(
                "row_title is required when database_id is set."
            )
        if row_t and not db_title and not db_id:
            raise ConfigurationError(
                "Set database_title or database_id together with row_title."
            )
        if db_title and not row_t and not db_id:
            raise ConfigurationError(
                "row_title is required when database_title is set."
            )
        if (cpath or leaf_t) and not (cpath and leaf_t):
            raise ConfigurationError(
                "container_path and leaf_title must both be set for container resolution."
            )
        if n_modes == 0:
            raise ConfigurationError(
                "Set default_page_id (NOTION_PAGE_ID), or database_title + row_title, or "
                "database_id + row_title, or container_path + leaf_title, or page_root + page_path."
            )
        return cls(
            notion_token=token,
            default_page_id=page_id,
            page_root=str(root).strip() if root else None,
            page_path=path,
            database_title=str(db_title).strip() if db_title else None,
            database_id=str(db_id).strip() if db_id else None,
            row_title=str(row_t).strip() if row_t else None,
            container_path=cpath,
            leaf_title=str(leaf_t).strip() if leaf_t else None,
            auto_sync_on_save=bool(merged.get("auto_sync_on_save", True)),
            image_format=str(merged.get("image_format", "png")),
            max_image_size_mb=float(merged.get("max_image_size_mb", 5.0)),
            debounce_seconds=float(merged.get("debounce_seconds", 2.0)),
        )


@dataclass
class LocalConfig:
    """Resolved settings used by local markdown and figure export.

    Parameters
    ----------
    notebook_output_dir
        Directory where notebook markdown files are written.
    figure_output_dir
        Directory where extracted figure assets are written.
    auto_sync_on_save
        When True, register a file watcher to export after saves.
    image_format
        Preferred raster format for figure extraction: ``png``, ``jpg``, or ``webp``.
    debounce_seconds
        Minimum delay after a filesystem event before running an export.
    """

    notebook_output_dir: Path
    figure_output_dir: Path
    auto_sync_on_save: bool = True
    image_format: str = "png"
    debounce_seconds: float = 2.0

    @staticmethod
    def load_from_env() -> dict[str, Any]:
        """Read optional local-export settings from process environment.

        Returns
        -------
        dict
            Keys that map to :class:`LocalConfig` fields when set.
        """
        out: dict[str, Any] = {}
        md = os.environ.get("NOTEBOOK_OUTPUT_DIR")
        if md:
            out["notebook_output_dir"] = md.strip()
        fd = os.environ.get("FIGURE_OUTPUT_DIR")
        if fd:
            out["figure_output_dir"] = fd.strip()
        auto = os.environ.get("LOCAL_AUTO_SYNC_ON_SAVE")
        if auto:
            out["auto_sync_on_save"] = auto.strip().lower() not in {"0", "false", "no", "off"}
        fmt = os.environ.get("LOCAL_IMAGE_FORMAT")
        if fmt:
            out["image_format"] = fmt.strip()
        db = os.environ.get("LOCAL_DEBOUNCE_SECONDS")
        if db:
            out["debounce_seconds"] = float(db.strip())
        return out

    @staticmethod
    def load_from_file(path: str | Path | None = None) -> dict[str, Any]:
        """Load optional local-export fields from JSON config if present.

        Parameters
        ----------
        path
            File to read; defaults to ``~/.notion_matplotlib/config.json``.

        Returns
        -------
        dict
            Parsed mapping from JSON, or an empty mapping when missing.
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
        notebook_output_dir: str | Path | None = None,
        figure_output_dir: str | Path | None = None,
        auto_sync_on_save: bool | None = None,
        image_format: str | None = None,
        debounce_seconds: float | None = None,
        file_path: str | Path | None = None,
    ) -> LocalConfig:
        """Merge explicit local-export args over environment and JSON config.

        Parameters
        ----------
        notebook_output_dir
            Destination directory for notebook markdown files.
        figure_output_dir
            Destination directory for extracted figure assets.
        auto_sync_on_save
            Enable or disable watcher-based sync.
        image_format
            Preferred figure format for extraction.
        debounce_seconds
            Debounce delay for save events.
        file_path
            JSON path; defaults to ``~/.notion_matplotlib/config.json``.

        Returns
        -------
        LocalConfig

        Raises
        ------
        ConfigurationError
            Raised when output directories are missing after merging.
        """
        from notion_notebook.exceptions import ConfigurationError

        merged: dict[str, Any] = {}
        merged.update(cls.load_from_env())
        merged.update({k: v for k, v in cls.load_from_file(file_path).items() if v is not None})
        if notebook_output_dir is not None:
            merged["notebook_output_dir"] = str(notebook_output_dir)
        if figure_output_dir is not None:
            merged["figure_output_dir"] = str(figure_output_dir)
        if auto_sync_on_save is not None:
            merged["auto_sync_on_save"] = auto_sync_on_save
        if image_format is not None:
            merged["image_format"] = image_format
        if debounce_seconds is not None:
            merged["debounce_seconds"] = debounce_seconds

        nb_out = merged.get("notebook_output_dir")
        fig_out = merged.get("figure_output_dir")
        if not nb_out:
            raise ConfigurationError(
                "notebook_output_dir is required (constructor, NOTEBOOK_OUTPUT_DIR, or config file)."
            )
        if not fig_out:
            raise ConfigurationError(
                "figure_output_dir is required (constructor, FIGURE_OUTPUT_DIR, or config file)."
            )
        return cls(
            notebook_output_dir=Path(str(nb_out)).expanduser().resolve(),
            figure_output_dir=Path(str(fig_out)).expanduser().resolve(),
            auto_sync_on_save=bool(merged.get("auto_sync_on_save", True)),
            image_format=str(merged.get("image_format", "png")),
            debounce_seconds=float(merged.get("debounce_seconds", 2.0)),
        )
