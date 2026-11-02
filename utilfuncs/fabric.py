"""Fabric inventory: validated add/modify with sticky values and sortable listing."""
from . import dropdown
from .validation import validate_bool, validate_choice, validate_number, validate_text

LIST_FIELDS = ("Color", "Shade", "Pattern", "Type", "Grain")
SORTABLE = ("ID", "FabricName", "Color", "Shade", "Pattern", "Type", "Grain", "Length", "Width", "SqIn", "Use")


def defaults(conn):
    """Default values shown on first display or after CLEAR."""
    d = {"FabricName": "", "Length": 0, "Width": 0, "Use": 1}
    for f in LIST_FIELDS:
        d[f] = dropdown.get_default(conn, "Fabric", f) or ""
    return d


def validate(conn, v):
    """Validate a form dict; returns cleaned dict with SqIn calculated (Length x Width)."""
    out = {"FabricName": validate_text("FabricName", v.get("FabricName"), max_len=100)}
    for f in LIST_FIELDS:
        allowed = dropdown.get_list(conn, "Fabric", f)
        val = v.get(f) or None
        out[f] = validate_choice(f, val, allowed) if val is not None else None
    out["Length"] = validate_number("Length", v.get("Length"), minimum=0, decimals=3)
    out["Width"] = validate_number("Width", v.get("Width"), minimum=0, decimals=3)
    out["SqIn"] = round(out["Length"] * out["Width"], 3)
    out["Use"] = validate_bool("Use", v.get("Use", 1))
    return out


class FabricForm:
    """Form state: sticky values retained after Add/Modify (ID is not), reset by clear()."""

    def __init__(self, conn):
        self.conn = conn
        self.clear()

    def clear(self):
        self.values = defaults(self.conn)
        self.id = None

    def add(self, values):
        c = validate(self.conn, values)
        cur = self.conn.execute(
            "INSERT INTO Fabric (FabricName,Color,Shade,Pattern,Type,Grain,Length,Width,SqIn,Use) "
            "VALUES (:FabricName,:Color,:Shade,:Pattern,:Type,:Grain,:Length,:Width,:SqIn,:Use)", c)
        self.conn.commit()
        self.values, self.id = c, None
        return cur.lastrowid

    def modify(self, row_id, values):
        c = validate(self.conn, values)
        c["ID"] = row_id
        cur = self.conn.execute(
            "UPDATE Fabric SET FabricName=:FabricName,Color=:Color,Shade=:Shade,Pattern=:Pattern,"
            "Type=:Type,Grain=:Grain,Length=:Length,Width=:Width,SqIn=:SqIn,Use=:Use WHERE ID=:ID", c)
        if not cur.rowcount:
            raise ValueError(f"ID: no Fabric row with ID {row_id}")
        self.conn.commit()
        self.values, self.id = {k: v for k, v in c.items() if k != "ID"}, None


def list_rows(conn, sort_by="ID", descending=False):
    """Rows for the scrolling list, sortable by any column."""
    sort_by = validate_choice("Sort column", sort_by, SORTABLE)
    return [dict(r) for r in conn.execute(
        f'SELECT * FROM Fabric ORDER BY "{sort_by}" {"DESC" if descending else "ASC"}, ID')]
