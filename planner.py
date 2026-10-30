"""Panel planner: builds a rectangle from equal cells (symmetric) using the fewest seams."""
from itertools import product


EPS = 1e-9


def _layout(fab, cw, ch):
    """Best way to cut cells of ch x cw (cut size) from one fabric.
    Returns (rotated, per_row, cell_rows, strip) or None. A strip is cut across the full width of the fabric,
    so consumed length = number of strip rows * strip length."""
    opts = []
    for rot, along, across in ((False, ch, cw), (True, cw, ch)):
        per_row = int((fab["WIDTH"] + EPS) // across)
        n_rows = int((fab["LENGTH"] + EPS) // along)
        if per_row and n_rows:
            opts.append((rot, per_row, n_rows, along))
    return max(opts, key=lambda o: o[1] * o[2]) if opts else None


def _assign(avail, need_l, need_w, count):
    """Cover `count` cells using the fewest/smallest fabrics. Each fabric may supply several cells.
    Returns [(fabric, rotated, cells, consumed_length)] or None."""
    cands = []
    for f in avail:
        lay = _layout(f, need_w, need_l)
        if lay:
            cands.append((f, lay))
    # fewest fabrics first (largest capacity), then least material
    cands.sort(key=lambda c: (-(c[1][1] * c[1][2]), c[0]["LENGTH"] * c[0]["WIDTH"]))
    picks, left = [], count
    for f, (rot, per_row, n_rows, along) in cands:
        if left <= 0:
            break
        take = min(left, per_row * n_rows)
        picks.append((f, rot, take, -(-take // per_row) * along))
        left -= take
    return picks if left <= 0 else None


def plan_panel(panel, fabrics, max_parts=None):
    """panel: dict(PANELNAME, SEAMALLOWANCE, LENGTH, WIDTH[, MAXPARTS]). fabrics: FABRIC rows.
    Builds the panel from equal cells in a rows x cols grid with at most max_parts cells (default 4),
    preferring the fewest seams. A fabric may supply several cells. Raises ValueError if impossible."""
    if max_parts is None:
        max_parts = panel.get("MAXPARTS", 4)
    max_parts = int(max_parts)
    if max_parts < 1:
        raise ValueError("Maximum parts must be at least 1")
    sa = panel["SEAMALLOWANCE"]
    pl, pw = panel["LENGTH"], panel["WIDTH"]
    avail = [f for f in fabrics if f["USE"]]
    best = None
    for rows in range(1, max_parts + 1):
        for cols in range(1, max_parts // rows + 1):
            cl, cw = pl / rows, pw / cols
            # symmetric: cut size = cell + seam allowance both sides (working dim = dim - 2*SA)
            need_l, need_w = cl + 2 * sa, cw + 2 * sa
            picks = _assign(avail, need_l, need_w, rows * cols)
            if picks is None:
                continue
            key = ((rows - 1) + (cols - 1), len(picks), sum(p[3] * p[0]["WIDTH"] for p in picks))
            if best is None or key < best[0]:
                best = (key, rows, cols, picks, cl, cw, need_l, need_w)
    if best is None:
        raise ValueError(f"Cannot build panel with {max_parts} or fewer parts from available inventory")
    _, rows, cols, picks, cl, cw, nl, nw = best
    parts, cuts, i = [], [], 0
    for f, rot, take, consumed in picks:
        for n in range(take):
            r, c = divmod(i, cols)
            i += 1
            parts.append({"row": r, "col": c, "x": c * cw, "y": r * cl, "w": cw, "h": cl, "fabric_id": f["ID"]})
            cuts.append({"fabric_id": f["ID"], "name": f["NAME"], "cut_length": nl if not rot else nw,
                         "cut_width": nw if not rot else nl,
                         "consumed_length": consumed if n == 0 else 0,   # fabric's total, charged once
                         "rotated": rot})
    return {"panel": panel["PANELNAME"], "length": pl, "width": pw, "seam_allowance": sa,
            "rows": rows, "cols": cols, "seams": (rows - 1) + (cols - 1), "parts": parts, "cuts": cuts}


def cut_list(plan):
    lines = []
    for n, c in enumerate(plan["cuts"], 1):
        lines.append(f"{n}. Fabric #{c['fabric_id']} ({c['name']}): cut {c['cut_length']:g} x {c['cut_width']:g}"
                     f" (finished {plan['length'] / plan['rows']:g} x {plan['width'] / plan['cols']:g})")
    return "\n".join(lines)
