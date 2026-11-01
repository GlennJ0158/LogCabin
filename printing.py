"""Printable cutting-plan report: HTML (cut list + panel drawing) opened in the browser's print dialog."""
import html
import os
import re
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


MANUAL_BOLD = re.compile(r"\*\*(.+?)\*\*")
RTF_SKIP = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "headerl", "headerr",
            "footerl", "footerr", "themedata", "colorschememapping", "latentstyles", "datastore", "generator",
            "pntext", "listtext"}
RTF_WORD = re.compile(r"([a-zA-Z]+)(-?\d+)? ?")
RTF_GROUP_START = re.compile(r"\\(\*|([a-zA-Z]+))")


def rtf_blocks(text):
    """Read the common RTF codes (paragraphs, bold, tabs, bullets, unicode, hex) into manual blocks.
    Italic and underline are not displayed. A paragraph whose text is all bold becomes a heading."""
    blocks, cells, bold, skip, stack = [], [], False, False, []

    def flush():
        while cells and cells[0][0].isspace():
            cells.pop(0)
        while cells and cells[-1][0].isspace():
            cells.pop()
        if not cells:
            return
        kind = "p"
        if cells[0][0] == "\u2022":
            kind = "li"
            cells.pop(0)
            while cells and cells[0][0].isspace():
                cells.pop(0)
        elif all(b for _, b in cells):
            kind = "h"
        runs = []
        for ch, b in cells:
            if runs and runs[-1][1] == b:
                runs[-1] = (runs[-1][0] + ch, b)
            else:
                runs.append((ch, b))
        blocks.append((kind, runs))
        cells.clear()

    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "{":
            stack.append((bold, skip))
            m = RTF_GROUP_START.match(text, i + 1)
            if m and (m.group(1) == "*" or m.group(2) in RTF_SKIP):
                skip = True
            i += 1
        elif c == "}":
            if stack:
                bold, skip = stack.pop()
            i += 1
        elif c == "\\":
            d = text[i + 1] if i + 1 < n else ""
            if d in ("\\", "{", "}"):
                if not skip:
                    cells.append((d, bold))
                i += 2
            elif d == "'":
                if not skip:
                    cells.append((bytes([int(text[i + 2:i + 4], 16)]).decode("cp1252", errors="replace"), bold))
                i += 4
            elif d == "~":
                if not skip:
                    cells.append((" ", bold))
                i += 2
            elif d.isalpha():
                m = RTF_WORD.match(text, i + 1)
                word, param = m.group(1), m.group(2)
                i = m.end()
                p = int(param) if param is not None else None
                if word in RTF_SKIP:
                    skip = True
                elif skip:
                    continue
                elif word == "par":
                    flush()
                elif word == "line":
                    cells.append((" ", bold))
                elif word == "tab":
                    cells.append(("\t", bold))
                elif word == "bullet":
                    cells.append(("\u2022", bold))
                elif word == "b":
                    bold = p != 0
                elif word == "plain":
                    bold = False
                elif word == "u" and p is not None:
                    cells.append((chr(p % 65536), bold))
                    if i < n and text[i] not in "\\{}":
                        i += 1   # skip the ASCII fallback character after \uN
            else:
                i += 2
        elif c in "\r\n":
            i += 1
        else:
            if not skip:
                cells.append((c, bold))
            i += 1
    flush()
    return blocks


def manual_blocks(body):
    """Split manual text into (kind, runs) blocks. kind: 'h' heading, 'li' bullet, 'p' paragraph.
    RTF text (starts with {\\rtf) is read with rtf_blocks(). Otherwise line markup:
    '## ' starts a heading, '- ' or '* ' a bullet, '**text**' is bold. Blank lines are skipped."""
    if str(body or "").lstrip().startswith("{\\rtf"):
        return rtf_blocks(str(body))
    blocks = []
    for raw in str(body or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            kind, line = "h", line[3:].strip()
        elif line[:2] in ("- ", "* "):
            kind, line = "li", line[2:].strip()
        else:
            kind = "p"
        runs, pos = [], 0
        for m in MANUAL_BOLD.finditer(line):
            if m.start() > pos:
                runs.append((line[pos:m.start()], False))
            runs.append((m.group(1), True))
            pos = m.end()
        if pos < len(line):
            runs.append((line[pos:], False))
        blocks.append((kind, runs or [("", False)]))
    return blocks


def render_manual_html(heading, body):
    parts = []
    for kind, runs in manual_blocks(body):
        inner = "".join(f"<b>{html.escape(t)}</b>" if b else html.escape(t) for t, b in runs)
        if kind == "h":
            parts.append(f"<h2>{inner}</h2>")
        elif kind == "li":
            parts.append(f"<li>{inner}</li>")
        else:
            parts.append(f"<p>{inner}</p>")
    # wrap consecutive <li> items in one <ul>
    body_html = re.sub(r"((?:<li>.*?</li>)+)", r"<ul>\1</ul>", "".join(parts))
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{html.escape(str(heading))}</title>
<style>body{{font-family:sans-serif;max-width:800px}}</style></head><body>
<div style="font-size:small;color:#666">{LABEL}</div>
<h1>{html.escape(str(heading))}</h1>{body_html}
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
