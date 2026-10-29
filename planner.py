"""Panel planner: builds a rectangle from equal cells (symmetric) using the fewest seams."""
from itertools import product


def _fits(fab, cw, ch):
    """Return (orientation_rotated, consumed_length) if a cut ch x cw (cut size) fits fabric; else None.
    A strip is cut across the full width of the fabric, so consumed length = the piece's length along it."""
    opts = []
    if fab["LENGTH"] >= ch and fab["WIDTH"] >= cw:
        opts.append((False, ch))
    if fab["LENGTH"] >= cw and fab["WIDTH"] >= ch:
        opts.append((True, cw))
    return min(opts, key=lambda o: o[1]) if opts else None


def plan_panel(panel, fabrics, max_div=4):
    """panel: dict(PANELNAME, SEAMALLOWANCE, LENGTH, WIDTH). fabrics: FABRIC rows.
    Returns plan dict or raises ValueError. Each fabric supplies at most one cell."""
    sa = panel["SEAMALLOWANCE"]
    pl, pw = panel["LENGTH"], panel["WIDTH"]
    avail = [f for f in fabrics if f["USE"]]
    best = None
    for rows, cols in product(range(1, max_div + 1), repeat=2):
        if rows * cols > len(avail):
            continue
        cl, cw = pl / rows, pw / cols
        # symmetric: cut size = cell + seam allowance both sides (working dim = dim - 2*SA)
        need_l, need_w = cl + 2 * sa, cw + 2 * sa
        # greedy: tightest fit first, mirrored cells share the same pick order
        pool = sorted(avail, key=lambda f: f["LENGTH"] * f["WIDTH"])
        picks, ok = [], True
        for _ in range(rows * cols):
            for f in pool:
                fit = _fits(f, need_w, need_l)
                if fit:
                    picks.append((f, fit))
                    pool.remove(f)
                    break
            else:
                ok = False
                break
        if not ok:
            continue
        seams = (rows - 1) + (cols - 1)
        waste = sum(f["LENGTH"] * f["WIDTH"] for f, _ in picks)
        key = (seams, waste)
        if best is None or key < best[0]:
            best = (key, rows, cols, picks, cl, cw, need_l, need_w)
    if best is None:
        raise ValueError("Cannot build panel from available inventory")
    _, rows, cols, picks, cl, cw, nl, nw = best
    parts, cuts = [], []
    for i, (f, (rot, consumed)) in enumerate(picks):
        r, c = divmod(i, cols)
        parts.append({"row": r, "col": c, "x": c * cw, "y": r * cl, "w": cw, "h": cl, "fabric_id": f["ID"]})
        cuts.append({"fabric_id": f["ID"], "name": f["NAME"], "cut_length": nl if not rot else nw,
                     "cut_width": nw if not rot else nl, "consumed_length": consumed, "rotated": rot})
    return {"panel": panel["PANELNAME"], "length": pl, "width": pw, "seam_allowance": sa,
            "rows": rows, "cols": cols, "seams": (rows - 1) + (cols - 1), "parts": parts, "cuts": cuts}


def cut_list(plan):
    lines = []
    for n, c in enumerate(plan["cuts"], 1):
        lines.append(f"{n}. Fabric #{c['fabric_id']} ({c['name']}): cut {c['cut_length']:g} x {c['cut_width']:g}"
                     f" (finished {plan['length'] / plan['rows']:g} x {plan['width'] / plan['cols']:g})")
    return "\n".join(lines)
