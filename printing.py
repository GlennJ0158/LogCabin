"""Printable cutting-plan report: HTML (cut list + panel drawing) opened in the browser's print dialog."""
import html
import os
import tempfile
import webbrowser

from version import LABEL
from planner import GRAIN_MARK, GRAIN_MEANING, part_label


def render_plan_html(plan):
    s = min(460 / plan["width"], 360 / plan["length"])
    rects = []
    for p in plan["parts"]:
        x, y, w, h = 10 + p["x"] * s, 10 + p["y"] * s, p["w"] * s, p["h"] * s
        rects.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#cfe8ff" stroke="#000"/>'
                     f'<text x="{x + w / 2:.1f}" y="{y + h / 2:.1f}" text-anchor="middle">{html.escape(part_label(p))}</text>')
    rows = "".join(
        f"<tr><td>{n}</td><td>#{c['fabric_id']}</td><td>{html.escape(str(c['name']))}</td>"
        f"<td>{c['cut_length']:g} x {c['cut_width']:g}</td><td>{'Yes' if c['rotated'] else 'No'}</td></tr>"
        for n, c in enumerate(plan["cuts"], 1))
    used = [k for k in GRAIN_MARK if any((p.get("grain") or "n") == k for p in plan["parts"])]
    legend = "".join(f"<tr><td><b>{html.escape(GRAIN_MARK[k])}</b></td><td>{GRAIN_MEANING[k]}</td></tr>"
                     for k in used)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Cutting plan - {html.escape(str(plan['panel']))}</title>
<style>body{{font-family:sans-serif}}table{{border-collapse:collapse}}
td,th{{border:1px solid #888;padding:3px 8px}}</style></head><body>
<div style="font-size:small;color:#666">{LABEL}</div>
<h1>{html.escape(str(plan['panel']))}</h1>
<p>Finished size {plan['length']:g} x {plan['width']:g}; seam allowance {plan['seam_allowance']:g};
{len(plan['parts'])} parts ({plan['rows']} x {plan['cols']}); seams: {plan['seams']}</p>
<table><tr><th>#</th><th>Fabric</th><th>Name</th><th>Cut size (L x W)</th><th>Rotated</th></tr>{rows}</table>
<svg width="{plan['width'] * s + 20:.0f}" height="{plan['length'] * s + 20:.0f}" style="margin-top:16px">{''.join(rects)}</svg>
<h3>Legend</h3><table>{legend}</table>
<script>window.onload=function(){{window.print();}}</script></body></html>"""


def render_manual_html(heading, body):
    paragraphs = "".join(f"<p>{html.escape(line)}</p>" for line in str(body or "").splitlines() if line.strip())
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{html.escape(str(heading))}</title>
<style>body{{font-family:sans-serif;max-width:800px}}</style></head><body>
<div style="font-size:small;color:#666">{LABEL}</div>
<h1>{html.escape(str(heading))}</h1>{paragraphs}
<script>window.onload=function(){{window.print();}}</script></body></html>"""


def open_for_print(page):
    """Write the HTML page to a temp file and open it (the page triggers the print dialog). Returns the path."""
    fd, path = tempfile.mkstemp(suffix=".html", prefix="quilt_print_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(page)
    webbrowser.open("file://" + path.replace(os.sep, "/") if os.name != "nt" else path)
    return path


def print_plan(plan):
    return open_for_print(render_plan_html(plan))
