"""Line-art pictures for the job card's quality checklist.

The floor staff who fill the checklist may not read the labels, so each check
gets a small picture and each lot box gets a tick and a cross to circle.
Defect checks ("No bend", "Free of rust") show the defect under a prohibition
sign; the rest show what should be there. Everything is drawn with plain FPDF
lines and shapes, like the hole diagrams, so it prints cleanly in black and white.

Kept free of service imports so it can be tested on its own, like hole_layout.
"""

import math

STROKE = 0.35
BOLD = 0.7


class _Canvas:
    """Draws inside a size x size square at (x, y), using 0..1 coordinates."""

    def __init__(self, pdf, x, y, size):
        self.pdf, self.x, self.y, self.size = pdf, x, y, size

    def _point(self, u, v):
        return (self.x + u * self.size, self.y + v * self.size)

    def stroke(self, width):
        self.pdf.set_line_width(width)

    def line(self, u1, v1, u2, v2):
        self.pdf.line(*self._point(u1, v1), *self._point(u2, v2))

    def rect(self, u1, v1, u2, v2, style="D"):
        x, y = self._point(u1, v1)
        self.pdf.rect(x, y, (u2 - u1) * self.size, (v2 - v1) * self.size, style)

    def circle(self, cu, cv, r, style="D"):
        x, y = self._point(cu - r, cv - r)
        self.pdf.ellipse(x, y, 2 * r * self.size, 2 * r * self.size, style)

    def path(self, *points, closed=False, style="D"):
        coordinates = [self._point(u, v) for u, v in points]
        if closed:
            self.pdf.polygon(coordinates, style=style)
        else:
            self.pdf.polyline(coordinates, style=style)


def _prohibited(c):
    """Circle with a slash: 'this must not be there'."""
    c.stroke(BOLD)
    c.circle(0.5, 0.5, 0.47)
    d = 0.47 / math.sqrt(2)
    c.line(0.5 - d, 0.5 - d, 0.5 + d, 0.5 + d)


def _arrow_heads(c, u1, v1, u2, v2, head=0.1):
    """Double-headed dimension arrow from (u1, v1) to (u2, v2), horizontal or vertical."""
    c.line(u1, v1, u2, v2)
    if v1 == v2:
        c.line(u1, v1, u1 + head, v1 - head)
        c.line(u1, v1, u1 + head, v1 + head)
        c.line(u2, v2, u2 - head, v2 - head)
        c.line(u2, v2, u2 - head, v2 + head)
    else:
        c.line(u1, v1, u1 - head, v1 + head)
        c.line(u1, v1, u1 + head, v1 + head)
        c.line(u2, v2, u2 - head, v2 - head)
        c.line(u2, v2, u2 + head, v2 - head)


def _coil(c):  # Material grade & thickness as per job card
    for r in (0.42, 0.29, 0.14):
        c.circle(0.5, 0.5, r)


def _oil_drop(c):  # Anti-rust applied
    c.path((0.5, 0.05), (0.33, 0.38), (0.67, 0.38), closed=True, style="F")
    c.circle(0.5, 0.42, 0.18, style="F")
    c.rect(0.05, 0.72, 0.95, 0.9)


def _rust(c):  # Free of rust
    c.rect(0.12, 0.36, 0.88, 0.64)
    for u, v in ((0.3, 0.46), (0.52, 0.55), (0.7, 0.45)):
        c.circle(u, v, 0.055, style="F")
    _prohibited(c)


def _cut_size(c):  # Cut size as per drawing
    c.rect(0.05, 0.55, 0.95, 0.85)
    c.line(0.05, 0.12, 0.05, 0.48)
    c.line(0.95, 0.12, 0.95, 0.48)
    _arrow_heads(c, 0.08, 0.3, 0.92, 0.3)


def _holes(c):  # Hole size & position as per drawing
    c.rect(0.05, 0.28, 0.95, 0.72)
    for u in (0.25, 0.5, 0.75):
        c.circle(u, 0.5, 0.09)


def _stack(c):  # Stack size as per drawing
    for v in (0.12, 0.32, 0.52, 0.72):
        c.rect(0.05, v, 0.66, v + 0.14)
    _arrow_heads(c, 0.84, 0.12, 0.84, 0.86)


def _burr(c):  # No burr at edges & holes
    teeth = 5
    step = 0.72 / teeth
    points = [(0.14, 0.66), (0.14, 0.48)]
    for i in range(teeth):
        points += [(0.14 + step * (i + 0.5), 0.3), (0.14 + step * (i + 1), 0.48)]
    points.append((0.86, 0.66))
    c.path(*points, closed=True)
    _prohibited(c)


def _bend(c):  # No bend
    c.stroke(BOLD)
    c.path((0.14, 0.66), (0.52, 0.66), (0.82, 0.3))
    _prohibited(c)


def _dent(c):  # No dent
    c.path((0.14, 0.66), (0.14, 0.38), (0.4, 0.38), (0.5, 0.55), (0.6, 0.38), (0.86, 0.38), (0.86, 0.66), closed=True)
    _prohibited(c)


def _wave(c):  # No waviness
    c.stroke(BOLD)
    steps = 24
    c.path(*[(0.12 + 0.76 * i / steps, 0.5 - 0.13 * math.sin(4 * math.pi * i / steps)) for i in range(steps + 1)])
    _prohibited(c)


def _bundle(c):  # No. of bundles as per drawing
    for v in (0.2, 0.4, 0.6):
        c.rect(0.08, v, 0.92, v + 0.18)
    c.stroke(BOLD)
    for u in (0.3, 0.7):
        c.line(u, 0.12, u, 0.86)


def _box(c):  # Packaging as per customer requirement
    c.path((0.1, 0.38), (0.7, 0.38), (0.7, 0.9), (0.1, 0.9), closed=True)
    c.path((0.1, 0.38), (0.3, 0.16), (0.9, 0.16), (0.7, 0.38), closed=True)
    c.path((0.7, 0.38), (0.9, 0.16), (0.9, 0.68), (0.7, 0.9), closed=True)
    c.stroke(BOLD)
    c.line(0.4, 0.38, 0.6, 0.16)


def _core_gap(c):  # No gaps in core
    c.stroke(BOLD)
    # Outer frame with a break in its top edge: the gap.
    c.path((0.45, 0.2), (0.2, 0.2), (0.2, 0.8), (0.8, 0.8), (0.8, 0.2), (0.59, 0.2))
    c.rect(0.38, 0.38, 0.62, 0.62)
    _prohibited(c)


# Keyed by the check keys in src/quality/fg_qc.py.
_ICONS = {
    "material_as_per_jc": _coil,
    "anti_rust_applied": _oil_drop,
    "free_of_rust": _rust,
    "cut_size_ok": _cut_size,
    "hole_size_ok": _holes,
    "stack_size_ok": _stack,
    "no_burr": _burr,
    "no_bend": _bend,
    "no_dent": _dent,
    "no_waviness": _wave,
    "bundles_ok": _bundle,
    "packaging_ok": _box,
    "no_core_gaps": _core_gap,
}
ICON_KEYS = frozenset(_ICONS)


def draw_check_icon(pdf, key, x, y, size):
    """Draws the picture for a checklist item in a size x size square; unknown checks stay blank."""
    icon = _ICONS.get(key)
    if icon is None:
        return
    with pdf.local_context(line_width=STROKE, draw_color=0, fill_color=0):
        icon(_Canvas(pdf, x, y, size))


def draw_tick(pdf, x, y, size):
    with pdf.local_context(line_width=BOLD, draw_color=0):
        _Canvas(pdf, x, y, size).path((0.1, 0.55), (0.38, 0.85), (0.9, 0.15))


def draw_cross(pdf, x, y, size):
    with pdf.local_context(line_width=BOLD, draw_color=0):
        c = _Canvas(pdf, x, y, size)
        c.line(0.15, 0.15, 0.85, 0.85)
        c.line(0.85, 0.15, 0.15, 0.85)


def draw_dash(pdf, x, y, size):
    """'Not applicable' mark, for the hole check on plain strips."""
    with pdf.local_context(line_width=BOLD, draw_color=0):
        _Canvas(pdf, x, y, size).line(0.15, 0.5, 0.85, 0.5)
