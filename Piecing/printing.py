"""Printing support: renders inventory to an HTML file and sends it to the printer."""
import html
import os
import tempfile

from database import FIELDS


def render_html(rows):
    head = "".join(f"<th>{f}</th>" for f in FIELDS)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(r[f]))}</td>" for f in FIELDS) + "</tr>"
        for r in rows
    )
    return (
        "<html><head><title>Fabric Inventory</title><style>"
        "table{border-collapse:collapse}td,th{border:1px solid #444;padding:4px 8px}"
        f"</style></head><body><h1>Fabric Inventory</h1><table><tr>{head}</tr>{body}</table></body></html>"
    )


def print_rows(rows):
    """Print on Windows via the default handler; elsewhere open the file. Returns the path."""
    fd, path = tempfile.mkstemp(suffix=".html", prefix="piecing_")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(render_html(rows))
    if hasattr(os, "startfile"):
        os.startfile(path, "print")
    return path
