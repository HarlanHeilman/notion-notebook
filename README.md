# notion-notebook

Export Jupyter notebooks to a Notion page on save: structured cells, image uploads, optional inline **Figures** table (append-only plot history per sync), and git-aware metadata.

The package also supports a local-only export mode that writes notebook markdown and figure files to configured directories without any Notion API calls.

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

## Local-only export

```python
from notion_notebook import LocalNotebookExporter

exporter = LocalNotebookExporter(
    notebook_output_dir="/absolute/path/to/markdown",
    figure_output_dir="/absolute/path/to/figures",
    notebook_path="/absolute/path/to/notebook.ipynb",  # optional if ipynbname can resolve
)
exporter.start()
```

Call `exporter.manual_sync()` for an immediate local export, or `exporter.stop()` to tear down the file watcher.

### IPython shortcut

The magic name is `%nbexp` (not `%notebook`, which is often reserved elsewhere).

```python
import notion_notebook  # registers line magic

%nbexp local-exporter
```

Defaults write under `<repo>/docs/save/notebooks` and `<repo>/docs/save/figures` when the notebook path is inside a git checkout. Override directories:

```python
%nbexp local-exporter --md path/to/markdown-dir --fig path/to/figures-dir
```

## CLI

The `notion-notebook` console script prints a short usage hint; primary use is the Python API in notebooks.

## Development

```bash
uv run pytest
uv run ty check
uv run ruff check src/ tests/
```

After editing notebook Python in this repo, use `uv run ty check` and `uv run ruff check notebooks/` as well when those files change.
