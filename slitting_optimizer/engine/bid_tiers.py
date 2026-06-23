"""Bid-tier helpers — single source of truth for the multi-tier max-bid
display used by both the Excel report (`tools/measurement_report.py`)
and the Streamlit UI (`pages/bid_optimizer.py` in the ERP).

Each tier yields the ₹/kg bid ceiling at which net margin (post-transport)
hits exactly the named target. Per-lot revenue/slit-cost/transport are
fixed once the optimizer solves the lot, so any tier's bid is a linear
function — we compute them all from one solve.

The FIRST tier in the list is the "primary": it drives the bidable flag
(bidable = primary bid >= lot start price) and the profit/margin display
columns. Override via SLIT_BID_TIERS env (comma list of `name:margin`):

    SLIT_BID_TIERS=safe:0.10,ceiling:0.0      # 2-tier preset
    SLIT_BID_TIERS=safe:0.08,compete:0.05,aggressive:0.03,ceiling:0.0  # default 4-tier
"""

from __future__ import annotations

import os


DEFAULT_BID_TIERS = "safe:0.08,compete:0.05,aggressive:0.03,ceiling:0.0"


def parse_bid_tiers(spec: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for pair in spec.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise ValueError(f"SLIT_BID_TIERS entry '{pair}' missing colon "
                             "(expected name:margin)")
        name, margin = pair.split(":", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"SLIT_BID_TIERS entry '{pair}' has empty name")
        try:
            m = float(margin)
        except (ValueError, TypeError):
            raise ValueError(
                f"SLIT_BID_TIERS entry '{pair}' has non-numeric margin")
        if not (0.0 <= m <= 1.0):
            raise ValueError(f"SLIT_BID_TIERS margin {m} for '{name}' "
                             "must be in [0.0, 1.0]")
        out.append((name, m))
    if not out:
        raise ValueError("SLIT_BID_TIERS must list at least one tier")
    return out


def get_bid_tiers() -> list[tuple[str, float]]:
    """Read SLIT_BID_TIERS at call-time so changes take effect without restart."""
    return parse_bid_tiers(os.environ.get("SLIT_BID_TIERS", DEFAULT_BID_TIERS))


def bid_for_net_margin(revenue: float, slit_cost: float,
                       transport: float, weight_kg: float,
                       margin_net: float) -> float:
    """₹/kg bid that yields exactly `margin_net` post-transport, given fixed
    revenue / slit_cost / transport from the solved lot. Linear in bid."""
    if weight_kg <= 0:
        return 0.0
    return (revenue * (1 - margin_net) - slit_cost - transport) / weight_kg
