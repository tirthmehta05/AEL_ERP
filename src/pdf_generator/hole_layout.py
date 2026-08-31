"""Geometry for the hole diagram drawn in each job card row.

Kept free of FPDF and of any service imports so the layout maths can be tested
on its own — pdf_service reaches the whole sales-order stack, which makes it
awkward to exercise directly.

Hole values are free-form strings entered on the Sales Order page ("Plain",
"Centre", "3-Hole", ...). Counted layouts are stored as "<n>-Hole", so adding a
new count is a data change rather than a code change: any "<n>-Hole" renders.
"""

import re
from typing import Optional

# Fractional span across the plate that counted holes are distributed over.
# Matches the original 5-Hole layout, which ran 0.15 -> 0.85.
HOLE_SPAN_START = 0.15
HOLE_SPAN_END = 0.85

# Layouts that predate custom counts, preserved exactly. 3-Hole was spaced
# i/(n+1) while 5-Hole ran edge to edge — two different rules, so no single
# formula reproduces both. Job cards get printed and filed, so both keep the
# appearance they have always had rather than being quietly redrawn.
LEGACY_HOLE_POSITIONS = {
    3: (0.25, 0.5, 0.75),
    5: (0.15, 0.325, 0.5, 0.675, 0.85),
}

# Largest count offered in the UI.
#
# The job card gives each hole diagram a 35mm x 10mm cell, which leaves a 31mm
# plate and a 21.7mm span to place holes along. Circles shrink as they crowd
# (see hole_radius), and that holds up to about 12: at 12 the circle is 1.58mm
# across against a scaled-down stroke, still legibly a ring. By 15 the diameter
# approaches the pen width and the hole floods in to a solid dot, so the
# diagram stops being countable. Past that the honest answer is a text label,
# not smaller circles.
MAX_HOLES = 12

DEFAULT_HOLE_RADIUS = 1.5
DEFAULT_STROKE_WIDTH = 0.5

# Fraction of the centre-to-centre gap a hole may occupy, so adjacent circles
# keep visible daylight between them once they start to crowd.
_MAX_RADIUS_AS_GAP_FRACTION = 0.4

# Stroke as a fraction of radius. Holds the default 0.5mm pen at the default
# 1.5mm radius, and thins it for smaller circles so they read as rings rather
# than filling in with ink.
_STROKE_AS_RADIUS_FRACTION = DEFAULT_STROKE_WIDTH / DEFAULT_HOLE_RADIUS

_COUNTED_HOLE_RE = re.compile(r"^(\d+)\s*-?\s*holes?$", re.IGNORECASE)


def parse_hole_count(hole_type: str) -> Optional[int]:
    """Return n for a counted layout like "4-Hole", or None for anything else.

    Tolerant of the shapes a user can type into the free-text Hole column on
    the update form — "4 Hole", "4-hole", "4holes" — since that field has never
    been restricted to the dropdown's values.
    """
    if not hole_type:
        return None

    match = _COUNTED_HOLE_RE.match(str(hole_type).strip())
    if not match:
        return None

    count = int(match.group(1))
    return count if count > 0 else None


def hole_positions(count: int) -> list:
    """Fractional x positions across the plate for `count` holes.

    A single hole sits centred; the rest spread evenly across the span. Legacy
    counts return their original hand-picked positions.
    """
    if count <= 0:
        return []
    if count == 1:
        return [0.5]
    if count in LEGACY_HOLE_POSITIONS:
        return list(LEGACY_HOLE_POSITIONS[count])

    step = (HOLE_SPAN_END - HOLE_SPAN_START) / (count - 1)
    return [HOLE_SPAN_START + i * step for i in range(count)]


def hole_radius(count: int, plate_width: float) -> float:
    """Radius to draw each hole at, shrunk so circles never run together.

    Stays at the default up to six holes on a standard job card; beyond that it
    scales with the gap rather than letting circles overlap.
    """
    if count <= 1:
        return DEFAULT_HOLE_RADIUS

    positions = hole_positions(count)
    smallest_gap = min(
        (b - a) * plate_width for a, b in zip(positions, positions[1:])
    )
    return min(DEFAULT_HOLE_RADIUS, smallest_gap * _MAX_RADIUS_AS_GAP_FRACTION)


def stroke_width(radius: float) -> float:
    """Pen width for a hole of the given radius.

    A fixed 0.5mm stroke on a 1mm circle is almost all ink, which is what turns
    a crowded diagram into a row of dots. Thinning the pen with the circle keeps
    the hole visible as a hole.
    """
    return min(DEFAULT_STROKE_WIDTH, radius * _STROKE_AS_RADIUS_FRACTION)
