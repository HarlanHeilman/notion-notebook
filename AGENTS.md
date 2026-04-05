## Learned User Preferences

- After editing notebook Python in this repo, verify with `uv run ty check` and `uv run ruff check notebooks/` when checking in changes.

## Learned Workspace Facts

- Python environment is managed with `uv`; local work uses Python 3.13 in the project venv.
- notion-client 3.x targets Notion API 2025-09-03: list rows via `databases.retrieve` to read `data_sources`, then `data_sources.query`; `databases.query` is not available on the client.
- Empty `data_sources` on `databases.retrieve` or messages that data sources are not accessible to the integration usually mean the database is not connected to the integration (Connections) or rows live under a different database (for example a linked view); paginated `search` filtered by `parent.database_id` can list rows when that path is applicable.
- Inline databases often sit inside `column_list` / `column` blocks; listing only top-level page children misses them and can select an unrelated top-level `child_database` instead of the intended one (for example "All Projects" in columns vs a separate "Untitled" database).
- Notion Search `filter.property` / `value` no longer supports `database`; allowed values include `page` and `data_source`. To find databases by title, list `child_database` blocks under a parent page or call `search` without that filter and keep results with `object == "database"`.
