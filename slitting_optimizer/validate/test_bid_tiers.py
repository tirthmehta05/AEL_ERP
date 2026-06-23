"""Unit tests for engine.bid_tiers — the shared tier helper used by the
Excel report and the Streamlit page. Run with `pytest validate/`."""

import os

import pytest

from engine import bid_tiers as bt


# ─── parse_bid_tiers ────────────────────────────────────────────────────────

def test_parse_default():
    tiers = bt.parse_bid_tiers(bt.DEFAULT_BID_TIERS)
    assert tiers == [
        ("safe",       0.08),
        ("compete",    0.05),
        ("aggressive", 0.03),
        ("ceiling",    0.0),
    ]


def test_parse_single():
    assert bt.parse_bid_tiers("only:0.06") == [("only", 0.06)]


def test_parse_strips_whitespace():
    assert bt.parse_bid_tiers(" safe : 0.08 , ceiling : 0 ") == [
        ("safe", 0.08), ("ceiling", 0.0)]


def test_parse_rejects_empty():
    with pytest.raises(ValueError, match="at least one tier"):
        bt.parse_bid_tiers("")


def test_parse_rejects_missing_colon():
    with pytest.raises(ValueError, match="missing colon"):
        bt.parse_bid_tiers("safe0.08")


def test_parse_rejects_empty_name():
    with pytest.raises(ValueError, match="empty name"):
        bt.parse_bid_tiers(":0.08")


def test_parse_rejects_non_numeric_margin():
    with pytest.raises(ValueError, match="non-numeric"):
        bt.parse_bid_tiers("safe:high")


def test_parse_rejects_out_of_range():
    with pytest.raises(ValueError, match="must be in"):
        bt.parse_bid_tiers("safe:1.5")
    with pytest.raises(ValueError, match="must be in"):
        bt.parse_bid_tiers("safe:-0.1")


# ─── get_bid_tiers reads env at call time ───────────────────────────────────

def test_env_override(monkeypatch):
    monkeypatch.setenv("SLIT_BID_TIERS", "fast:0.02,slow:0.10")
    assert bt.get_bid_tiers() == [("fast", 0.02), ("slow", 0.10)]


def test_env_default(monkeypatch):
    monkeypatch.delenv("SLIT_BID_TIERS", raising=False)
    tiers = bt.get_bid_tiers()
    assert tiers[0] == ("safe", 0.08)


# ─── bid_for_net_margin: the formula ────────────────────────────────────────

def test_zero_weight_returns_zero():
    assert bt.bid_for_net_margin(1_000_000, 0, 0, 0, 0.08) == 0.0


def test_ceiling_bid_gives_zero_profit():
    """At ceiling (0% net margin), revenue - bid*wt - slit - transport = 0."""
    rev, slit, transport, wt = 1_000_000.0, 50_000.0, 10_000.0, 10_000
    bid = bt.bid_for_net_margin(rev, slit, transport, wt, 0.0)
    net_profit = rev - bid * wt - slit - transport
    assert abs(net_profit) < 0.01


def test_safe_tier_gives_exact_target_margin():
    """At SAFE (8% net target), the realised net margin is exactly 8%."""
    rev, slit, transport, wt = 3_174_960.0, 0.0, 39_687.0, 39_687
    bid = bt.bid_for_net_margin(rev, slit, transport, wt, 0.08)
    net_profit = rev - bid * wt - slit - transport
    net_margin = net_profit / rev
    assert net_margin == pytest.approx(0.08, abs=1e-6)


def test_tiers_strictly_increasing_in_bid():
    """As margin target falls (safe → ceiling), the allowed bid ceiling rises."""
    rev, slit, transport, wt = 4_181_504.0, 211_992.0, 76_472.0, 52_998
    bids = [bt.bid_for_net_margin(rev, slit, transport, wt, m)
            for m in (0.08, 0.05, 0.03, 0.0)]
    assert bids == sorted(bids), f"Tier bids should ascend, got {bids}"


def test_steelemart_lot_281917_safe_matches_real_run():
    """Regression: SAFE bid on Steelemart lot 281917 (100% KAPSON, no slit,
    KAPSON transport ₹1/kg). Should yield ~₹72.60/kg at 8% net target."""
    rev = 3_174_960.0       # 39,687 kg × ₹80
    slit = 0.0              # KAPSON whole-coil → no slit cost
    transport = 39_687.0    # 39.687 T × ₹1000/T = ₹39,687
    wt = 39_687
    bid = bt.bid_for_net_margin(rev, slit, transport, wt, 0.08)
    assert bid == pytest.approx(72.60, abs=0.05)


def test_linear_in_target_margin():
    """bid(margin) should be a linear function of margin (slope -rev/wt)."""
    rev, slit, transport, wt = 1_000_000.0, 0.0, 0.0, 10_000
    b0 = bt.bid_for_net_margin(rev, slit, transport, wt, 0.0)
    b1 = bt.bid_for_net_margin(rev, slit, transport, wt, 0.10)
    expected_slope = -rev / wt
    actual_slope = (b1 - b0) / 0.10
    assert actual_slope == pytest.approx(expected_slope, rel=1e-6)
