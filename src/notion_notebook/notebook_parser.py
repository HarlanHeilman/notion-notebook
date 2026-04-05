"""Parse Jupyter notebooks on disk into structured cell and output records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import nbformat


@dataclass
class CellOutput:
    """One Jupyter output payload (stream, error, display_data, or execute_result).

    Parameters
    ----------
    output_type
        Jupyter ``output_type`` string.
    content
        Primary text payload when applicable (stream text, traceback joined, or plain).
    mime_blobs
        Mapping of MIME type to raw ``data`` payload (may be base64 str, list, or bytes).
    """

    output_type: str
    content: str = ""
    mime_blobs: dict[str, object] = field(default_factory=dict)


@dataclass
class NotebookCell:
    """Single notebook cell with ordered outputs.

    Parameters
    ----------
    index
        Zero-based cell index in the notebook.
    cell_type
        ``code``, ``markdown``, or ``raw``.
    source
        Cell source as a single string.
    execution_count
        Code cell execution count when present.
    outputs
        Parsed outputs for code cells.
    metadata
        Cell ``metadata`` dict when present (for language id hints).
    """

    index: int
    cell_type: str
    source: str
    execution_count: int | None
    outputs: list[CellOutput]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ParsedNotebook:
    """Notebook document after reading from disk.

    Parameters
    ----------
    path
        Absolute path string.
    name
        Filename without ``.ipynb``.
    cells
        Ordered cells with outputs.
    kernel_name
        Language/kernel metadata when present.
    modified_time
        Filesystem mtime in UTC when the file was read, or epoch if unknown.
    """

    path: str
    name: str
    cells: list[NotebookCell]
    kernel_name: str | None
    modified_time: datetime


class NotebookParser:
    """Read ``.ipynb`` files using nbformat and normalize cell sources and outputs."""

    def parse(self, notebook_path: str | Path) -> ParsedNotebook:
        """Read and parse a notebook file into :class:`ParsedNotebook`.

        Parameters
        ----------
        notebook_path
            Path to an ``.ipynb`` file.

        Returns
        -------
        ParsedNotebook

        Raises
        ------
        FileNotFoundError
            When ``notebook_path`` does not exist.
        nbformat.reader.NotJSONError
            When the file is not valid JSON.
        nbformat.validator.ValidationError
            When the notebook fails nbformat validation.
        """
        p = Path(notebook_path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(p)
        nb = nbformat.read(p.open(encoding="utf-8"), as_version=4)
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
        kernel_name = None
        kspec = nb.get("metadata", {}).get("kernelspec", {})
        if isinstance(kspec, dict) and isinstance(kspec.get("name"), str):
            kernel_name = kspec["name"]
        cells: list[NotebookCell] = []
        for i, cell in enumerate(nb.cells):
            src = cell.source
            if not isinstance(src, str):
                src = "".join(src)
            outs: list[CellOutput] = []
            meta_raw = cell.get("metadata", {})
            meta: dict[str, object] = dict(meta_raw) if isinstance(meta_raw, dict) else {}
            if cell.cell_type == "code":
                for o in cell.get("outputs", []):
                    outs.append(self._parse_output(o))
            cells.append(
                NotebookCell(
                    index=i,
                    cell_type=cell.cell_type,
                    source=src,
                    execution_count=cell.get("execution_count"),
                    outputs=outs,
                    metadata=meta,
                )
            )
        return ParsedNotebook(
            path=str(p),
            name=p.stem,
            cells=cells,
            kernel_name=kernel_name,
            modified_time=mtime,
        )

    def _parse_output(self, o: object) -> CellOutput:
        if not isinstance(o, dict):
            return CellOutput(output_type="stream", content="")
        od = cast(dict[str, Any], o)
        ot = str(od.get("output_type", "stream"))
        if ot == "stream":
            t = od.get("text", "")
            if isinstance(t, str):
                text = t
            elif isinstance(t, list):
                text = "".join(str(x) for x in t)
            else:
                text = str(t)
            return CellOutput(output_type="stream", content=text)
        if ot == "error":
            tb = od.get("traceback")
            if isinstance(tb, list):
                return CellOutput(output_type="error", content="\n".join(str(x) for x in tb))
            return CellOutput(output_type="error", content="")
        if ot in ("display_data", "execute_result"):
            data = od.get("data")
            mime_blobs: dict[str, object] = {}
            if isinstance(data, dict):
                mime_blobs = dict(data)
            plain = ""
            tp = mime_blobs.get("text/plain")
            if tp is not None:
                plain = tp if isinstance(tp, str) else "".join(str(x) for x in cast(list[Any], tp))
            return CellOutput(
                output_type=ot,
                content=plain,
                mime_blobs=mime_blobs,
            )
        return CellOutput(output_type=ot, content=str(od))
