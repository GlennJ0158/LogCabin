"""Log Cabin patterns: strips are sewn around a centre square, each strip spanning the full current side.

A pattern is a centre square plus an ordered list of strips (Side, Color, Width). Strip N is placed on
the growing square after strips 1..N-1. The block is square when every strip is placed.
All dimensions are in inches. Cut sizes add a seam allowance to every edge (finished + 2 x seam).
"""
from utilfuncs.validation import ValidationError, validate_choice, validate_number, validate_text

SIDES = ("Right", "Bottom", "Left", "Top")
COLORS = ("Light", "Dark")
VARIATIONS = ("Classic", "Reverse Classic", "Courthouse Steps", "Other")
DEFAULT_SEAM = 0.25
MAX_RINGS = 50
MAX_BLOCKS = 200


def ring_sides(variation, ring):
    """(Side, Color) pairs for one ring (1-based) of a generated variation."""
    if variation == "Classic":   # dark on the right and bottom, light on the left and top
        return [("Right", "Dark"), ("Bottom", "Dark"), ("Left", "Light"), ("Top", "Light")]
    if variation == "Reverse Classic":   # the Classic split turned to the other diagonal
        return [("Right", "Light"), ("Bottom", "Light"), ("Left", "Dark"), ("Top", "Dark")]
    if variation == "Courthouse Steps":   # opposite sides share a colour; the colours alternate by ring
        a, b = ("Light", "Dark") if ring % 2 else ("Dark", "Light")
        return [("Left", a), ("Right", a), ("Top", b), ("Bottom", b)]
    raise ValidationError("Variation", f"'{variation}' has no generated rings; enter the strips by hand")


def _positive(field, value):
    num = validate_number(field, value, minimum=0, decimals=4)
    if num <= 0:
        raise ValidationError(field, "must be greater than 0")
    return num


def _whole(field, value, minimum=1, maximum=None):
    num = validate_number(field, value, minimum=minimum, maximum=maximum)
    if num != int(num):
        raise ValidationError(field, f"'{value}' must be a whole number")
    return int(num)


def generate_strips(variation, width, rings):
    """Strip rows (Side, Color, Width) for the given number of rings of a variation (4 strips per ring)."""
    width = _positive("Strip width", width)
    rings = _whole("Rings", rings, maximum=MAX_RINGS)
    strips = []
    for ring in range(1, rings + 1):
        strips += [{"Side": s, "Color": c, "Width": width} for s, c in ring_sides(variation, ring)]
    return strips


def clean_strip(row, sides=SIDES, colors=COLORS, label="Strip"):
    """Validate one strip row; errors name the strip and the field."""
    return {"Side": validate_choice(f"{label} Side", row.get("Side"), sides),
            "Color": validate_choice(f"{label} Color", row.get("Color"), colors),
            "Width": _positive(f"{label} Width", row.get("Width"))}


def place(centre, strips):
    """Place strips in order around the centre square (origin at its top-left corner).

    Returns (placed, block_width, block_height); each placed strip gets its finished Length (inches).
    """
    left = top = 0.0
    right = bottom = float(centre)
    placed = []
    for no, s in enumerate(strips, start=1):
        w = s["Width"]
        height, span = bottom - top, right - left
        if s["Side"] == "Right":
            length, right = height, right + w
        elif s["Side"] == "Left":
            length, left = height, left - w
        elif s["Side"] == "Top":
            length, top = span, top - w
        else:
            length, bottom = span, bottom + w
        placed.append({"StripNo": no, "Side": s["Side"], "Color": s["Color"], "Width": w,
                       "Length": round(length, 4)})
    return placed, round(right - left, 4), round(bottom - top, 4)


def validate(header, strips, variations=VARIATIONS, sides=SIDES, colors=COLORS):
    """Clean a pattern. Returns (header, strips); raises ValidationError naming the field at fault.

    The strips must close a square block, so a pattern that does not is rejected.
    """
    h = {
        "PatternName": validate_text("PatternName", header.get("PatternName"), max_len=100),
        "Variation": validate_choice("Variation", header.get("Variation"), variations),
        "CentreSize": _positive("CentreSize", header.get("CentreSize")),
        "CentreColor": validate_text("CentreColor", header.get("CentreColor"), max_len=50, required=False),
        "SeamAllowance": validate_number("SeamAllowance", header.get("SeamAllowance"), minimum=0,
                                         maximum=1, decimals=4),
    }
    if not strips:
        raise ValidationError("Strips", "a pattern needs at least one strip")
    clean = [clean_strip(s, sides, colors, label=f"Strip {n}") for n, s in enumerate(strips, start=1)]
    _, bw, bh = place(h["CentreSize"], clean)
    if abs(bw - bh) > 1e-6:
        raise ValidationError("Strips", f"the strips make a {bw} x {bh} in block, not a square; "
                                        "change the strips so the block closes")
    return h, clean


def cut_list(header, strips):
    """Finished and cut sizes (inches) for the centre square and every strip, plus the block size."""
    seam = header["SeamAllowance"]
    placed, bw, bh = place(header["CentreSize"], strips)
    return {
        "block": bw,
        "centre_cut": round(header["CentreSize"] + 2 * seam, 4),
        "strips": [dict(p, CutWidth=round(p["Width"] + 2 * seam, 4), CutLength=round(p["Length"] + 2 * seam, 4))
                   for p in placed],
    }


def quilt(plan, across, down):
    """Quilt size, block count and cut totals for a grid of identical blocks (no sashing)."""
    across = _whole("Blocks across", across, maximum=MAX_BLOCKS)
    down = _whole("Blocks down", down, maximum=MAX_BLOCKS)
    blocks = across * down
    inches = {}
    for s in plan["strips"]:
        inches[s["Color"]] = round(inches.get(s["Color"], 0) + s["CutLength"] * blocks, 4)
    return {
        "across": across, "down": down, "blocks": blocks,
        "width": round(plan["block"] * across, 4), "height": round(plan["block"] * down, 4),
        "centre_squares": blocks, "centre_cut": plan["centre_cut"],
        "strip_inches": inches,
    }
