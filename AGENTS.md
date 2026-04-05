## Learned User Preferences

- After editing notebook Python in this repo, verify with `uv run ty check` and `uv run ruff check notebooks/` when checking in changes.

## Learned Workspace Facts

- Python environment is managed with `uv`; local work uses Python 3.13 in the project venv.
- notion-client 3.x targets Notion API 2025-09-03: list rows via `databases.retrieve` to read `data_sources`, then `data_sources.query`; `databases.query` is not available on the client.
- Empty `data_sources` on `databases.retrieve` or messages that data sources are not accessible to the integration usually mean the database is not connected to the integration (Connections) or rows live under a different database (for example a linked view); paginated `search` filtered by `parent.database_id` can list rows when that path is applicable.
- Inline databases often sit inside `column_list` / `column` blocks; listing only top-level page children misses them and can select an unrelated top-level `child_database` instead of the intended one (for example "All Projects" in columns vs a separate "Untitled" database).
- Notion Search `filter.property` / `value` no longer supports `database`; allowed values include `page` and `data_source`. Prefer **`search` with `filter.value: "data_source"`** and match the **data source title** (what the UI shows), then read `parent.database_id`. Fall back to unfiltered `search` and `object == "database"` for legacy titles, or walk `child_database` under a parent page.
- Use `notion_page_id` with a known page URL or id for a direct target. `notion_page_root` with `notion_page_path` resolves nested **child pages** under a root **page** by title. Database rows: `NOTION_DATABASE_TITLE` + `NOTION_ROW_TITLE`, or `NOTION_DATABASE_ID` + `NOTION_ROW_TITLE` to skip title search. Search-and-walk (page segments, optional database as last segment, then leaf): `NOTION_CONTAINER_PATH` + `NOTION_LEAF_TITLE`.
- The exporter `Figures` database: create as an **inline** embedded table (`databases.create` with `is_inline=True` and `initial_data_source`). Apply column schema on the primary **data source** (`data_sources.update`) if needed. Each sync **appends** new figure rows (`pages.create`, parent `data_source_id`) so re-runs keep history; it does not replace rows by cell index.
- IPython `EventManager` does not register a notebook `pre_save_hook` (invalid name raises `KeyError`); save-driven sync uses `NotebookWatcher` when it is enabled, not IPython pre-save events.
