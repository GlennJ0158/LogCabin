"""Data layer for QuiltBack. Fabric, DropDown, HelpText, Selection and CSV come from utilfuncs;
PANEL and CUTPLAN are QuiltBack-only tables kept in the same database."""
import json

from utilfuncs import csvio, dropdown, fabric, helptext, selection
from utilfuncs.db import connect
from utilfuncs.validation import ValidationError

RECORDS = ["Fabric", "Dropdown", "Helptext"]   # maintenance screens
TABLES = {"Fabric": "Fabric", "Dropdown": "DropDown", "Helptext": "HelpText"}
FIELDS = {   # form fields (ID is never edited)
    "Fabric": ["FabricName", "Color", "Shade", "Pattern", "Type", "Grain", "Length", "Width", "Use"],
    "Dropdown": ["TableName", "FieldName", "ListItem", "Def", "Use"],
    "Helptext": ["TableName", "FieldName", "HoverText", "FullText", "RT", "Use"],
}
COLUMNS = {   # list columns, including ID and the computed SqIn
    "Fabric": ["ID", "FabricName", "Color", "Shade", "Pattern", "Type", "Grain", "Length", "Width", "SqIn", "Use"],
    "Dropdown": ["ID"] + FIELDS["Dropdown"],
    "Helptext": ["ID"] + FIELDS["Helptext"],
}
REQUIRED = {"TableName", "FieldName", "ListItem"}

PANEL_FIELDS = ["PANELNAME", "SEAMALLOWANCE", "LENGTH", "WIDTH", "MAXPARTS"]   # keys = PanelForm fields
PANEL_BUTTONS = ["Build Plan", "Save Plan", "Approve Plan", "Print Plan"]
RECORD_BUTTONS = ["Add", "Update", "Delete", "Clear"]
FILTER_FIELDS = ["Filter" + k for k in ("Name", "Color", "Shade", "Pattern", "Type", "Grain",
                                         "LengthMin", "LengthMax", "WidthMin", "WidthMax", "Use")]
FABRIC_BUTTONS = ["Apply Filter", "Clear Filter", "Select All Shown", "Select Highlighted", "Invert Selection",
                  "Save Selection", "Add to Selection", "Remove From Selection", "Activate Selection"]
FABRIC_SET_FIELDS = ["Title", "NamedSelection"]   # Fabric page selection entries (keys = app.py widgets)
PANEL_SELECTION_FIELD = "Selection"   # Panel page dropdown: saved selection used to build the plan
PANEL_CASE_FIELD = "Case"   # Panel page layout choice: symmetric (equal cells) or variable (strips)
PANEL_CASES = ["Symmetric", "Variable"]
NAV_RECORD = "Navigation"   # TableName for the screen-switching buttons (label = screen name)
NAV_BUTTONS = ["Fabric", "Panel", "Dropdown", "Helptext"]
FILE_BUTTONS = ["Export CSV", "Import CSV", "User Manual"]   # top-bar buttons: CSV transfer and manual
RETAIN = {   # fields kept after Add/Update (the rest reset to blank or default)
    "Fabric": {"Color", "Shade", "Pattern", "Type", "Grain", "Length", "Width"},
    "Dropdown": {"TableName", "FieldName"},
    "Helptext": {"TableName", "FieldName"},
}

LOCAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS PANEL(ID INTEGER PRIMARY KEY AUTOINCREMENT, PANELNAME TEXT NOT NULL,
  SEAMALLOWANCE REAL NOT NULL DEFAULT 0.25, LENGTH REAL NOT NULL, WIDTH REAL NOT NULL);
CREATE TABLE IF NOT EXISTS CUTPLAN(ID INTEGER PRIMARY KEY AUTOINCREMENT, PANELID INTEGER, PLAN TEXT NOT NULL,
  APPROVED INTEGER NOT NULL DEFAULT 0);
"""


def helptext_pairs():
    """Unique (TableName, FieldName) pairs of help keys that the UI asks for."""
    pairs = []
    for rec in RECORDS:
        pairs += [(rec, f) for f in FIELDS[rec]] + [(rec, b) for b in RECORD_BUTTONS]
    pairs += [("Panel", f) for f in PANEL_FIELDS] + [("Panel", b) for b in PANEL_BUTTONS]
    pairs += [("Fabric", f) for f in FILTER_FIELDS] + [("Fabric", b) for b in FABRIC_BUTTONS]
    pairs += [("Fabric", f) for f in FABRIC_SET_FIELDS]
    pairs += [("Panel", PANEL_SELECTION_FIELD), ("Panel", PANEL_CASE_FIELD)] + [("Panel", c) for c in PANEL_CASES]
    pairs += [(NAV_RECORD, b) for b in NAV_BUTTONS + FILE_BUTTONS]
    return list(dict.fromkeys(pairs))


# display sort per record: (field, descending) in priority order
SORTS = {
    "Fabric": [("Use", True), ("Type", False), ("FabricName", False), ("Length", False), ("Width", False)],
    "Helptext": [("TableName", False), ("FieldName", False), ("Use", True), ("HoverText", False)],
}


def _txt(v):
    return str(v if v is not None else "").lower()


def sort_rows(name, rows):
    """Order rows for display per SORTS (stable multi-key sort, text case-insensitive)."""
    rows = list(rows)
    for fld, desc in reversed(SORTS.get(name, [])):
        rows.sort(key=lambda r: r[fld] if isinstance(r[fld], (int, float)) else _txt(r[fld]), reverse=desc)
    return rows


class DB:
    def __init__(self, path="quiltback.db"):
        self.c = connect(path)
        self.c.executescript(LOCAL_SCHEMA)
        dropdown.seed(self.c)
        helptext.seed(self.c, extra_items=helptext_pairs())

    # records (Fabric, Dropdown, Helptext)
    def list(self, name):
        if name == "Fabric":
            return fabric.list_rows(self.c)
        return [dict(r) for r in self.c.execute(f"SELECT * FROM {TABLES[name]} ORDER BY ID")]

    def add(self, name, vals):
        if name == "Fabric":
            return fabric.FabricForm(self.c).add(vals)
        vals = self._required(vals)
        cur = self.c.execute(f"INSERT INTO {TABLES[name]}({','.join(vals)}) VALUES({','.join('?' * len(vals))})",
                             list(vals.values()))
        self.c.commit()
        return cur.lastrowid

    def update_many(self, name, ids, changes):
        """Apply the changed fields to every record in ids, all or nothing. Fabric rows are re-validated whole."""
        if not ids or not changes:
            return
        if name == "Fabric":
            current = {r["ID"]: r for r in self.list("Fabric")}
            batch = []
            for i in ids:
                if i not in current:
                    raise ValueError(f"ID: no Fabric row with ID {i}")
                batch.append((i, {**current[i], **changes}))
            for _, vals in batch:
                fabric.validate(self.c, vals)
            form = fabric.FabricForm(self.c)
            for i, vals in batch:
                form.modify(i, vals)
            return
        changes = self._required(changes)
        sets = ",".join(f"{k}=?" for k in changes)
        self.c.executemany(f"UPDATE {TABLES[name]} SET {sets} WHERE ID=?",
                           [[*changes.values(), i] for i in ids])
        self.c.commit()

    def delete_many(self, name, ids):
        self.c.executemany(f"DELETE FROM {TABLES[name]} WHERE ID=?", [(i,) for i in ids])
        self.c.commit()

    @staticmethod
    def _required(vals):
        for f in REQUIRED & set(vals):
            if not str(vals[f] or "").strip():
                raise ValidationError(f, "a value is required")
        return vals

    # choices and defaults
    def defaults(self, name):
        """Default choice values applied on first display and after Clear (Fabric list fields only)."""
        if name != "Fabric":
            return {}
        return {f: dropdown.get_default(self.c, "Fabric", f) or "" for f in fabric.LIST_FIELDS}

    def choices(self, name, field, table=None):
        """Choice list for a record field: Fabric dropdown lists, and the Dropdown/Helptext name fields."""
        if name == "Fabric":
            return dropdown.get_list(self.c, "Fabric", field)
        if name == "Dropdown" and field == "TableName":
            return dropdown.table_choices(self.c)
        if name == "Dropdown" and field == "FieldName":
            try:
                return dropdown.field_choices(self.c, table or "")
            except ValueError:
                return []
        col = "TableName" if field == "TableName" else "FieldName"
        return [r[0] for r in self.c.execute(f"SELECT DISTINCT {col} FROM HelpText ORDER BY {col}")]

    def helptext(self, record, field):
        """(hover text, full text) for a help key."""
        return helptext.hover_text(self.c, record, field), helptext.full_text(self.c, record, field)[0]

    # fabric filter
    def filter_fabric(self, name="", color="", shade="", pattern="", type_="", grain="",
                      length=(None, None), width=(None, None), use=None):
        """Fabric rows matching every criterion; blank text and None numbers do not restrict."""
        ids = set(selection.filter_rows(self.c, "Fabric", numeric={"Length": length, "Width": width},
                                        binary={"Use": use}, include_unused=True))
        needle = name.strip().lower()
        wanted = {"Color": color, "Shade": shade, "Pattern": pattern, "Type": type_, "Grain": grain}
        out = []
        for r in self.list("Fabric"):
            if r["ID"] not in ids:
                continue
            if needle and needle not in (r["FabricName"] or "").lower():
                continue
            if any(v and (r[f] or "").lower() != v.lower() for f, v in wanted.items()):
                continue
            out.append(r)
        return out

    # saved fabric selections (utilfuncs Selection with TableName 'Fabric')
    def save_selection(self, title, ids):
        if not ids:
            raise ValueError("Select at least one fabric record")
        return selection.save(self.c, "Fabric", title, list(ids))

    def selection_names(self):
        return dropdown.selection_names(self.c, "Fabric")

    def selection_ids(self, name):
        return set(selection.saved_ids(self.c, name))

    def fabrics_in_selection(self, name):
        keep = self.selection_ids(name)
        return [r for r in self.list("Fabric") if r["ID"] in keep]

    def change_selection(self, name, ids, add):
        """Add ids to (add=True) or remove them from (add=False) a saved selection."""
        (selection.add_to_saved if add else selection.remove_from_saved)(self.c, name, list(ids))

    # panels and cutting plans
    def add_panel(self, name, seam, length, width):
        cur = self.c.execute("INSERT INTO PANEL(PANELNAME,SEAMALLOWANCE,LENGTH,WIDTH) VALUES(?,?,?,?)",
                             (name, seam, length, width))
        self.c.commit()
        return cur.lastrowid

    def save_plan(self, panel_id, plan):
        cur = self.c.execute("INSERT INTO CUTPLAN(PANELID,PLAN) VALUES(?,?)", (panel_id, json.dumps(plan)))
        self.c.commit()
        return cur.lastrowid

    def approve_plan(self, plan_id):
        """Mark approved and subtract consumed fabric length from inventory."""
        row = self.c.execute("SELECT PLAN, APPROVED FROM CUTPLAN WHERE ID=?", (plan_id,)).fetchone()
        if row is None or row["APPROVED"]:
            raise ValueError("Plan missing or already approved")
        plan = json.loads(row["PLAN"])
        for cut in plan["cuts"]:
            f = self.c.execute("SELECT Length, Width FROM Fabric WHERE ID=?", (cut["fabric_id"],)).fetchone()
            if f is None:
                raise ValueError(f"Fabric {cut['fabric_id']} no longer exists")
            left = round(f["Length"] - cut["consumed_length"], 4)
            if left < 0:
                raise ValueError(f"Fabric {cut['fabric_id']} has insufficient length")
            self.c.execute("UPDATE Fabric SET Length=?, SqIn=?, Use=? WHERE ID=?",
                           (left, round(left * f["Width"], 3), 1 if left > 0 else 0, cut["fabric_id"]))
        self.c.execute("UPDATE CUTPLAN SET APPROVED=1 WHERE ID=?", (plan_id,))
        self.c.commit()

    # CSV: one file with every row of every table (utilfuncs csvio, '~' delimited)
    def export_csv(self, path):
        return csvio.export_csv(self.c, path)

    def import_csv(self, path):
        return csvio.import_csv(self.c, path)
