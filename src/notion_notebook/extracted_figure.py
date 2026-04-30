"""Pure-data figure payloads extracted from notebook cell outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ExtractedFigure:
    """One raster figure extracted from a code cell output.

    Parameters
    ----------
    cell_index
        Notebook cell index containing the figure.
    figure_index
        One-based index among image outputs in that cell for this sync.
    image_data
        Raw image bytes in ``image_format`` encoding.
    image_format
        File format: ``png``, ``jpg``, or ``webp``.
    code
        Full source of the parent code cell.
    title
        Parsed ``plt.title`` text when detectable; otherwise ``None``.
    timestamp
        UTC time assigned at extraction.
    """

    cell_index: int
    figure_index: int
    image_data: bytes
    image_format: str
    code: str
    title: str | None
    timestamp: datetime

    def mime_type(self) -> str:
        """Return the MIME type string for this figure's format."""
        return {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }.get(self.image_format.lower(), "image/png")
