"""Resolve Notion page ids from titles, paths, and database rows."""

from __future__ import annotations

from typing import Any, cast

from notion_client import Client
from notion_client.helpers import collect_paginated_api

from notion_notebook.utils import normalize_page_id

_CONTAINER_TYPES = frozenset(
    {"column_list", "column", "synced_block", "toggle", "callout"}
)


def _norm_title(s: str) -> str:
    return " ".join(s.strip().split()).casefold()


def _titles_match(found: str | None, want: str) -> bool:
    if not found:
        return False
    return _norm_title(found) == _norm_title(want)


def _page_title_from_properties(props: dict[str, Any]) -> str | None:
    for v in props.values():
        if not isinstance(v, dict) or v.get("type") != "title":
            continue
        parts = v.get("title") or []
        if not isinstance(parts, list):
            continue
        out: list[str] = []
        for p in parts:
            if isinstance(p, dict):
                t = (p.get("text") or {}).get("content")
                if t:
                    out.append(str(t))
                elif p.get("plain_text"):
                    out.append(str(p.get("plain_text")))
        s = "".join(out).strip()
        if s:
            return s
    return None


def _database_title_from_object(obj: dict[str, Any]) -> str | None:
    t = obj.get("title")
    if isinstance(t, str):
        return t.strip() or None
    if isinstance(t, list):
        plain = "".join(
            str(p.get("plain_text", ""))
            for p in t
            if isinstance(p, dict)
        ).strip()
        return plain or None
    return None


def _page_or_database_title(hit: dict[str, Any]) -> str | None:
    otype = hit.get("object")
    if otype == "page":
        return _page_title_from_properties(hit.get("properties") or {})
    if otype == "database":
        return _database_title_from_object(hit)
    return None


def search_page_id_by_title(notion: Any, title: str) -> str | None:
    """Return a page id whose title matches ``title`` (case-insensitive, normalized whitespace).

    Uses Notion ``search`` with a page filter and picks the first exact title match.
    """
    resp = cast(
        dict[str, Any],
        notion.search(
            query=title,
            filter={"property": "object", "value": "page"},
            page_size=20,
        ),
    )
    want = _norm_title(title)
    for hit in resp.get("results") or []:
        if hit.get("object") != "page":
            continue
        got = _page_or_database_title(hit)
        if got and _norm_title(got) == want:
            return str(hit["id"])
    return None


def _rich_text_plain(rich: Any) -> str | None:
    if not isinstance(rich, list):
        return None
    s = "".join(
        str(p.get("plain_text", ""))
        for p in rich
        if isinstance(p, dict)
    ).strip()
    return s or None


def _database_id_from_parent_dict(parent: Any) -> str | None:
    if not isinstance(parent, dict):
        return None
    ptype = parent.get("type")
    if ptype == "database_id" and parent.get("database_id"):
        return str(parent["database_id"])
    if ptype == "data_source_id" and parent.get("database_id"):
        return str(parent["database_id"])
    return None


def _database_id_from_data_source_hit(notion: Any, hit: dict[str, Any]) -> str | None:
    db = _database_id_from_parent_dict(hit.get("parent"))
    if db:
        return db
    ds_id = hit.get("id")
    if not ds_id:
        return None
    full = cast(dict[str, Any], notion.data_sources.retrieve(str(ds_id)))
    return _database_id_from_parent_dict(full.get("parent"))


def _data_source_title_matches(hit: dict[str, Any], want_norm: str) -> bool:
    plain = _rich_text_plain(hit.get("title"))
    return bool(plain) and _norm_title(plain) == want_norm


def _iter_search_results(
    notion: Any,
    query: str,
    *,
    filter_value: str | None,
) -> Any:
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {"query": query, "page_size": 100}
        if filter_value is not None:
            kwargs["filter"] = {"property": "object", "value": filter_value}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = cast(dict[str, Any], notion.search(**kwargs))
        yield resp
        cursor = resp.get("next_cursor")
        if not cursor:
            break


def _first_significant_token(title: str) -> str | None:
    for part in title.replace("/", " ").split():
        p = part.strip()
        if len(p) > 2:
            return p
    return None


def _try_find_database_via_data_source_search(
    notion: Any,
    query: str,
    want_norm: str,
) -> str | None:
    for resp in _iter_search_results(notion, query, filter_value="data_source"):
        for hit in resp.get("results") or []:
            if hit.get("object") != "data_source":
                continue
            if not _data_source_title_matches(hit, want_norm):
                continue
            db_id = _database_id_from_data_source_hit(notion, hit)
            if db_id:
                return db_id
    return None


def search_database_id_by_title(notion: Any, title: str) -> str | None:
    """Return a database id whose **visible** title matches ``title``.

    Resolution order:

    1. **Data sources** — ``search`` with ``filter: data_source`` (the name
       shown in the Notion UI for many databases is the primary **data source**
       title, not the legacy database ``title`` field).
    2. Same as (1) with a shorter **query** (first significant word) when the
       full string returns no exact title match, still requiring an exact
       case-insensitive title match on each hit.
    3. **Database objects** — unfiltered ``search`` and keep ``object ==
       database`` with a matching ``title`` (older / rare responses).

    Notion Search does not accept ``filter.value: \"database\"``; use
    ``data_source`` or unfiltered results instead.
    """
    want = _norm_title(title)
    for q in (title,):
        found = _try_find_database_via_data_source_search(notion, q, want)
        if found:
            return normalize_page_id(found)
    tok = _first_significant_token(title)
    if tok and _norm_title(tok) != want:
        found = _try_find_database_via_data_source_search(notion, tok, want)
        if found:
            return normalize_page_id(found)
    for resp in _iter_search_results(notion, title, filter_value=None):
        for hit in resp.get("results") or []:
            if hit.get("object") != "database":
                continue
            got = _database_title_from_object(hit)
            if got and _norm_title(got) == want:
                return normalize_page_id(str(hit["id"]))
    return None


def _primary_data_source_id(notion: Any, database_id: str) -> str | None:
    meta = cast(dict[str, Any], notion.databases.retrieve(database_id))
    sources = meta.get("data_sources") or []
    if not sources:
        return None
    return str(sources[0]["id"])


def _title_property_name_from_data_source(notion: Any, data_source_id: str) -> str | None:
    ds = cast(dict[str, Any], notion.data_sources.retrieve(data_source_id))
    for name, spec in (ds.get("properties") or {}).items():
        if isinstance(spec, dict) and spec.get("type") == "title":
            return str(name)
    return None


def find_row_page_id_in_database(notion: Any, database_id: str, row_title: str) -> str | None:
    """Return the page id for a database row whose title property matches ``row_title``."""
    ds_id = _primary_data_source_id(notion, database_id)
    if not ds_id:
        return None
    prop = _title_property_name_from_data_source(notion, ds_id)
    if not prop:
        return None
    want = _norm_title(row_title)
    filt: dict[str, Any] = {"property": prop, "title": {"equals": row_title}}
    resp = cast(
        dict[str, Any],
        notion.data_sources.query(ds_id, filter=filt, page_size=10),
    )
    rows = list(resp.get("results") or [])
    if rows:
        return str(rows[0]["id"])
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {"page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        batch = cast(
            dict[str, Any],
            notion.data_sources.query(ds_id, **kwargs),
        )
        for row in batch.get("results") or []:
            props = row.get("properties") or {}
            pv = props.get(prop)
            if not isinstance(pv, dict) or pv.get("type") != "title":
                continue
            parts = pv.get("title") or []
            text = "".join(
                str(p.get("plain_text", ""))
                for p in parts
                if isinstance(p, dict)
            )
            if _norm_title(text) == want:
                return str(row["id"])
        cursor = batch.get("next_cursor")
        if not cursor:
            break
    return None


def resolve_database_and_row_by_title(
    token: str,
    database_title: str,
    row_title: str,
    *,
    database_id: str | None = None,
) -> str:
    """Resolve a page id by database and row title (title property match).

    When ``database_id`` is set, it is used directly and ``database_title`` is
    only for error messages. Otherwise a database is located by title via
    :func:`search_database_id_by_title` (data source search first, then legacy
    database objects).

    Parameters
    ----------
    token
        Notion integration token.
    database_title
        Database title as shown in the Notion UI (used when ``database_id`` is
        ``None``).
    row_title
        Target row title (must match the database title property).
    database_id
        Optional raw database id or URL to skip title search.

    Returns
    -------
    str
        Normalized 32-character hex page id for the row.

    Raises
    ------
    ValueError
        When the database or row cannot be found.
    """
    notion = Client(auth=token)
    if database_id:
        db_id = normalize_page_id(database_id)
    else:
        db_id = search_database_id_by_title(notion, database_title)
    if not db_id:
        raise ValueError(
            f"No database titled {database_title!r} found via search "
            "(try NOTION_DATABASE_ID with the database UUID from Notion)."
        )
    row_id = find_row_page_id_in_database(notion, db_id, row_title)
    if not row_id:
        raise ValueError(
            f"No row titled {row_title!r} in database {database_title!r}."
        )
    return normalize_page_id(row_id)


def _child_page_title(block: dict[str, Any]) -> str | None:
    cp = block.get("child_page")
    if not isinstance(cp, dict):
        return None
    t = cp.get("title")
    if isinstance(t, str):
        return t.strip()
    return None


def _child_database_title(block: dict[str, Any]) -> str | None:
    cd = block.get("child_database")
    if not isinstance(cd, dict):
        return None
    t = cd.get("title")
    if isinstance(t, str):
        return t.strip()
    if isinstance(t, list):
        return (
            "".join(
                str(p.get("plain_text", ""))
                for p in t
                if isinstance(p, dict)
            ).strip()
            or None
        )
    return None


def _find_child_page_under_block_parent(
    notion: Any,
    block_parent_id: str,
    title: str,
) -> str | None:
    children = list(
        collect_paginated_api(
            notion.blocks.children.list,
            block_id=block_parent_id,
            page_size=100,
        )
    )
    for block in children:
        btype = block.get("type")
        if btype == "child_page":
            ct = _child_page_title(block)
            if _titles_match(ct, title):
                return str(block["id"])
        if btype in _CONTAINER_TYPES:
            bid = block.get("id")
            if bid:
                nested = _find_child_page_under_block_parent(notion, str(bid), title)
                if nested:
                    return nested
    return None


def _find_child_database_under_block_parent(
    notion: Any,
    block_parent_id: str,
    title: str,
) -> str | None:
    children = list(
        collect_paginated_api(
            notion.blocks.children.list,
            block_id=block_parent_id,
            page_size=100,
        )
    )
    for block in children:
        btype = block.get("type")
        if btype == "child_database":
            ct = _child_database_title(block)
            if _titles_match(ct, title):
                return str(block["id"])
        if btype in _CONTAINER_TYPES:
            bid = block.get("id")
            if bid:
                nested = _find_child_database_under_block_parent(
                    notion, str(bid), title
                )
                if nested:
                    return nested
    return None


def resolve_page_by_title_path(
    token: str,
    root_page_id_or_url: str,
    path_segments: tuple[str, ...],
) -> str:
    """Walk from ``root_page_id_or_url`` through nested ``child_page`` titles.

    Traverses ``path_segments`` in order, recursing into common container block
    types so pages inside columns or toggles resolve. The final segment's page
    id is returned.

    Parameters
    ----------
    token
        Notion integration token.
    root_page_id_or_url
        Starting page (UUID, hex id, or ``notion.so`` URL).
    path_segments
        Non-empty sequence of child page titles to match at each level.

    Returns
    -------
    str
        Normalized 32-character hex page id for the leaf page.

    Raises
    ------
    ValueError
        When ``path_segments`` is empty, a title is not found, or the root id
        cannot be normalized.
    """
    if not path_segments:
        raise ValueError("path_segments must be non-empty")

    notion = Client(auth=token)
    current = normalize_page_id(root_page_id_or_url)
    for segment in path_segments:
        nxt = _find_child_page_under_block_parent(notion, current, segment)
        if not nxt:
            raise ValueError(
                f"No child page titled {segment!r} under page {current}."
            )
        current = normalize_page_id(nxt)
    return current


def resolve_container_path_and_leaf(
    token: str,
    container_segments: tuple[str, ...],
    leaf_title: str,
) -> str:
    """Walk pages by title, optionally ending at a database, then resolve ``leaf_title``.

    The first segment is resolved with :func:`search_page_id_by_title`. Each
    subsequent segment looks for a matching ``child_database`` (recursive in
    containers) first; if the database is the **last** container segment, the
    function queries that database for a row titled ``leaf_title`` and returns
    the row page id. Otherwise it looks for a ``child_page`` and continues.

    If all container segments are exhausted on a **page**, the leaf is resolved
    as a ``child_page`` under that page.

    Parameters
    ----------
    token
        Notion integration token.
    container_segments
        At least one page title (first segment). Further segments are child
        databases or pages under the previous page.
    leaf_title
        Row title when the path ends at a database, or child page title when
        the path ends at a page.

    Returns
    -------
    str
        Normalized hex page id for the leaf.

    Raises
    ------
    ValueError
        When search or block traversal fails, or a database appears as a
        non-final container segment (unsupported).
    """
    if not container_segments:
        raise ValueError("container_segments must be non-empty")
    if not leaf_title.strip():
        raise ValueError("leaf_title must be non-empty")

    notion = Client(auth=token)
    first = container_segments[0]
    current_page = search_page_id_by_title(notion, first)
    if not current_page:
        raise ValueError(f"No top-level page titled {first!r} found via search.")

    for idx, seg in enumerate(container_segments[1:]):
        is_last_seg = idx == len(container_segments) - 2
        db_id = _find_child_database_under_block_parent(
            notion, current_page, seg
        )
        if db_id:
            if not is_last_seg:
                raise ValueError(
                    f"Database {seg!r} is not the final container segment; "
                    "navigating past a database is not supported."
                )
            row_id = find_row_page_id_in_database(notion, db_id, leaf_title)
            if not row_id:
                raise ValueError(
                    f"No row titled {leaf_title!r} under database {seg!r}."
                )
            return normalize_page_id(row_id)
        nxt_page = _find_child_page_under_block_parent(notion, current_page, seg)
        if not nxt_page:
            raise ValueError(
                f"No child page or database titled {seg!r} under the current page."
            )
        current_page = nxt_page

    leaf_id = _find_child_page_under_block_parent(
        notion, current_page, leaf_title
    )
    if not leaf_id:
        raise ValueError(
            f"No child page titled {leaf_title!r} under the resolved container page."
        )
    return normalize_page_id(leaf_id)
