"""SQLite data layer for the Piecing fabric inventory."""
import csv
import sqlite3

FIELDS = ["ID", "NAME", "TYPE", "COLOR", "LENGTH", "WIDTH", "GRAIN"]
GRAINS = ["Lengthwise", "Crosswise", "Bias"]
NUMERIC = {"LENGTH", "WIDTH"}


class ValidationError(ValueError):
    pass


def validate(item):
    """Return a cleaned copy of item (dict keyed by FIELDS) or raise ValidationError."""
    clean = {}
    for f in FIELDS:
        clean[f] = str(item.get(f, "") if item.get(f) is not None else "").strip()
    for f in ("ID", "NAME", "TYPE", "COLOR", "GRAIN"):
        if not clean[f]:
            raise ValidationError(f"{f} is required.")
    for f in NUMERIC:
        try:
            value = float(clean[f])
        except ValueError:
            raise ValidationError(f"{f} must be a number.") from None
        if value <= 0 or value != value or value == float("inf"):
            raise ValidationError(f"{f} must be greater than zero.")
        clean[f] = value
    if clean["GRAIN"].lower() not in [g.lower() for g in GRAINS]:
        raise ValidationError("GRAIN must be one of: " + ", ".join(GRAINS) + ".")
    clean["GRAIN"] = next(g for g in GRAINS if g.lower() == clean["GRAIN"].lower())
    return clean


class Inventory:
    def __init__(self, path="piecing.db"):
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS fabric (
                ID TEXT PRIMARY KEY, NAME TEXT NOT NULL, TYPE TEXT NOT NULL,
                COLOR TEXT NOT NULL, LENGTH REAL NOT NULL, WIDTH REAL NOT NULL,
                GRAIN TEXT NOT NULL)"""
        )
        self.conn.commit()

    def close(self):
        self.conn.close()

    def next_id(self):
        n = self.conn.execute("SELECT COUNT(*) FROM fabric").fetchone()[0] + 1
        while self.get(f"F{n:04d}"):
            n += 1
        return f"F{n:04d}"

    def get(self, item_id):
        row = self.conn.execute("SELECT * FROM fabric WHERE ID=?", (item_id,)).fetchone()
        return dict(zip(FIELDS, row)) if row else None

    def add(self, item):
        item = validate(item)
        try:
            self.conn.execute(
                "INSERT INTO fabric VALUES (?,?,?,?,?,?,?)", [item[f] for f in FIELDS]
            )
        except sqlite3.IntegrityError:
            raise ValidationError(f"ID '{item['ID']}' already exists.") from None
        self.conn.commit()

    def update(self, original_id, item):
        item = validate(item)
        if item["ID"] != original_id and self.get(item["ID"]):
            raise ValidationError(f"ID '{item['ID']}' already exists.")
        cur = self.conn.execute(
            "UPDATE fabric SET ID=?,NAME=?,TYPE=?,COLOR=?,LENGTH=?,WIDTH=?,GRAIN=? WHERE ID=?",
            [item[f] for f in FIELDS] + [original_id],
        )
        if cur.rowcount == 0:
            raise ValidationError(f"ID '{original_id}' not found.")
        self.conn.commit()

    def delete(self, item_id):
        self.conn.execute("DELETE FROM fabric WHERE ID=?", (item_id,))
        self.conn.commit()

    def list(self, sort_by=(), search=""):
        """sort_by: iterable of (field, descending) pairs. search matches any field."""
        sql, params = "SELECT * FROM fabric", []
        if search:
            sql += " WHERE " + " OR ".join(f"CAST({f} AS TEXT) LIKE ? ESCAPE '\\'" for f in FIELDS)
            like = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params = [like] * len(FIELDS)
        order = []
        for field, desc in sort_by:
            if field not in FIELDS:
                raise ValueError(f"Unknown sort field {field}")
            col = field if field in NUMERIC else f"{field} COLLATE NOCASE"
            order.append(f"{col} {'DESC' if desc else 'ASC'}")
        if order:
            sql += " ORDER BY " + ", ".join(order)
        return [dict(zip(FIELDS, r)) for r in self.conn.execute(sql, params)]

    def export_csv(self, path, rows=None):
        rows = self.list() if rows is None else rows
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
