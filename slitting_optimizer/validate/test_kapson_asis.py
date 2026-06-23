"""Hand-computed fixtures for the KAPSON range-mode (asis) feature.

The Width column accepts either a single number ("60" → slit, exact strip)
or a range ("1000-1650" → asis, whole coil within the range). Asis orders
consume the COIL's full weight against the order's monthly cap; slit-mode
orders only receive strips. These tests pin both behaviors exactly.

Run with `pytest validate/test_kapson_asis.py`.
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from app.repository.customer_repository import _parse_width
from engine import optimizer as eng


# ─── Width parser: range vs single-value behaviour ──────────────────────────

def test_parse_width_single_value_is_slit():
    mode, w, lo, hi = _parse_width("60")
    assert mode == "slit"
    assert w == int(round(60 * eng.WIDTH_SCALE))
    assert lo is None and hi is None


def test_parse_width_range_is_asis():
    mode, w, lo, hi = _parse_width("1000-1650")
    assert mode == "asis"
    assert w == 0
    assert lo == int(round(1000 * eng.WIDTH_SCALE))
    assert hi == int(round(1650 * eng.WIDTH_SCALE))


def test_parse_width_collapsed_range_is_slit():
    """X-X should collapse to a slit-mode exact width (no point making it asis)."""
    mode, w, _, _ = _parse_width("500-500")
    assert mode == "slit"
    assert w == int(round(500 * eng.WIDTH_SCALE))


def test_parse_width_rejects_inverted_range():
    import pytest
    with pytest.raises(ValueError, match="min > max"):
        _parse_width("1650-1000")


def test_parse_width_rejects_non_numeric():
    import pytest
    with pytest.raises(ValueError):
        _parse_width("wide-narrow")


# ─── Engine end-to-end: asis disposition is selected when KAPSON fits ───────

def _kapson_order(monthly_t=300, min_w=1000, max_w=1650, rate=80,
                  grades=("50c470",), coatings=("C5L", "C6L"),
                  thickness=0.5, oid=0):
    return {
        "id": oid, "customer": "KAPSON",
        "mode": "asis", "width_cdmm": 0,
        "width_min_cdmm": int(round(min_w * eng.WIDTH_SCALE)),
        "width_max_cdmm": int(round(max_w * eng.WIDTH_SCALE)),
        "qty_g": int(round(monthly_t * eng.MT_TO_GRAMS)),
        "monthly_g": int(round(monthly_t * eng.MT_TO_GRAMS)),
        "rate_per_kg": rate,
        "grades": set(grades), "coatings": set(coatings),
        "thicknesses": {round(thickness, 3)},
        "min_coil_g": 0,
    }


def _slit_order(width_mm=60, monthly_t=10, rate=80, grades=("50c470",),
                coatings=("C6L",), thickness=0.5, oid=0):
    return {
        "id": oid, "customer": "Amba",
        "mode": "slit",
        "width_cdmm": int(round(width_mm * eng.WIDTH_SCALE)),
        "width_min_cdmm": None, "width_max_cdmm": None,
        "qty_g": int(round(monthly_t * eng.MT_TO_GRAMS)),
        "monthly_g": int(round(monthly_t * eng.MT_TO_GRAMS)),
        "rate_per_kg": rate,
        "grades": set(grades), "coatings": set(coatings),
        "thicknesses": {round(thickness, 3)},
        "min_coil_g": 0,
    }


def _coil(width_mm=1065, weight_kg=5310, grade="50c470", coating="C6L",
          thickness=0.5, price_per_kg=63):
    return {
        "id": 0, "lot": "test", "batch": "TST001",
        "width_cdmm": int(round(width_mm * eng.WIDTH_SCALE)),
        "weight_g": int(round(weight_kg * 1000)),
        "price_per_kg": price_per_kg,
        "grade": grade, "coating": coating,
        "thickness": round(thickness, 3),
    }


def test_F1_asis_only_kapson_takes_whole_coil():
    """KAPSON range covers the coil, no other buyer exists → asis fires."""
    coils = [_coil()]
    orders = [_kapson_order(oid=0)]
    res = eng.solve(coils, orders, n_workers=2)
    s = res["solver"]
    assert res["status"] in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert s.Value(res["as_is"][0]) == 1, "as_is disposition should fire"
    assert s.Value(res["slit"][0]) == 0, "slit must NOT fire"
    assert s.Value(res["asis_alloc"][0, 0]) == 1, "KAPSON should get the coil"


def test_F2_kapson_vs_amba_picks_higher_value():
    """When BOTH KAPSON (whole) and Amba (slit) accept the coil, optimizer
    picks the higher-value disposition. KAPSON at ₹80 with no slit cost beats
    Amba slit at ₹80 - ₹4/kg slit cost — KAPSON should win."""
    coils = [_coil()]
    orders = [_kapson_order(oid=0), _slit_order(oid=1)]
    res = eng.solve(coils, orders, n_workers=2)
    s = res["solver"]
    assert res["status"] in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert s.Value(res["as_is"][0]) == 1, "whole-coil to KAPSON wins"
    # KAPSON gets it, not Amba
    assert s.Value(res["asis_alloc"][0, 0]) == 1
    amba_strips = sum(s.Value(res["x"].get((0, 1), 0)) if (0, 1) in res["x"]
                      else 0 for _ in [None])
    assert amba_strips == 0, "Amba should get zero strips when KAPSON wins"


def test_F3_grade_mismatch_blocks_kapson():
    """KAPSON only accepts grade 50c470. A 50c800 coil must NOT trigger asis."""
    coils = [_coil(grade="50c800")]
    orders = [_kapson_order(grades=("50c470",), oid=0)]
    res = eng.solve(coils, orders, n_workers=2)
    s = res["solver"]
    assert res["status"] in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    # No compatible order → as_is must be 0 (forced)
    assert s.Value(res["as_is"][0]) == 0


def test_F4_width_outside_range_blocks_kapson():
    """KAPSON accepts 1000-1650mm. A 800mm coil falls outside; asis must NOT fire."""
    coils = [_coil(width_mm=800)]
    orders = [_kapson_order(min_w=1000, max_w=1650, oid=0)]
    res = eng.solve(coils, orders, n_workers=2)
    s = res["solver"]
    assert res["status"] in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert s.Value(res["as_is"][0]) == 0
