"""CSV export and import of every row of every table in one file.

The delimiter is '~' because it does not occur in HelpText or DropDown text.
The first column, 'Table', names the table each row belongs to. The remaining
columns are the union of all table fields; cells for fields a row's table does
not have are blank. Import upserts rows by ID inside one transaction, so a
failed import leaves the database unchanged.
"""
import csv

from .db import table_fields, tables
from .validation import ValidationError

DELIMITER = "~"
TABLE_COLUMN = "Table"


def export_csv(conn, path):
    """Write all rows of all tables to path. Returns {table: row_count}."""
    names = tables(conn)
    fields = {t: table_fields(conn, t) for t in names}
    columns = []
    for t in names:
        columns += [f for f in fields[t] if f not in columns]
    counts = {}
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=DELIMITER)
        w.writerow([TABLE_COLUMN] + columns)
        for t in names:
            rows = conn.execute(f'SELECT * FROM "{t}" ORDER BY ID').fetchall()
            counts[t] = len(rows)
            for r in rows:
                w.writerow([t] + ["" if c not in fields[t] or r[c] is None else r[c] for c in columns])
    return counts


def import_csv(conn, path):
    """Upsert rows from a file written by export_csv. Returns {table: row_count}.

    Rows are matched by ID; new IDs are inserted and existing IDs are overwritten.
    Blank cells become NULL for nullable columns. Any error rolls back everything.
    """
    known = {t: table_fields(conn, t) for t in tables(conn)}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=DELIMITER)
        if not reader.fieldnames or reader.fieldnames[0] != TABLE_COLUMN:
            raise ValidationError(TABLE_COLUMN, f"first column must be '{TABLE_COLUMN}'")
        rows = list(reader)
    counts = {}
    try:
        conn.commit()
        conn.execute("BEGIN")
        conn.execute("PRAGMA defer_foreign_keys = ON")
        for line_no, row in enumerate(rows, start=2):
            t = row[TABLE_COLUMN]
            if t not in known:
                raise ValidationError(TABLE_COLUMN, f"line {line_no}: unknown table '{t}'")
            info = {r["name"]: r for r in conn.execute(f'PRAGMA table_info("{t}")')}
            try:
                row_id = int(row.get("ID", ""))
            except ValueError:
                raise ValidationError("ID", f"line {line_no}: '{row.get('ID', '')}' is not an integer")
            cols = known[t]
            values = {}
            for f in cols:
                raw = row.get(f, "")
                values[f] = None if raw == "" and not info[f]["notnull"] else raw
            values["ID"] = row_id
            names = ", ".join(f'"{c}"' for c in cols)
            marks = ", ".join("?" for _ in cols)
            if "ID" not in cols:
                raise ValidationError("ID", f"table '{t}' has no ID column")
            updates = ", ".join(f'"{c}"=excluded."{c}"' for c in cols if c != "ID")
            conn.execute(
                f'INSERT INTO "{t}" ({names}) VALUES ({marks}) '
                f'ON CONFLICT(ID) DO UPDATE SET {updates}',
                [values[c] for c in cols])
            counts[t] = counts.get(t, 0) + 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return counts
