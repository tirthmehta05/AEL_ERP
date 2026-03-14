"""Tests for uniform-or-mixed sets logic introduced in the Weight Receipt save flow.

Covers:
1. Model accepts int and "Mixed" string for WeightReceiptRequest / WeightReceiptRecord.
2. Pure logic that derives the receipt-level sets value from per-design sets.
"""

import pytest
from datetime import date
from src.data_entry.models.weight_receipt_models import (
    WeighedDesignDetail,
    WeightReceiptRequest,
    WeightReceiptRecord,
)


# ---------------------------------------------------------------------------
# Helper: mirrors the logic added to pages/weight_receipt.py
# ---------------------------------------------------------------------------
def _compute_receipt_sets(weighed_designs, is_itemized_mode, fallback=0):
    """Pure copy of the uniform-or-mixed logic used at save time."""
    if is_itemized_mode and weighed_designs:
        design_sets_vals = [d.sets for d in weighed_designs if d.sets is not None]
        if not design_sets_vals:
            return fallback
        unique_sets = set(design_sets_vals)
        return design_sets_vals[0] if len(unique_sets) == 1 else "Mixed"
    return fallback


def _make_design(sets_val):
    return WeighedDesignDetail(width=100.0, length=200.0, sets=sets_val)


# ---------------------------------------------------------------------------
# Model validation tests
# ---------------------------------------------------------------------------
class TestWeightReceiptRequestSetsType:
    def _base(self, sets_val):
        return WeightReceiptRequest(
            weight_receipt_number="WR-001",
            receipt_date=date(2024, 1, 1),
            job_card_number="JC-001",
            party_name="Test Party",
            material="CRGO",
            sets=sets_val,
            designs=[],
        )

    def test_accepts_integer_sets(self):
        req = self._base(5)
        assert req.sets == 5

    def test_accepts_mixed_string(self):
        req = self._base("Mixed")
        assert req.sets == "Mixed"

    def test_accepts_zero(self):
        req = self._base(0)
        assert req.sets == 0


class TestWeightReceiptRecordSetsType:
    def _base(self, sets_val):
        return WeightReceiptRecord(
            weight_receipt_number="WR-001",
            receipt_date=date(2024, 1, 1),
            job_card_number="JC-001",
            party_name="Test Party",
            material="CRGO",
            sets=sets_val,
            designs_json="[]",
        )

    def test_accepts_integer_sets(self):
        rec = self._base(3)
        assert rec.sets == 3

    def test_accepts_mixed_string(self):
        rec = self._base("Mixed")
        assert rec.sets == "Mixed"

    def test_to_list_preserves_integer_sets(self):
        rec = self._base(4)
        row = rec.to_list()
        assert row[6] == 4

    def test_to_list_preserves_mixed_string(self):
        rec = self._base("Mixed")
        row = rec.to_list()
        assert row[6] == "Mixed"


# ---------------------------------------------------------------------------
# Logic tests for _compute_receipt_sets
# ---------------------------------------------------------------------------
class TestComputeReceiptSets:
    def test_uniform_sets_returns_that_value(self):
        designs = [_make_design(3), _make_design(3), _make_design(3)]
        assert _compute_receipt_sets(designs, is_itemized_mode=True) == 3

    def test_mixed_sets_returns_mixed_string(self):
        designs = [_make_design(2), _make_design(3), _make_design(5)]
        assert _compute_receipt_sets(designs, is_itemized_mode=True) == "Mixed"

    def test_two_designs_different_sets_returns_mixed(self):
        designs = [_make_design(1), _make_design(4)]
        assert _compute_receipt_sets(designs, is_itemized_mode=True) == "Mixed"

    def test_single_design_returns_its_sets(self):
        designs = [_make_design(7)]
        assert _compute_receipt_sets(designs, is_itemized_mode=True) == 7

    def test_non_itemized_mode_uses_fallback(self):
        designs = [_make_design(3), _make_design(5)]
        assert _compute_receipt_sets(designs, is_itemized_mode=False, fallback=10) == 10

    def test_empty_designs_uses_fallback(self):
        assert _compute_receipt_sets([], is_itemized_mode=True, fallback=0) == 0

    def test_designs_with_none_sets_ignored(self):
        """Designs without a sets value should not count toward uniqueness."""
        designs = [_make_design(3), WeighedDesignDetail(width=100.0, length=200.0, sets=None)]
        # Only one non-None value → uniform
        assert _compute_receipt_sets(designs, is_itemized_mode=True) == 3

    def test_all_designs_none_sets_uses_fallback(self):
        designs = [WeighedDesignDetail(width=100.0, length=200.0, sets=None)]
        assert _compute_receipt_sets(designs, is_itemized_mode=True, fallback=0) == 0
