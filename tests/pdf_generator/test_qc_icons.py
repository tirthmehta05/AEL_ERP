from unittest.mock import MagicMock

import pytest

from src.pdf_generator import qc_icons
from src.quality.fg_qc import FG_QC_CHECKS


def _drawn_points(pdf):
    points = []
    for c in pdf.line.call_args_list:
        points += [(c.args[0], c.args[1]), (c.args[2], c.args[3])]
    for c in pdf.rect.call_args_list + pdf.ellipse.call_args_list:
        x, y, w, h = c.args[:4]
        points += [(x, y), (x + w, y + h)]
    for c in pdf.polyline.call_args_list + pdf.polygon.call_args_list:
        points += list(c.args[0])
    return points


def test_every_checklist_item_has_a_picture():
    assert {check.key for check in FG_QC_CHECKS} == qc_icons.ICON_KEYS


@pytest.mark.parametrize("key", sorted(qc_icons.ICON_KEYS))
def test_picture_stays_inside_its_square(key):
    pdf = MagicMock()
    qc_icons.draw_check_icon(pdf, key, 10, 20, 9)

    points = _drawn_points(pdf)
    assert points
    assert all(10 - 1e-9 <= x <= 19 + 1e-9 and 20 - 1e-9 <= y <= 29 + 1e-9 for x, y in points)


def test_unknown_check_draws_nothing():
    pdf = MagicMock()
    qc_icons.draw_check_icon(pdf, "not_a_check", 0, 0, 9)
    assert not pdf.method_calls


@pytest.mark.parametrize("draw", [qc_icons.draw_tick, qc_icons.draw_cross])
def test_answer_marks_stay_inside_their_square(draw):
    pdf = MagicMock()
    draw(pdf, 5, 5, 5)

    points = _drawn_points(pdf)
    assert points
    assert all(5 <= x <= 10 and 5 <= y <= 10 for x, y in points)
