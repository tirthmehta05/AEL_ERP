"""Tests for the job card hole diagram geometry.

These live apart from test_pdf_service.py on purpose: pdf_service imports the
sales-order stack (and msal through it), so it cannot be imported in a bare
test environment. hole_layout deliberately has no such dependencies.
"""

import pytest

from src.pdf_generator import hole_layout

# The cell the job card gives each diagram: 35mm wide, 2mm padding each side.
JOB_CARD_PLATE_WIDTH = 31.0


@pytest.mark.parametrize("value,expected", [
    ("3-Hole", 3),
    ("4-Hole", 4),
    ("5-Hole", 5),
    ("12-Hole", 12),
    # the update form's Hole column is free text, so be forgiving
    ("4-hole", 4),
    ("4 Hole", 4),
    ("4holes", 4),
    ("  6-Hole  ", 6),
])
def test_parse_hole_count_reads_counted_layouts(value, expected):
    assert hole_layout.parse_hole_count(value) == expected


@pytest.mark.parametrize("value", [
    "Plain", "Centre", "Both Side", "Side", "Daimond", "V-Noch",
    "Ready Entry", "", None,
    "0-Hole",        # a zero count is not a layout
    "Hole",          # no number
    "3-Hole-Punch",  # trailing junk is not a count
])
def test_parse_hole_count_ignores_everything_else(value):
    assert hole_layout.parse_hole_count(value) is None


def test_legacy_layouts_are_unchanged():
    """3-Hole and 5-Hole must draw exactly as they always have.

    Job cards are printed and filed, so a general spacing rule must not quietly
    redraw designs that already exist on paper.
    """
    assert hole_layout.hole_positions(3) == [0.25, 0.5, 0.75]
    assert hole_layout.hole_positions(5) == [0.15, 0.325, 0.5, 0.675, 0.85]


def test_single_hole_is_centred():
    assert hole_layout.hole_positions(1) == [0.5]


def test_no_positions_for_a_zero_count():
    assert hole_layout.hole_positions(0) == []


def test_four_holes_spread_evenly_across_the_span():
    positions = hole_layout.hole_positions(4)

    assert len(positions) == 4
    assert positions[0] == pytest.approx(hole_layout.HOLE_SPAN_START)
    assert positions[-1] == pytest.approx(hole_layout.HOLE_SPAN_END)

    gaps = [b - a for a, b in zip(positions, positions[1:])]
    assert all(g == pytest.approx(gaps[0]) for g in gaps)


@pytest.mark.parametrize("count", range(2, hole_layout.MAX_HOLES + 1))
def test_positions_stay_inside_the_plate_and_in_order(count):
    positions = hole_layout.hole_positions(count)

    assert len(positions) == count
    assert positions == sorted(positions)
    assert positions[0] >= hole_layout.HOLE_SPAN_START
    assert positions[-1] <= hole_layout.HOLE_SPAN_END


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6])
def test_small_counts_keep_the_full_size_hole(count):
    """Up to six holes there is room to spare, so nothing should shrink."""
    radius = hole_layout.hole_radius(count, JOB_CARD_PLATE_WIDTH)
    assert radius == hole_layout.DEFAULT_HOLE_RADIUS


@pytest.mark.parametrize("count", range(2, hole_layout.MAX_HOLES + 1))
def test_holes_never_overlap_at_the_job_card_width(count):
    """The whole point of shrinking: circles must keep daylight between them."""
    positions = hole_layout.hole_positions(count)
    radius = hole_layout.hole_radius(count, JOB_CARD_PLATE_WIDTH)

    smallest_gap = min(
        (b - a) * JOB_CARD_PLATE_WIDTH for a, b in zip(positions, positions[1:])
    )
    assert smallest_gap > radius * 2


@pytest.mark.parametrize("count", range(2, hole_layout.MAX_HOLES + 1))
def test_every_supported_count_stays_visible_on_paper(count):
    """A hole must stay a ring, not flood into a solid dot.

    This is the constraint that sets MAX_HOLES: the circle has to stay wide
    enough that the pen drawing it leaves a gap in the middle.
    """
    radius = hole_layout.hole_radius(count, JOB_CARD_PLATE_WIDTH)
    stroke = hole_layout.stroke_width(radius)

    assert radius * 2 > stroke * 2, f"{count} holes: circle is all ink"


def test_stroke_thins_with_the_circle():
    full = hole_layout.stroke_width(hole_layout.DEFAULT_HOLE_RADIUS)
    crowded = hole_layout.stroke_width(
        hole_layout.hole_radius(hole_layout.MAX_HOLES, JOB_CARD_PLATE_WIDTH)
    )

    assert full == hole_layout.DEFAULT_STROKE_WIDTH
    assert crowded < full
