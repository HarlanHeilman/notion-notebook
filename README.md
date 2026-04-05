# notion-notebook

Export Jupyter notebooks to a Notion page on save: structured cells, image uploads, optional inline **Figures** table (append-only plot history per sync), and git-aware metadata.

## Install

```bash
uv sync
```

## Configure

Set environment variables or `~/.notion_matplotlib/config.json` (see `notion_notebook.config.Config`):

- `NOTION_TOKEN` — integration secret
- `NOTION_PAGE_ID` — target page id or URL fragment

## Use in a notebook

```python
from notion_notebook import NotebookExporter

exporter = NotebookExporter(
    notion_token="ntn_...",
    notion_page_id="your-page-id-or-url",
    notebook_path="/absolute/path/to/notebook.ipynb",  # optional if ipynbname can resolve
)
exporter.start()
```

Call `exporter.manual_sync()` for an immediate run, or `exporter.stop()` to tear down the file watcher.

## CLI

The `notion-notebook` console script prints a short usage hint; primary use is the Python API in notebooks.

## Development

```bash
uv run pytest
uv run ty check
uv run ruff check src/ tests/
```

After editing notebook Python in this repo, use `uv run ty check` and `uv run ruff check notebooks/` as well when those files change.
