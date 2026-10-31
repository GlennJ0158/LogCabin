"""SQLite data layer for QuiltBack: FABRIC, DROPDOWN, HELPTEXT, PANEL and cutting plans."""
import json
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
FABRIC_BUTTONS = ["Apply Filter", "Clear Filter", "Select All Shown"]
FILTER_FIELDS = ["FilterName", "FilterType", "FilterGrain", "FilterLengthMin", "FilterLengthMax",
                 "FilterWidthMin", "FilterWidthMax", "FilterUse"]  # FABRIC filter inputs (keys = app.py fvars)
NAV_RECORD = "Navigation"   # RECORDNAME for the screen-switching buttons (label = screen name)
NAV_BUTTONS = ["Fabric", "Panel", "Dropdown", "Helptext"]
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
    pairs += [("Fabric", f) for f in FILTER_FIELDS]  # FABRIC filter inputs
    pairs += [("Fabric", b) for b in FABRIC_BUTTONS]  # FABRIC filter buttons
    pairs += [(NAV_RECORD, b) for b in NAV_BUTTONS]  # navigation buttons

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
        rows.sort(key=lambda r: (r[fld] or 0) if isinstance(r[fld], (int, float)) or r[fld] is None
                  else _txt(r[fld]), reverse=desc)
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
        return (r["HOVERTEXT"], r["FULLHELP"]) if r else ("", "")

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
