"""HelpText table: seeding, lookup and RTF handling."""
import re

from .db import table_fields, tables


def seed(conn, extra_items=()):
    """Insert a HelpText row for every table/field (and extra (form, item) tuples) lacking one."""
    pairs = [(t, f) for t in tables(conn) for f in table_fields(conn, t)]
    pairs += list(extra_items)
    for t, f in pairs:
        conn.execute("INSERT OR IGNORE INTO HelpText (TableName, FieldName) VALUES (?,?)", (t, f))
    conn.commit()


def hover_text(conn, table, field):
    """Tool tip text for a field."""
    r = conn.execute("SELECT HoverText FROM HelpText WHERE TableName=? AND FieldName=? AND Use=1",
                     (table, field)).fetchone()
    return r["HoverText"] if r else "No Tool Tip"


def full_text(conn, table, field):
    """Return (text, is_rich) for F1 help; RTF is converted to plain text when displayed."""
    r = conn.execute("SELECT FullText, RT FROM HelpText WHERE TableName=? AND FieldName=? AND Use=1",
                     (table, field)).fetchone()
    if not r:
        return "No help yet", False
    return (rtf_to_text(r["FullText"]) if r["RT"] else r["FullText"]), bool(r["RT"])


def rtf_to_text(rtf):
    """Minimal RTF to plain text conversion for display."""
    s = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), rtf)
    s = re.sub(r"\\(par|line)\b ?", "\n", s)
    s = re.sub(r"\\tab\b ?", "\t", s)
    s = re.sub(r"\{\\\*[^{}]*\}", "", s)
    s = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", s)
    s = re.sub(r"\\([\\{}])", r"\1", s)
    return s.replace("{", "").replace("}", "").strip()
