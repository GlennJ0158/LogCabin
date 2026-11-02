"""DropDown table: seeding, static lists, dynamic lists, defaults."""
import warnings

from .db import table_fields, tables

# Static lists: (TableName, FieldName) -> (items, default)
STATIC_LISTS = {
    ("Fabric", "Color"): (["Red", "Yellow", "Blue"], None),
    ("Fabric", "Shade"): (["Dark", "Medium", "Light"], None),
    ("Fabric", "Pattern"): (["Solid", "Floral", "Geometric", "Other"], None),
    ("Fabric", "Type"): (["Cotton", "Linen", "Silk", "Wool", "Synthetic", "Other"], None),
    ("Fabric", "Grain"): (["Lengthwise", "Crosswise", "Bias", "None"], "Lengthwise"),
}


def seed(conn, lists=None):
    """Seed static lists only for fields that have no DropDown rows yet."""
    for (table, field), (items, default) in (lists or STATIC_LISTS).items():
        n = conn.execute("SELECT COUNT(*) FROM DropDown WHERE TableName=? AND FieldName=?",
                         (table, field)).fetchone()[0]
        if n:
            continue
        for item in items:
            conn.execute("INSERT INTO DropDown (TableName, FieldName, ListItem, Def) VALUES (?,?,?,?)",
                         (table, field, item, 1 if item == default else 0))
    conn.commit()


def get_list(conn, table, field):
    """Return list items sorted Def (default first), TableName, FieldName, ListItem. Use=0 ignored."""
    rows = conn.execute(
        "SELECT ListItem FROM DropDown WHERE TableName=? AND FieldName=? AND Use=1 "
        "ORDER BY Def DESC, TableName, FieldName, ListItem", (table, field)).fetchall()
    return [r["ListItem"] for r in rows]


def get_default(conn, table, field):
    """Return the default item; warn (naming the field) if several rows have Def=1."""
    rows = conn.execute(
        "SELECT ListItem FROM DropDown WHERE TableName=? AND FieldName=? AND Use=1 AND Def=1 "
        "ORDER BY ID", (table, field)).fetchall()
    if len(rows) > 1:
        warnings.warn(f"DropDown {table}.{field}: {len(rows)} rows have Def=TRUE; "
                      f"using first '{rows[0]['ListItem']}'")
    return rows[0]["ListItem"] if rows else None


def table_choices(conn):
    """Choices for the DropDown.TableName field."""
    return tables(conn)


def field_choices(conn, table):
    """Choices for DropDown.FieldName, limited to the chosen table (hierarchical)."""
    return table_fields(conn, table)


def selection_names(conn, table):
    """Dynamic list: saved Selection names for a table, built on each call."""
    return [r["SelectionName"] for r in conn.execute(
        "SELECT SelectionName FROM Selection WHERE TableName=? ORDER BY SelectionName", (table,))]
