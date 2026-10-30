"""Printable cutting-plan report: HTML (cut list + panel drawing) opened in the browser's print dialog."""
import html
import os
import tempfile
import webbrowser


def render_plan_html(plan):
    s = min(460 / plan["width"], 360 / plan["length"])
    rects = []
    for p in plan["parts"]:
        x, y, w, h = 10 + p["x"] * s, 10 + p["y"] * s, p["w"] * s, p["h"] * s
        rects.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#cfe8ff" stroke="#000"/>'
                     f'<text x="{x + w / 2:.1f}" y="{y + h / 2:.1f}" text-anchor="middle">Fabric #{p["fabric_id"]}</text>')
    rows = "".join(
        f"<tr><td>{n}</td><td>#{c['fabric_id']}</td><td>{html.escape(str(c['name']))}</td>"
        f"<td>{c['cut_length']:g} x {c['cut_width']:g}</td><td>{'Yes' if c['rotated'] else 'No'}</td></tr>"
        for n, c in enumerate(plan["cuts"], 1))
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Cutting plan - {html.escape(str(plan['panel']))}</title>
<style>body{{font-family:sans-serif}}table{{border-collapse:collapse}}
td,th{{border:1px solid #888;padding:3px 8px}}</style></head><body>
<h1>{html.escape(str(plan['panel']))}</h1>
<p>Finished size {plan['length']:g} x {plan['width']:g}; seam allowance {plan['seam_allowance']:g};
{len(plan['parts'])} parts ({plan['rows']} x {plan['cols']}); seams: {plan['seams']}</p>
<table><tr><th>#</th><th>Fabric</th><th>Name</th><th>Cut size (L x W)</th><th>Rotated</th></tr>{rows}</table>
<svg width="{plan['width'] * s + 20:.0f}" height="{plan['length'] * s + 20:.0f}" style="margin-top:16px">{''.join(rects)}</svg>
<script>window.onload=function(){{window.print();}}</script></body></html>"""


def print_plan(plan):
    """Write the report to a temp file and open it (the page triggers the print dialog). Returns the path."""
    fd, path = tempfile.mkstemp(suffix=".html", prefix="quilt_plan_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(render_plan_html(plan))
    webbrowser.open("file://" + path.replace(os.sep, "/") if os.name != "nt" else path)
    return path
