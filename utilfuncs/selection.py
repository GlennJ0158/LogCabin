"""Row selection: filter, invert, collapse, save and set operations."""
from .validation import ValidationError, validate_bool, validate_number, validate_text


def filter_rows(conn, table, numeric=None, binary=None, include_unused=False):
    """Return IDs matching filters.

    numeric: {field: (min, max)} inclusive; either bound may be blank/None.
    binary: {field: 1|0|''}; blank ignores the field.
    """
    fields = [r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    if not fields:
        raise ValidationError("TableName", f"unknown table '{table}'")
    where, args = [], []
    for f, (lo, hi) in (numeric or {}).items():
        if f not in fields:
            raise ValidationError(f, f"not a field of {table}")
        lo = validate_number(f"{f} minimum", lo, required=False)
        hi = validate_number(f"{f} maximum", hi, required=False)
        if lo is not None:
            where.append(f'"{f}" >= ?'); args.append(lo)
        if hi is not None:
            where.append(f'"{f}" <= ?'); args.append(hi)
    for f, v in (binary or {}).items():
        if f not in fields:
            raise ValidationError(f, f"not a field of {table}")
        if v in ("", None):
            continue
        where.append(f'"{f}" = ?'); args.append(validate_bool(f, v))
    if not include_unused and "Use" in fields and "Use" not in (binary or {}):
        where.append('"Use" = 1')
    sql = f'SELECT ID FROM "{table}"' + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY ID"
    return [r["ID"] for r in conn.execute(sql, args)]


def invert(conn, table, selected, include_unused=False):
    """Selected rows are released, unselected rows selected. Use=0 rows skipped unless requested."""
    sel = set(selected)
    return [i for i in filter_rows(conn, table, include_unused=include_unused) if i not in sel]


def select_highlighted(selected, highlighted):
    """Collapse the selection to the highlighted rows (if any are highlighted)."""
    hl = set(highlighted)
    return [i for i in selected if i in hl] if hl else list(selected)


def _selection(conn, name):
    r = conn.execute("SELECT ID, TableName FROM Selection WHERE SelectionName=?", (name,)).fetchone()
    if not r:
        raise ValidationError("SelectionName", f"no saved selection named '{name}'")
    return r


def saved_ids(conn, name):
    sid = _selection(conn, name)["ID"]
    return [r["RowID"] for r in conn.execute(
        "SELECT RowID FROM SelectedRows WHERE SelectionID=? ORDER BY RowID", (sid,))]


def _refresh_count(conn, sid):
    conn.execute("UPDATE Selection SET RowCount=(SELECT COUNT(*) FROM SelectedRows WHERE SelectionID=?) "
                 "WHERE ID=?", (sid, sid))


def save(conn, table, name, ids):
    """Save a new named selection; returns number saved. RowCount is the real entry count."""
    name = validate_text("SelectionName", name, max_len=100)
    if conn.execute("SELECT 1 FROM Selection WHERE SelectionName=?", (name,)).fetchone():
        raise ValidationError("SelectionName", f"'{name}' already exists")
    sid = conn.execute("INSERT INTO Selection (SelectionName, TableName) VALUES (?,?)",
                       (name, table)).lastrowid
    conn.executemany("INSERT OR IGNORE INTO SelectedRows (SelectionID, RowID) VALUES (?,?)",
                     [(sid, i) for i in set(ids)])
    _refresh_count(conn, sid)
    conn.commit()
    return len(set(ids))


def add_to_saved(conn, name, ids):
    """Add rows to a saved selection (unique). Returns (count_before, count_after)."""
    s = _selection(conn, name)
    before = len(saved_ids(conn, name))
    conn.executemany("INSERT OR IGNORE INTO SelectedRows (SelectionID, RowID) VALUES (?,?)",
                     [(s["ID"], i) for i in set(ids)])
    _refresh_count(conn, s["ID"])
    conn.commit()
    return before, len(saved_ids(conn, name))


def remove_from_saved(conn, name, ids):
    """Remove rows from a saved selection. Returns (count_before, count_after)."""
    s = _selection(conn, name)
    before = len(saved_ids(conn, name))
    conn.executemany("DELETE FROM SelectedRows WHERE SelectionID=? AND RowID=?",
                     [(s["ID"], i) for i in set(ids)])
    _refresh_count(conn, s["ID"])
    conn.commit()
    return before, len(saved_ids(conn, name))


def intersect(conn, name, current):
    """Keep only current rows that are also saved. Returns (count_before, new_current)."""
    saved = set(saved_ids(conn, name))
    return len(saved), [i for i in current if i in saved]
