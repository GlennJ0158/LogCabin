"""SQLite data layer for QuiltBack: FABRIC, DROPDOWN, HELPTEXT, PANEL and cutting plans."""
import csv
import io
import json
import os
import sqlite3

BASE_DROPDOWNS = [
    ("Fabric", "Type", ["Cotton", "Flannel", "Linen", "Batik", "Other"]),
    ("Fabric", "Grain", ["Lengthwise", "Crosswise", "Bias"]),
]
RECORDS = ["Fabric", "Dropdown", "Helptext"]
FIELDS = {
    "Fabric": ["Id", "Name", "Type", "Grain", "Length", "Width", "Use"],
    "Dropdown": ["Id", "RecordName", "FieldName", "Def", "Value", "Use"],
    "Helptext": ["Id", "RecordName", "FieldName", "HoverText", "FullHelp", "Use"],
}

PANEL_FIELDS = ["PanelName", "SeamAllowance", "Length", "Width", "MaxParts"]
PANEL_BUTTONS = ["Build Plan", "Save Plan", "Approve Plan", "Print Plan"]
RECORD_BUTTONS = ["Add", "Update", "Delete", "Clear"]
FABRIC_BUTTONS = ["Apply Filter", "Clear Filter", "Select All Shown", "Save Selection"]
FABRIC_SET_FIELDS = ["Title"]   # Fabric page selection-save entry (label text in the UI)
PANEL_SELECTION_FIELD = "Selection"   # Panel page dropdown: saved selection used to build the plan
NAV_RECORD = "Navigation"   # RECORDNAME for the screen-switching buttons (label = screen name)
NAV_BUTTONS = ["Fabric", "Panel", "Dropdown", "Helptext"]
FILE_BUTTONS = ["Export CSV", "Import CSV"]   # top-bar buttons for all-records CSV transfer
CSV_TABLES = ["PANEL", "FABRIC", "DROPDOWN", "HELPTEXT", "FABRICSET", "CUTPLAN"]
SEED_HOVER = "Seeding, No Help (Hover)"
SEED_FULL = "(Fullhelp) Seeding None"


SCHEMA = """
CREATE TABLE IF NOT EXISTS FABRIC(ID INTEGER PRIMARY KEY AUTOINCREMENT, NAME TEXT NOT NULL,
  TYPE TEXT, GRAIN TEXT, LENGTH REAL NOT NULL, WIDTH REAL NOT NULL, USE INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS DROPDOWN(ID INTEGER PRIMARY KEY AUTOINCREMENT, RECORDNAME TEXT NOT NULL,
  FIELDNAME TEXT NOT NULL, VALUE TEXT NOT NULL, DEF INTEGER NOT NULL DEFAULT 0, USE INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS HELPTEXT(ID INTEGER PRIMARY KEY AUTOINCREMENT, RECORDNAME TEXT NOT NULL,
  FIELDNAME TEXT NOT NULL, HOVERTEXT TEXT DEFAULT '', FULLHELP TEXT DEFAULT '', USE INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS PANEL(ID INTEGER PRIMARY KEY AUTOINCREMENT, PANELNAME TEXT NOT NULL,
  SEAMALLOWANCE REAL NOT NULL DEFAULT 0.25, LENGTH REAL NOT NULL, WIDTH REAL NOT NULL);
CREATE TABLE IF NOT EXISTS FABRICSET(ID INTEGER PRIMARY KEY AUTOINCREMENT, TITLE TEXT NOT NULL,
  FABRICIDS TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS CUTPLAN(ID INTEGER PRIMARY KEY AUTOINCREMENT, PANELID INTEGER, PLAN TEXT NOT NULL,
  APPROVED INTEGER NOT NULL DEFAULT 0);
"""


def helptext_pairs():
    """Unique (form/record, field-or-button) pairs that the UI asks help for."""
    pairs = []
    for rec in RECORDS:  # RecordForm fields
        pairs += [(rec, f) for f in FIELDS[rec][1:]]
    pairs += [("Panel", f) for f in PANEL_FIELDS]  # PanelForm fields

    for rec in RECORDS:  # RecordForm buttons
        pairs += [(rec, b) for b in RECORD_BUTTONS]
    pairs += [("Panel", b) for b in PANEL_BUTTONS]  # PanelForm buttons
    pairs += [("Fabric", b) for b in FABRIC_BUTTONS]  # FABRIC filter buttons
    pairs += [("Fabric", f) for f in FABRIC_SET_FIELDS]  # FABRIC selection-save title
    pairs += [("Panel", PANEL_SELECTION_FIELD)]  # PANEL saved-selection dropdown
    pairs += [(NAV_RECORD, b) for b in NAV_BUTTONS]  # navigation buttons
    pairs += [(NAV_RECORD, b) for b in FILE_BUTTONS]  # CSV export/import buttons

    seen, out = set(), []
    for r, f in pairs:  # de-dupe, keep order
        k = (r.upper(), f.upper())
        if k not in seen:
            seen.add(k)
            out.append((r, f))
    return out


def _txt(v):
    return str(v if v is not None else "").lower()


# display sort per record: (field, descending) in priority order
SORTS = {
    "Fabric": [("USE", True), ("TYPE", False), ("NAME", False), ("LENGTH", False), ("WIDTH", False)],
    "Helptext": [("RECORDNAME", False), ("FIELDNAME", False), ("USE", True), ("HOVERTEXT", False)],
}


def sort_rows(name, rows):
    """Order rows for display per SORTS (stable multi-key sort, text case-insensitive)."""
    rows = list(rows)
    for fld, desc in reversed(SORTS.get(name, [])):
        rows.sort(key=lambda r: r[fld] if isinstance(r[fld], (int, float)) else _txt(r[fld]), reverse=desc)
    return rows


def filter_fabric(rows, name="", type_="", grain="", length_min=None, length_max=None,
                  width_min=None, width_max=None, use=None):
    """Return the FABRIC rows matching every supplied criterion (blank/None = no restriction)."""
    out = []
    for r in rows:
        if name and name.lower() not in (r["NAME"] or "").lower():
            continue
        if type_ and (r["TYPE"] or "").lower() != type_.lower():
            continue
        if grain and (r["GRAIN"] or "").lower() != grain.lower():
            continue
        if length_min is not None and r["LENGTH"] < length_min:
            continue
        if length_max is not None and r["LENGTH"] > length_max:
            continue
        if width_min is not None and r["WIDTH"] < width_min:
            continue
        if width_max is not None and r["WIDTH"] > width_max:
            continue
        if use is not None and bool(r["USE"]) != bool(use):
            continue
        out.append(r)
    return out


class DB:
    def __init__(self, path="quiltback.db"):
        self.c = sqlite3.connect(path)
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)
        if not self.c.execute("SELECT 1 FROM DROPDOWN").fetchone():
            self._seed()
        self.seed_helptext()
        self.seed_helptext_dropdowns()

    def _seed(self):
        rows = list(BASE_DROPDOWNS)
        rows.append(("Dropdown", "RecordName", RECORDS))
        rows.append(("Dropdown", "FieldName", [f for r in RECORDS for f in FIELDS[r][1:]]))
        for rec, fld, vals in rows:
            for v in vals:
                self.c.execute("INSERT INTO DROPDOWN(RECORDNAME,FIELDNAME,VALUE) VALUES(?,?,?)", (rec, fld, v))
        self.c.commit()

    def seed_helptext_dropdowns(self):
        """Idempotently make every HELPTEXT record/field name selectable (forms, fields and buttons)."""
        pairs = helptext_pairs()
        recs = list(dict.fromkeys(r for r, _ in pairs))
        flds = list(dict.fromkeys(f for _, f in pairs))
        for fld, vals in (("RecordName", recs), ("FieldName", flds)):
            for v in vals:
                self.c.execute(
                    "INSERT INTO DROPDOWN(RECORDNAME,FIELDNAME,VALUE) SELECT 'Helptext',?,? WHERE NOT EXISTS ("
                    "SELECT 1 FROM DROPDOWN WHERE UPPER(RECORDNAME)='HELPTEXT' AND UPPER(FIELDNAME)=UPPER(?) "
                    "AND UPPER(VALUE)=UPPER(?))", (fld, v, fld, v))
        self.c.commit()

    def seed_helptext(self):
        """Idempotently add HELPTEXT rows for every field/button pair used by the UI."""
        added = 0
        for rec, fld in helptext_pairs():
            cur = self.c.execute(
                "INSERT INTO HELPTEXT(RECORDNAME,FIELDNAME,HOVERTEXT,FULLHELP,USE) "
                "SELECT ?,?,?,?,1 WHERE NOT EXISTS ("
                "SELECT 1 FROM HELPTEXT WHERE UPPER(RECORDNAME)=UPPER(?) AND UPPER(FIELDNAME)=UPPER(?))",
                (rec, fld, SEED_HOVER, SEED_FULL, rec, fld),
            )
            added += cur.rowcount
        self.c.commit()
        return added

    # generic CRUD
    def list(self, table):
        return [dict(r) for r in self.c.execute(f"SELECT * FROM {table.upper()} ORDER BY ID")]

    def add(self, table, **vals):
        cols = ",".join(vals)
        cur = self.c.execute(f"INSERT INTO {table.upper()}({cols}) VALUES({','.join('?' * len(vals))})",
                             list(vals.values()))
        self.c.commit()
        return cur.lastrowid

    def update(self, table, id_, **vals):
        sets = ",".join(f"{k}=?" for k in vals)
        self.c.execute(f"UPDATE {table.upper()} SET {sets} WHERE ID=?", list(vals.values()) + [id_])
        self.c.commit()

    def delete(self, table, id_):
        self.c.execute(f"DELETE FROM {table.upper()} WHERE ID=?", (id_,))
        self.c.commit()

    def update_many(self, table, ids, **vals):
        """Apply the same column changes to every record in ids, atomically."""
        if not ids or not vals:
            return
        sets = ",".join(f"{k}=?" for k in vals)
        self.c.executemany(f"UPDATE {table.upper()} SET {sets} WHERE ID=?",
                           [list(vals.values()) + [i] for i in ids])
        self.c.commit()

    def delete_many(self, table, ids):
        self.c.executemany(f"DELETE FROM {table.upper()} WHERE ID=?", [(i,) for i in ids])
        self.c.commit()

    # dropdowns
    def dropdown(self, record, field):
        """Return (values, default, error). Multiple DEF rows: error message, last wins."""
        rows = self.c.execute(
            "SELECT VALUE, DEF FROM DROPDOWN WHERE UPPER(RECORDNAME)=UPPER(?) AND UPPER(FIELDNAME)=UPPER(?) "
            "AND USE=1 ORDER BY ID", (record, field)).fetchall()
        defs = [r["VALUE"] for r in rows if r["DEF"]]
        err = None
        if len(defs) > 1:
            err = f"Multiple defaults for {record}.{field}: {', '.join(defs)}. Using '{defs[-1]}'."
        # list order: default value(s) first (Def), then Value alphabetically
        ordered = sorted(rows, key=lambda r: (not r["DEF"], r["VALUE"].lower()))
        return [r["VALUE"] for r in ordered], (defs[-1] if defs else None), err

    # help
    def helptext(self, record, field):
        r = self.c.execute(
            "SELECT HOVERTEXT, FULLHELP FROM HELPTEXT WHERE UPPER(RECORDNAME)=UPPER(?) AND UPPER(FIELDNAME)=UPPER(?) "
            "AND USE=1 ORDER BY ID DESC", (record, field)).fetchone()
        return (r["HOVERTEXT"] or "", r["FULLHELP"] or "") if r else ("", "")

    # fabric selections
    def save_fabric_set(self, title, fabric_ids):
        """Store a titled snapshot of selected FABRIC IDs (saved as JSON, like CUTPLAN.PLAN)."""
        if not str(title or "").strip():
            raise ValueError("Title is required")
        ids = [int(i) for i in fabric_ids]
        if not ids:
            raise ValueError("Select at least one fabric record")
        return self.add("FABRICSET", TITLE=title.strip(), FABRICIDS=json.dumps(ids))

    def fabrics_in_set(self, set_id):
        """FABRIC rows (ID order) whose IDs are stored in FABRICSET set_id. Deleted fabrics are ignored."""
        row = self.c.execute("SELECT FABRICIDS FROM FABRICSET WHERE ID=?", (set_id,)).fetchone()
        if row is None:
            raise ValueError(f"Saved selection {set_id} not found")
        ids = set(json.loads(row["FABRICIDS"]))
        return [f for f in self.list("FABRIC") if f["ID"] in ids]

    # CSV transfer: one file per table, named QuiltBack_<TABLE>.csv
    def _columns(self, table):
        """Return (name, declared_type, not_null) triples for table, in column order."""
        return [(r["name"], (r["type"] or "").upper(), bool(r["notnull"]))
                for r in self.c.execute(f"PRAGMA table_info({table})")]

    def export_csv(self, folder):
        os.makedirs(folder, exist_ok=True)
        written = []
        for t in CSV_TABLES:
            cols = [n for n, _, _ in self._columns(t)]
            path = os.path.join(folder, f"QuiltBack_{t}.csv")
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                for r in self.c.execute(f"SELECT {','.join(cols)} FROM {t} ORDER BY ID"):
                    w.writerow(["" if v is None else v for v in r])
            written.append(path)
        return written

    def import_csv(self, folder):
        """Upsert every QuiltBack_<TABLE>.csv in folder, matching rows by ID. All-or-nothing.
        Missing files are skipped. Returns {table: {"found", "input", "added", "modified"}}.
        Raises ValueError (naming the file) on unreadable, bad-header or bad-value files."""
        summary = {}
        try:
            for t in CSV_TABLES:
                stats = {"found": False, "input": 0, "added": 0, "modified": 0}
                summary[t] = stats
                path = os.path.join(folder, f"QuiltBack_{t}.csv")
                if not os.path.exists(path):
                    continue
                stats["found"] = True
                name = os.path.basename(path)
                text = self._read_text(path)
                types = {cname: (ctype, cnn) for cname, ctype, cnn in self._columns(t)}
                reader = csv.DictReader(io.StringIO(text, newline=""))
                unknown = [c for c in (reader.fieldnames or []) if c not in types]
                if unknown or "ID" not in (reader.fieldnames or []):
                    raise ValueError(f"{name}: header must include ID and only known columns "
                                     f"(bad: {', '.join(unknown) or 'ID missing'})")
                try:
                    for raw in reader:
                        row = {k: self._csv_value(v, *types[k]) for k, v in raw.items()}
                        stats["input"] += 1
                        stats[self._upsert(t, row)] += 1
                except (ValueError, sqlite3.Error) as e:
                    raise ValueError(f"{name}, record {stats['input'] + 1}: {e}") from e
            self.c.commit()
        except Exception:
            self.c.rollback()
            raise
        return summary

    @staticmethod
    def _read_text(path):
        """Read a CSV as UTF-8 (BOM allowed); fall back to Windows-1252, which Excel writes by default."""
        with open(path, "rb") as fh:
            data = fh.read()
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            try:
                return data.decode("cp1252")
            except UnicodeDecodeError:
                name = os.path.basename(path)
                raise ValueError(f"{name}: not UTF-8 or Windows-1252 text; byte 0x{data[e.start]:02X} at "
                                 f"offset {e.start} is invalid. Re-save the file as CSV UTF-8 and retry.") from e

    @staticmethod
    def _csv_value(text, decl_type, not_null):
        """Blank cells: NULL, except NOT NULL text columns keep ''. Numeric blanks become NULL."""
        if text == "":
            return "" if ("TEXT" in decl_type and not_null) else None
        return text

    def _upsert(self, table, row):
        """Insert or overwrite one row. Returns 'added' or 'modified'."""
        if row.get("ID") in (None, ""):
            row = {k: v for k, v in row.items() if k != "ID"}
            self.c.execute(f"INSERT INTO {table}({','.join(row)}) VALUES({','.join('?' * len(row))})",
                           list(row.values()))
            return "added"
        id_ = int(row["ID"])
        row["ID"] = id_
        exists = self.c.execute(f"SELECT 1 FROM {table} WHERE ID=?", (id_,)).fetchone()
        others = {k: v for k, v in row.items() if k != "ID"}
        if exists:
            sets = ",".join(f"{k}=?" for k in others)
            self.c.execute(f"UPDATE {table} SET {sets} WHERE ID=?", list(others.values()) + [id_])
            return "modified"
        self.c.execute(f"INSERT INTO {table}({','.join(row)}) VALUES({','.join('?' * len(row))})",
                       list(row.values()))
        return "added"

    # plans
    def save_plan(self, panel_id, plan):
        return self.add("CUTPLAN", PANELID=panel_id, PLAN=json.dumps(plan))

    def approve_plan(self, plan_id):
        """Mark approved and subtract consumed material from inventory."""
        row = self.c.execute("SELECT PLAN, APPROVED FROM CUTPLAN WHERE ID=?", (plan_id,)).fetchone()
        if row is None or row["APPROVED"]:
            raise ValueError("Plan missing or already approved")
        plan = json.loads(row["PLAN"])
        for cut in plan["cuts"]:
            f = self.c.execute("SELECT LENGTH FROM FABRIC WHERE ID=?", (cut["fabric_id"],)).fetchone()
            if f is None:
                raise ValueError(f"Fabric {cut['fabric_id']} no longer exists")
            left = round(f["LENGTH"] - cut["consumed_length"], 4)
            if left < 0:
                raise ValueError(f"Fabric {cut['fabric_id']} has insufficient length")
            self.c.execute("UPDATE FABRIC SET LENGTH=?, USE=? WHERE ID=?", (left, 1 if left > 0 else 0, cut["fabric_id"]))
        self.c.execute("UPDATE CUTPLAN SET APPROVED=1 WHERE ID=?", (plan_id,))
        self.c.commit()
