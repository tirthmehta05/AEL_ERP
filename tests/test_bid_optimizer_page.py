"""Tests for pages/bid_optimizer.py.

The page imports streamlit at module load, but conftest.py mocks the entire
streamlit module — so we can import the page in tests and exercise its
pure data-shaping helpers (`_enrich_record`, `_build_excel_blob`) without
launching a real Streamlit runtime.

The hard end-to-end test (Streamlit AppTest with file upload + button click)
lives in Phase F manual testing — running pytest with mocked streamlit will
exercise everything except the actual widget rendering.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# conftest.py has already prepended PROJECT_ROOT and mocked streamlit.
from pages import bid_optimizer as bo


# Engine modules were loaded as a side-effect of importing bid_optimizer
# (it prepends slitting_optimizer/ to sys.path). Re-use those here.
from engine import optimizer as eng                # noqa: E402
from engine import incremental as inc              # noqa: E402
from app.repository import auction_repository as ar  # noqa: E402
from app.repository import customer_repository as cr  # noqa: E402
from tools import measurement_report as mr         # noqa: E402

_SLOPT = Path(__file__).resolve().parent.parent / "slitting_optimizer"
_CUSTOMERS = _SLOPT / "data" / "sample_customers_v3.xlsx"
_MI_PUNE = _SLOPT / "data" / "sample_auction_lists" / "CRNO 27.05.2026 MI PUNE.xlsx"


@pytest.fixture(scope="module")
def orders_and_flags():
    if not _CUSTOMERS.exists():
        pytest.skip(f"customer fixture not found at {_CUSTOMERS}")
    orders, flags = cr.parse_customers(str(_CUSTOMERS))
    return orders, flags


@pytest.fixture(scope="module")
def solved_mi_pune(orders_and_flags):
    """Solve the small MI Pune auction once per test module (~2s)."""
    if not _MI_PUNE.exists():
        pytest.skip(f"auction fixture not found at {_MI_PUNE}")
    orders, _ = orders_and_flags
    os.environ.setdefault("SLIT_KNIFE_MAX_WIDE", "19")
    coils, auction_flags = ar.parse_auction(_MI_PUNE)
    from collections import defaultdict
    by_lot = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)
    records = [mr._build_lot_record(lot, by_lot[lot], orders, 30)
               for lot in sorted(by_lot)]
    return records, auction_flags


def test_enrich_record_produces_required_ui_fields(solved_mi_pune, orders_and_flags):
    records, _ = solved_mi_pune
    orders, _ = orders_and_flags
    # Find the bidable MI Pune lot (279263).
    target = next((r for r in records if r["feasible"] and r["lot"] == "279263"),
                  None)
    assert target is not None, "Lot 279263 must solve feasibly"

    enriched = bo._enrich_record(target, orders)
    # Required UI keys
    for key in ("lot", "weight_kg", "n_coils", "start", "coatings",
                "revenue", "slit_cost", "transport", "tiers",
                "primary_name", "primary_bid", "bidable", "headroom",
                "profit_primary", "margin_net", "margin_gross",
                "transport_pct", "by_cust", "scrap_kg", "scrap_pct",
                "coils", "coil_break"):
        assert key in enriched, f"missing UI field: {key}"
    # Four tiers by default; first is "safe"
    assert len(enriched["tiers"]) == 4
    assert enriched["primary_name"] == "safe"


def test_tier_ordering(solved_mi_pune, orders_and_flags):
    """For any bidable lot: ceiling > aggressive > compete > safe."""
    records, _ = solved_mi_pune
    orders, _ = orders_and_flags
    for r in records:
        if not r["feasible"]:
            continue
        enriched = bo._enrich_record(r, orders)
        bids = [b for _, _, b in enriched["tiers"]]
        assert bids == sorted(bids), f"lot {r['lot']} tiers not ascending: {bids}"


def test_bidable_flag_matches_primary_vs_start(solved_mi_pune, orders_and_flags):
    records, _ = solved_mi_pune
    orders, _ = orders_and_flags
    for r in records:
        if not r["feasible"]:
            continue
        enriched = bo._enrich_record(r, orders)
        expected = enriched["primary_bid"] >= enriched["start"]
        assert enriched["bidable"] == expected, (
            f"lot {r['lot']}: bidable mismatch")


def test_excel_blob_writes_valid_xlsx(solved_mi_pune, orders_and_flags):
    records, auction_flags = solved_mi_pune
    orders, customer_flags = orders_and_flags
    blob = bo._build_excel_blob(records, orders, customer_flags,
                                auction_flags, "MI_PUNE")
    assert isinstance(blob, bytes)
    assert len(blob) > 10_000, "Excel file looks suspiciously small"
    # Verify openpyxl can parse it and finds the expected sheets
    from openpyxl import load_workbook
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(blob)
        wb = load_workbook(f.name, data_only=True)
        os.unlink(f.name)
    expected = {"Summary", "Per-Lot Summary", "Lot P&L by Tier",
                "Lot Detail (Cut Sheets)", "Customer Fulfillment",
                "Customer × Lot", "Bidable Auction Summary",
                "Salvage", "Width Bands", "Flags"}
    assert expected.issubset(set(wb.sheetnames)), (
        f"missing sheets: {expected - set(wb.sheetnames)}")


def test_kapson_dominant_lot_flagged_single_buyer(solved_mi_pune, orders_and_flags):
    """A lot where one customer takes ≥50% should produce a risk-flag string."""
    records, _ = solved_mi_pune
    orders, _ = orders_and_flags
    for r in records:
        if not r["feasible"]:
            continue
        enriched = bo._enrich_record(r, orders)
        flags_html = bo._render_risk_flags(enriched)
        if not enriched["by_cust"]:
            continue
        top_kg = max(enriched["by_cust"].values())
        if top_kg / enriched["weight_kg"] >= 0.5:
            assert "single buyer" in flags_html, (
                f"lot {enriched['lot']} should flag single-buyer risk")


def test_render_helpers_handle_skip_lots(solved_mi_pune, orders_and_flags):
    """Render functions on a SKIP lot (no customer allocation) must not crash."""
    records, _ = solved_mi_pune
    orders, _ = orders_and_flags
    # 279264 is a SKIP lot (parser flagged no coatings)
    skip = next((r for r in records if r["feasible"] and r["lot"] == "279264"),
                None)
    if skip is None:
        pytest.skip("expected SKIP lot 279264 not present in fixture")
    enriched = bo._enrich_record(skip, orders)
    assert enriched["bidable"] is False
    # These all return strings or None; just ensure no exception.
    bo._render_risk_flags(enriched)
