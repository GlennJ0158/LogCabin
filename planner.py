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


def _prepare(panel, fabrics, max_parts):
    if max_parts is None:
        max_parts = panel.get("MAXPARTS", 4)
    max_parts = int(max_parts)
    if max_parts < 1:
        raise ValueError("Maximum parts must be at least 1")
    return max_parts, [f for f in fabrics if f["USE"]]


def plan_panel(panel, fabrics, max_parts=None):
    """panel: dict(PANELNAME, SEAMALLOWANCE, LENGTH, WIDTH[, MAXPARTS]). fabrics: FABRIC rows.
    Builds the panel from equal cells in a rows x cols grid with at most max_parts cells (default 4),
    preferring the fewest seams. A fabric may supply several cells. Falls back to variable-width strips.
    Raises ValueError if impossible."""
    max_parts, avail = _prepare(panel, fabrics, max_parts)
    grid = _plan_grid(panel, avail, max_parts)
    if grid is not None:
        return grid
    strip = _plan_strips(panel, avail, max_parts)
    if strip is not None:
        return strip
    raise ValueError(f"Cannot build panel with {max_parts} or fewer parts from available inventory")


def plan_cases(panel, fabrics, max_parts=None):
    """Both layouts for the same panel: {"symmetric": plan or None, "variable": plan or None}."""
    max_parts, avail = _prepare(panel, fabrics, max_parts)
    return {"symmetric": _plan_grid(panel, avail, max_parts),
            "variable": _plan_strips(panel, avail, max_parts)}


def _plan_grid(panel, avail, max_parts):
    """Equal-cell (symmetric) layout, or None if no grid fits."""
    sa = panel["SEAMALLOWANCE"]
    pl, pw = panel["LENGTH"], panel["WIDTH"]
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
        return None
    _, rows, cols, picks, cl, cw, nl, nw = best
    parts, cuts, i = [], [], 0
    for f, rot, take, consumed in picks:
        for n in range(take):
            r, c = divmod(i, cols)
            i += 1
            parts.append({"row": r, "col": c, "x": c * cw, "y": r * cl, "w": cw, "h": cl, "fabric_id": f["ID"],
                          "name": f["NAME"], "grain": grain_direction(f["GRAIN"], rot)})
            cuts.append({"fabric_id": f["ID"], "name": f["NAME"], "cut_length": nl if not rot else nw,
                         "cut_width": nw if not rot else nl,
                         "finished_length": cl, "finished_width": cw,
                         "consumed_length": consumed if n == 0 else 0,   # fabric's total, charged once
                         "rotated": rot})
    return {"panel": panel["PANELNAME"], "length": pl, "width": pw, "seam_allowance": sa, "mode": "grid",
            "rows": rows, "cols": cols, "seams": (rows - 1) + (cols - 1), "parts": parts, "cuts": cuts}


STRIP_NODE_LIMIT = 20000


def _plan_strips(panel, avail, max_parts):
    """Fallback when no equal-cell grid fits: horizontal bands of pieces with variable widths.
    Each band has one cut height; pieces in it sum to the panel width. Pieces are cut from fabric
    rectangles (guillotine splits), in either orientation. Returns a plan or None."""
    sa = panel["SEAMALLOWANCE"]
    pl, pw = panel["LENGTH"], panel["WIDTH"]
    free0 = [(f["ID"], 0.0, 0.0, float(f["LENGTH"]), float(f["WIDTH"])) for f in avail]
    fabrics = {f["ID"]: f for f in avail}
    budget = [STRIP_NODE_LIMIT]

    def fill_band(free, ph, width_left):
        """Fill one band of cut height ph across width_left (finished). Returns (pieces, free) or None."""
        free = list(free)
        pieces, left = [], width_left
        while left > EPS:
            best = None
            for idx, (fid, a0, b0, A, B) in enumerate(free):
                for rot in (False, True):
                    # panel height runs along the fabric length unless rotated; panel width runs across it
                    span_y, span_x = (A, B) if not rot else (B, A)
                    if span_y + EPS < ph:
                        continue
                    pwc = min(span_x, left + 2 * sa)
                    if pwc - 2 * sa <= EPS:
                        continue
                    key = (round(pwc, 6), -(A * B))
                    if best is None or key > best[0]:
                        best = (key, idx, rot, pwc)
            if best is None:
                return None
            _, idx, rot, pwc = best
            fid, a0, b0, A, B = free.pop(idx)
            eA, eB = (ph, pwc) if not rot else (pwc, ph)
            if A - eA > EPS:
                free.append((fid, a0 + eA, b0, A - eA, B))
            if B - eB > EPS:
                free.append((fid, a0, b0 + eB, eA, B - eB))
            pieces.append({"fid": fid, "a0": a0, "eA": eA, "eB": eB, "rot": rot,
                           "fin_w": pwc - 2 * sa, "fin_h": ph - 2 * sa})
            left -= pwc - 2 * sa
        return pieces, free

    def search(free, hl, used, bands):
        if hl <= EPS:
            return bands
        budget[0] -= 1
        if budget[0] < 0:
            return None
        cands = {round(v, 6) for (_, _, _, A, B) in free for v in (A, B)}
        cands.add(round(hl + 2 * sa, 6))
        options = []
        for ph in cands:
            if ph - 2 * sa <= EPS or ph > hl + 2 * sa + EPS:
                continue
            res = fill_band(free, ph, pw)
            if res is None:
                continue
            pieces, nfree = res
            if used + len(pieces) > max_parts:
                continue
            options.append((len(pieces), -ph, pieces, nfree, ph))
        options.sort(key=lambda o: (o[0], o[1]))
        for _, _, pieces, nfree, ph in options:
            found = search(nfree, hl - (ph - 2 * sa), used + len(pieces), bands + [(ph, pieces)])
            if found is not None:
                return found
        return None

    bands = search(free0, pl, 0, [])
    if bands is None:
        return None

    parts, cuts, charged = [], [], set()
    x_end_len = {}
    for _, pieces in bands:
        for p in pieces:
            x_end_len[p["fid"]] = max(x_end_len.get(p["fid"], 0.0), p["a0"] + p["eA"])
    y = 0.0
    for r, (ph, pieces) in enumerate(bands):
        x = 0.0
        for c, p in enumerate(pieces):
            f = fabrics[p["fid"]]
            parts.append({"row": r, "col": c, "x": x, "y": y, "w": p["fin_w"], "h": p["fin_h"],
                          "fabric_id": f["ID"], "name": f["NAME"],
                          "grain": grain_direction(f["GRAIN"], p["rot"])})
            cut = {"fabric_id": f["ID"], "name": f["NAME"], "cut_length": p["eA"], "cut_width": p["eB"],
                   "finished_length": p["fin_h"], "finished_width": p["fin_w"],
                   "consumed_length": 0, "rotated": p["rot"]}
            if p["fid"] not in charged:
                cut["consumed_length"] = round(x_end_len[p["fid"]], 4)   # fabric's total, charged once
                charged.add(p["fid"])
            cuts.append(cut)
            x += p["fin_w"]
        y += ph - 2 * sa
    seams = sum(len(p) - 1 for _, p in bands) + (len(bands) - 1)
    return {"panel": panel["PANELNAME"], "length": pl, "width": pw, "seam_allowance": sa, "mode": "strip",
            "rows": len(bands), "cols": max(len(p) for _, p in bands), "seams": seams,
            "parts": parts, "cuts": cuts}


def grain_direction(grain, rotated):
    """'h' (right to left), 'v' (up and down), 'b' (bias) or 'n' (None/blank/unrecognized).
    Lengthwise grain runs along the fabric length, which is vertical on the panel unless the cut is rotated."""
    g = (grain or "").strip().lower()
    if g == "bias":
        return "b"
    if g not in ("lengthwise", "crosswise"):
        return "n"
    vertical = (g == "lengthwise") != bool(rotated)
    return "v" if vertical else "h"


GRAIN_MARK = {"h": "==>", "v": "^|", "b": "^\\", "n": "<N>"}


GRAIN_MEANING = {"h": "Grain runs right to left", "v": "Grain runs up and down",
                 "b": "Bias grain (diagonal)", "n": "No grain specified"}


def part_label(part):
    """Sketch label: grain indicator, fabric name and ID."""
    mark = GRAIN_MARK[part.get("grain") or "n"]
    return f"{mark} {part.get('name', '')} (#{part['fabric_id']})".strip()


def cut_list(plan):
    lines = []
    for n, c in enumerate(plan["cuts"], 1):
        lines.append(f"{n}. Fabric #{c['fabric_id']} ({c['name']}): cut {c['cut_length']:g} x {c['cut_width']:g}"
                     f" (finished {c['finished_length']:g} x {c['finished_width']:g})"
                     f" Revolved {'Yes' if c['rotated'] else 'NO'}")
    return "\n".join(lines)
