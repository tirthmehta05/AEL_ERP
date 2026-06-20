"""Bid Optimizer — inline Streamlit page over the vendored slitting_optimizer
engine. Pre-auction workflow: the procurement assistant uploads an auction
Excel, the engine solves each lot, and per-lot cards surface BID/SKIP plus
four bid tiers (SAFE 8% / COMPETE 5% / AGGRESSIVE 3% / CEILING 0% — all
post-transport net margins). Drill-downs show P&L by tier, the cut plan,
and per-customer allocation. A full multi-sheet Excel report is
downloadable from the header.

The engine module ships under `slitting_optimizer/`; we prepend its path so
its internal `from engine import …` / `from app.repository import …` imports
keep working unchanged.
"""

from __future__ import annotations

import io
import sys
import time
import tempfile
from collections import defaultdict
from pathlib import Path

import streamlit as st

from src.shared.utils.logger_config import setup_logger

# ── Engine import (vendored library lives at AEL_ERP/slitting_optimizer/) ────
_SLOPT_ROOT = Path(__file__).resolve().parent.parent / "slitting_optimizer"
if str(_SLOPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLOPT_ROOT))

from engine import incremental as inc                       # noqa: E402
from engine import optimizer as eng                         # noqa: E402
from engine.bid_tiers import bid_for_net_margin, get_bid_tiers  # noqa: E402
from app.repository import auction_repository as ar         # noqa: E402
from tools import measurement_report as mr                  # noqa: E402

logger = setup_logger(__name__)

_LOCK_S = 30                                                # double-submit window
_CUSTOMERS_PATH = _SLOPT_ROOT / "data" / "sample_customers_v3.xlsx"

# Tier visual styling — colored left-edge + chip backgrounds. Keep in sync
# with the design system documented in the page-level CSS below.
_TIER_COLORS = {
    "safe":       ("#E8F2EC", "#2A6450"),
    "compete":    ("#FAEFD8", "#8C6515"),
    "aggressive": ("#F5E1D8", "#A04020"),
    "ceiling":    ("#ECDADA", "#6A2020"),
}


# ── Streamlit session-state plumbing ────────────────────────────────────────

def _init_state() -> None:
    defaults = {
        "slopt_uploaded_name": None,
        "slopt_auction_bytes": None,
        "slopt_orders": None,
        "slopt_lot_records": None,
        "slopt_auction_flags": None,
        "slopt_solve_lock": 0.0,
        # Per-lot transport overrides set by the user post-solve. Shape:
        #   { lot_id: {"kapson_rs_per_kg": float,
        #              "slitter_rs_per_kg": float} }
        # Defaults when missing: KAPSON ₹1/kg (current TRANSPORT_RATES),
        # source→slitter ₹0 (implicit current assumption). The optimizer
        # doesn't see transport — only the bid ceiling depends on it, so
        # this is a pure display-layer recompute (no re-solve).
        "slopt_transport_overrides": {},
        # Per-coil quality factor (0.0-1.0; 1.0 = perfect). User edits the
        # per-coil table inside each lot's "Adjust quality" tab to discount
        # rusty / aged / damaged coils. Affects the bid CEILING only via
        # adjusted revenue — cut plan stays the same. Shape:
        #   { lot_id: {coil_id: {"year": int|None,
        #                        "quality": float}} }
        "slopt_coil_quality": {},
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _locked() -> bool:
    if time.time() - st.session_state.slopt_solve_lock < _LOCK_S:
        st.warning("A solve is already in progress — please wait…")
        return True
    st.session_state.slopt_solve_lock = time.time()
    return False


def _reset() -> None:
    for k in list(st.session_state):
        if k.startswith("slopt_"):
            del st.session_state[k]
    _init_state()


# ── Design tokens injected once per page render ─────────────────────────────

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

.bo-root, .bo-root * { font-family: 'IBM Plex Sans', sans-serif; color: #18202A; }
.bo-disp { font-family: 'IBM Plex Sans Condensed', sans-serif; font-weight: 700; letter-spacing: 0.02em; }
.bo-mono { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }
.bo-mute { color: #59636E; }
.bo-faint { color: #939BA4; }

.bo-card { background: #fff; border-left: 4px solid #DCE0E0; padding: 18px 22px;
           margin: 10px 0; border-radius: 4px; box-shadow: 0 1px 2px rgba(20,30,40,0.04); }
.bo-card.bid  { border-left-color: #2A6450; }
.bo-card.skip { border-left-color: #7A7E84; background: #F7F7F6; }

.bo-card-head { display: flex; align-items: baseline; gap: 16px; margin-bottom: 14px; }
.bo-lot-no    { font-family: 'IBM Plex Sans Condensed'; font-weight: 700; font-size: 20px; letter-spacing: 0.04em; }
.bo-status    { font-family: 'IBM Plex Sans Condensed'; font-weight: 600; font-size: 11px;
                letter-spacing: 0.10em; padding: 2px 8px; border-radius: 2px; }
.bo-status.bid  { background: #E8F2EC; color: #2A6450; }
.bo-status.skip { background: #ECECEC; color: #5C6068; }
.bo-meta { margin-left: auto; font-size: 12px; color: #59636E; font-family: 'IBM Plex Mono'; }

.bo-grid { display: grid; grid-template-columns: 2fr 3fr; gap: 28px; align-items: start; }
.bo-spec { font-size: 13px; line-height: 1.7; color: #59636E; }
.bo-spec strong { color: #18202A; font-weight: 600; }

.bo-tier-table { width: 100%; border-collapse: collapse; }
.bo-tier-row td { padding: 8px 10px; font-family: 'IBM Plex Mono'; font-size: 13px;
                  border-bottom: 1px solid #ECEEEC; }
.bo-tier-row td.tier-name { font-family: 'IBM Plex Sans Condensed'; font-weight: 600;
                            font-size: 11px; letter-spacing: 0.08em; }
.bo-tier-row td.tier-bid  { font-size: 16px; font-weight: 600; text-align: right; }
.bo-tier-row td.tier-pct  { text-align: right; }
.bo-tier-row td.tier-band { width: 4px; padding: 0; }
.bo-tier-row.primary td   { background: #FAFAFA; }

.bo-flag  { display: inline-block; font-family: 'IBM Plex Mono'; font-size: 11px;
            letter-spacing: 0.05em; text-transform: uppercase; padding: 3px 8px;
            margin: 4px 6px 0 0; border: 1px solid #B85638; color: #B85638; border-radius: 2px; }
.bo-flag.muted { border-color: #939BA4; color: #59636E; }

.bo-mini { font-family: 'IBM Plex Mono'; font-size: 12px; color: #18202A; }
.bo-mini-label { color: #939BA4; font-family: 'IBM Plex Sans Condensed'; font-weight: 600;
                 font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }

.bo-pattern { font-family: 'IBM Plex Mono'; font-size: 12px; line-height: 1.6;
              background: #F7F7F6; padding: 10px 12px; border-radius: 3px;
              white-space: pre-wrap; word-break: break-word; }

.bo-section-head { font-family: 'IBM Plex Sans Condensed'; font-weight: 700; font-size: 13px;
                   letter-spacing: 0.10em; text-transform: uppercase; color: #18202A;
                   border-bottom: 1px solid #DCE0E0; padding-bottom: 6px; margin: 28px 0 12px; }
</style>
"""


# ── Solve & extract per-lot record ──────────────────────────────────────────

def _solve_auction(auction_path: Path, orders, status_cb, time_limit_s: int):
    """Iterate lots, solve each, stream progress through status_cb(lot, idx, total, summary).
    Returns (records, auction_flags).

    The engine's SOLVE_TIME_LIMIT_S is a module-level constant set at import
    from os.environ. We override it directly per solve here so the slider's
    value is actually honoured (env vars set after import are not re-read)."""
    coils, auction_flags = ar.parse_auction(auction_path)
    by_lot: dict[str, list[dict]] = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)
    lots = sorted(by_lot)
    records = []
    old_limit = eng.SOLVE_TIME_LIMIT_S
    try:
        eng.SOLVE_TIME_LIMIT_S = time_limit_s
        for i, lot in enumerate(lots, start=1):
            status_cb(lot, i, len(lots), None)
            rec = mr._build_lot_record(lot, by_lot[lot], orders, time_limit_s)
            records.append(rec)
            status_cb(lot, i, len(lots), rec)
    finally:
        eng.SOLVE_TIME_LIMIT_S = old_limit
    return records, auction_flags


def _compute_transport(rec, orders, override: dict | None) -> dict:
    """Per-lot transport breakdown.

    Three components (only the first two are user-overridable):
      1. KAPSON-bound kg × source→KAPSON ₹/kg (override `kapson_rs_per_kg`,
         default the existing TRANSPORT_RATES["kapson"] flat rate, ₹1/kg).
      2. Slit-bound kg × source→OUR slitter ₹/kg (override
         `slitter_rs_per_kg`, default ₹0 — current implicit assumption).
      3. Per-customer slitter→customer ₹/T from TRANSPORT_RATES (fixed;
         these don't depend on source location, only customer destination).

    Returns {kapson_kg, kapson_rate, kapson_cost, slit_kg, slit_rate,
             slit_cost_source, cust_cost_slitter_to_customer, total}.
    """
    override = override or {}
    # split allocations by KAPSON vs slit
    kapson_kg = 0.0
    slit_kg_by_cust: dict[str, float] = defaultdict(float)
    for oid, kg in rec.get("cust_alloc_kg", {}).items():
        cust = next(o["customer"] for o in orders if o["id"] == oid)
        if cust.lower() == "kapson":
            kapson_kg += kg
        else:
            slit_kg_by_cust[cust] += kg
    slit_kg = sum(slit_kg_by_cust.values())
    # 1. source → KAPSON
    kapson_rate = float(override.get("kapson_rs_per_kg", 1.0))
    kapson_cost = kapson_kg * kapson_rate
    # 2. source → slitter (only for slit-bound material)
    slitter_rate = float(override.get("slitter_rs_per_kg", 0.0))
    slit_cost_source = slit_kg * slitter_rate
    # 3. slitter → customer (per-customer fixed bracket rates)
    cust_cost = 0.0
    for cust, kg in slit_kg_by_cust.items():
        rate_per_t = mr._bracket_rate_for_auction(cust, kg)
        cust_cost += rate_per_t * kg / 1000
    total = kapson_cost + slit_cost_source + cust_cost
    return {
        "kapson_kg": kapson_kg, "kapson_rate": kapson_rate,
        "kapson_cost": kapson_cost,
        "slit_kg": slit_kg, "slit_rate": slitter_rate,
        "slit_cost_source": slit_cost_source,
        "cust_cost_slitter_to_customer": cust_cost,
        "total": total,
    }


def _adjusted_revenue(rec, coil_quality: dict | None) -> tuple[float, bool]:
    """Apply per-coil quality factors to the solved lot's total revenue.

    Each coil contributes proportionally to its weight; quality ∈ [0,1]
    scales that contribution. Returns (effective_revenue, any_haircut).
    If no quality overrides exist or all are 1.0, returns the unmodified
    revenue (and any_haircut=False)."""
    base_rev = rec["metrics"]["total_rev"]
    total_kg = rec["metrics"]["total_wt"]
    if not coil_quality or total_kg <= 0:
        return base_rev, False
    adjusted = 0.0
    any_haircut = False
    for c in rec["coils"]:
        kg = c["weight_g"] / 1000
        share = base_rev * (kg / total_kg)
        q = float(coil_quality.get(c["id"], {}).get("quality", 1.0))
        if q < 1.0:
            any_haircut = True
        adjusted += q * share
    return adjusted, any_haircut


def _enrich_record(rec, orders, transport_override: dict | None = None,
                   coil_quality: dict | None = None) -> dict:
    """Compute tier bids, transport, headroom, customer split. Returns a flat dict
    of UI-ready fields keyed off the lot record. Idempotent — safe to re-call.

    `transport_override` is the per-lot dict (kapson_rs_per_kg, slitter_rs_per_kg);
    None falls back to defaults (₹1/kg KAPSON, ₹0 slitter).
    `coil_quality` is a {coil_id: {year, quality}} dict for this lot; default
    is all coils at 100%."""
    if not rec["feasible"]:
        return {"feasible": False, "lot": rec["lot"], "status": rec["status"]}
    m = rec["metrics"]
    coils = rec["coils"]
    weight = m["total_wt"]
    base_revenue = m["total_rev"]
    revenue, quality_applied = _adjusted_revenue(rec, coil_quality)
    slit_cost = rec.get("slit_cost_rs", 0.0)
    start = coils[0]["price_per_kg"] if coils else 0.0
    tx = _compute_transport(rec, orders, transport_override)
    transport = tx["total"]
    tiers = get_bid_tiers()
    bids = [(name, mn, bid_for_net_margin(revenue, slit_cost, transport,
                                          weight, mn))
            for name, mn in tiers]
    primary_name, primary_mn, primary_bid = bids[0]
    bidable = primary_bid >= start
    profit_primary = revenue - primary_bid * weight - slit_cost - transport
    margin_net = (100 * profit_primary / revenue) if revenue else 0
    margin_gross = margin_net + (100 * transport / revenue if revenue else 0)
    # disposition split — kg by customer (slit + asis)
    by_cust = defaultdict(float)
    for oid, kg in rec.get("cust_alloc_kg", {}).items():
        cust = next(o["customer"] for o in orders if o["id"] == oid)
        by_cust[cust] += kg
    coatings = sorted({c["coating"] for c in coils})
    return {
        "feasible": True, "lot": rec["lot"], "weight_kg": weight,
        "n_coils": len(coils), "start": start, "coatings": coatings,
        "revenue": revenue, "base_revenue": base_revenue,
        "quality_applied": quality_applied,
        "slit_cost": slit_cost, "transport": transport,
        "transport_breakdown": tx,
        "tiers": bids, "primary_name": primary_name,
        "primary_bid": primary_bid, "bidable": bidable,
        "headroom": primary_bid - start,
        "profit_primary": profit_primary,
        "margin_net": margin_net, "margin_gross": margin_gross,
        "transport_pct": (100 * transport / revenue if revenue else 0),
        "by_cust": dict(by_cust),
        "scrap_kg": rec["kg_scrap"], "scrap_pct": (100 * rec["kg_scrap"] / weight
                                                   if weight else 0),
        "coils": coils, "coil_break": rec.get("coil_break", {}),
    }


# ── Renderers ───────────────────────────────────────────────────────────────

def _fmt_rs(n) -> str:
    return f"₹{n:,.0f}" if n is not None else "—"


def _fmt_kg(n) -> str:
    return f"{n:,.0f} kg"


def _fmt_t(kg) -> str:
    return f"{kg/1000:.1f} T"


def _render_header(records_summary):
    n_bidable = sum(1 for r in records_summary if r["bidable"])
    n_total = len(records_summary)
    total_profit = sum(r["profit_primary"] for r in records_summary if r["bidable"])
    primary_label = records_summary[0]["primary_name"].upper() if records_summary else "SAFE"
    col1, col2, col3 = st.columns(3)
    col1.metric("Bidable lots", f"{n_bidable} / {n_total}")
    col2.metric(f"Projected profit @ {primary_label}", _fmt_rs(total_profit))
    col3.metric("Recommended action",
                "BID" if n_bidable else "SKIP",
                f"{n_bidable} of {n_total}")


def _render_risk_flags(r) -> str:
    flags = []
    top_kg = max(r["by_cust"].values()) if r["by_cust"] else 0
    if r["weight_kg"] and top_kg / r["weight_kg"] >= 0.5:
        top_cust = max(r["by_cust"], key=r["by_cust"].get)
        flags.append(
            f'<span class="bo-flag">{top_cust} '
            f'{100*top_kg/r["weight_kg"]:.0f}% — single buyer</span>')
    if r["scrap_pct"] >= 10:
        flags.append(f'<span class="bo-flag">{r["scrap_pct"]:.0f}% scrap</span>')
    return "".join(flags)


def _render_lot_card(r):
    status = "bid" if r["bidable"] else "skip"
    coat_str = ", ".join(r["coatings"]) or "—"
    headroom_color = "#2A6450" if r["headroom"] >= 0 else "#B85638"
    tier_rows = []
    for i, (name, mn, bid) in enumerate(r["tiers"]):
        bg, fg = _TIER_COLORS.get(name, ("#F7F7F6", "#18202A"))
        primary_cls = " primary" if i == 0 else ""
        label = name.upper()
        if name == "ceiling":
            label_suffix = "  · WALK-AWAY"
        elif i == 0:
            label_suffix = "  · RECOMMENDED"
        else:
            label_suffix = ""
        tier_rows.append(
            f'<tr class="bo-tier-row{primary_cls}">'
            f'<td class="tier-band" style="background:{fg}"></td>'
            f'<td class="tier-name" style="color:{fg}">{label}<span class="bo-faint">{label_suffix}</span></td>'
            f'<td class="tier-bid">₹{bid:.2f}</td>'
            f'<td class="tier-pct" style="background:{bg};color:{fg}">{mn*100:.1f}%</td>'
            f'</tr>'
        )
    flags_html = _render_risk_flags(r)
    # st.html bypasses the markdown processor that was choking on the inline
    # <table>. Keep CSS injection via st.markdown (style tag only) — that path
    # is fine.
    flag_block = (f'<div style="margin-top:8px">{flags_html}</div>'
                  if flags_html else "")
    sign = "+" if r["headroom"] >= 0 else ""
    html = (
        f'<div class="bo-card {status} bo-root">'
        f'<div class="bo-card-head">'
        f'<span class="bo-lot-no">LOT {r["lot"]}</span>'
        f'<span class="bo-status {status}">{"BID" if r["bidable"] else "SKIP"}</span>'
        f'<span class="bo-meta">{_fmt_t(r["weight_kg"])} · {r["n_coils"]} coils · '
        f'start ₹{r["start"]:.2f}/kg · {coat_str}</span>'
        f'</div>'
        f'<div class="bo-grid">'
        f'<div class="bo-spec">'
        f'<div class="bo-mini-label">Headroom @ {r["primary_name"]}</div>'
        f'<div class="bo-mono" style="color:{headroom_color}; font-size:18px; '
        f'font-weight:600; margin:2px 0 14px">{sign}₹{r["headroom"]:.2f} / kg</div>'
        f'<div class="bo-mini-label">Profit @ {r["primary_name"]}</div>'
        f'<div class="bo-mono" style="font-size:16px; font-weight:600; '
        f'margin:2px 0 14px">{_fmt_rs(r["profit_primary"])}</div>'
        f'<div class="bo-mini-label">Margin (net / gross)</div>'
        f'<div class="bo-mono" style="margin:2px 0 14px">'
        f'{r["margin_net"]:.2f}% / {r["margin_gross"]:.2f}%</div>'
        f'<div class="bo-mini-label">Transport %</div>'
        f'<div class="bo-mono" style="margin:2px 0 14px">{r["transport_pct"]:.2f}%</div>'
        f'{flag_block}'
        f'</div>'
        f'<div>'
        f'<div class="bo-mini-label" style="margin-bottom:6px">'
        f'Bid tiers (post-transport net)</div>'
        f'<table class="bo-tier-table">{"".join(tier_rows)}</table>'
        f'</div>'
        f'</div>'
        f'</div>'
    )
    st.html(html)


def _render_pnl_table(r):
    rows = []
    for name, mn, bid in r["tiers"]:
        lot_cost = bid * r["weight_kg"]
        gross_profit = r["revenue"] - lot_cost - r["slit_cost"]
        gross_margin = (100 * gross_profit / r["revenue"]) if r["revenue"] else 0
        net_profit = gross_profit - r["transport"]
        net_margin = (100 * net_profit / r["revenue"]) if r["revenue"] else 0
        rows.append({
            "tier": name.upper(),
            "target_net_%": f"{mn*100:.2f}",
            "bid_₹/kg": f"{bid:.2f}",
            "lot_cost_₹": f"{lot_cost:,.0f}",
            "revenue_₹": f"{r['revenue']:,.0f}",
            "slit_cost_₹": f"{r['slit_cost']:,.0f}",
            "transport_₹": f"{r['transport']:,.0f}",
            "gross_profit_₹": f"{gross_profit:,.0f}",
            "gross_margin_%": f"{gross_margin:.2f}",
            "net_profit_₹": f"{net_profit:,.0f}",
            "net_margin_%": f"{net_margin:.2f}",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_cut_plan(r):
    lines = []
    for c in r["coils"]:
        bk = r["coil_break"].get(c["id"], {})
        disp = bk.get("disposition", "?")
        wt_kg = c["weight_g"] / 1000
        lines.append(
            f"{c['batch']}  ·  {c['width_cdmm']/eng.WIDTH_SCALE:g}mm  ·  "
            f"{wt_kg:.0f}kg  ·  {c['coating']}  ·  {disp}\n"
            f"    {bk.get('cut_pattern', '')}"
        )
    # newlines inside <div> get preserved by white-space: pre-wrap CSS
    body = ("\n\n").join(lines)
    st.html(f'<div class="bo-pattern">{body}</div>')


def _render_customer_split(r):
    rows = [{"customer": cust,
             "kg": f"{kg:,.0f}",
             "share": f"{100*kg/r['weight_kg']:.1f}%"}
            for cust, kg in sorted(r["by_cust"].items(), key=lambda x: -x[1])]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_quality_override(r):
    """Per-coil quality editor. Default 100% per coil; user discounts
    individual coils for rust / dent / age. Effective revenue scales
    proportionally and tier ceilings refresh. Year column is informational."""
    lot = r["lot"]
    coils = r["coils"]
    state = st.session_state.slopt_coil_quality.setdefault(lot, {})

    st.caption(
        "Discount individual coils for visible quality issues (rust, dent) "
        "or age. Quality defaults to 100%. Year is optional reference. "
        "Bid ceilings above refresh live. The cut plan is unchanged."
    )

    # Build rows from current state
    rows = []
    for c in coils:
        cid = c["id"]
        entry = state.get(cid, {})
        rows.append({
            "coil_id": cid,
            "batch": c["batch"],
            "width_mm": c["width_cdmm"] / eng.WIDTH_SCALE,
            "weight_kg": round(c["weight_g"] / 1000, 1),
            "grade": c["grade"],
            "coating": c["coating"],
            "year": entry.get("year"),
            "quality_%": float(entry.get("quality", 1.0)) * 100,
        })

    edited = st.data_editor(
        rows,
        column_config={
            "coil_id": None,   # hidden
            "batch": st.column_config.TextColumn("batch", disabled=True),
            "width_mm": st.column_config.NumberColumn("width (mm)",
                                                     disabled=True),
            "weight_kg": st.column_config.NumberColumn("weight (kg)",
                                                      disabled=True),
            "grade": st.column_config.TextColumn("grade", disabled=True),
            "coating": st.column_config.TextColumn("coating", disabled=True),
            "year": st.column_config.NumberColumn(
                "year (opt)", min_value=2015, max_value=2030,
                step=1, format="%d",
                help="Optional reference for the user. Doesn't auto-adjust "
                     "quality — set the quality column manually.",
            ),
            "quality_%": st.column_config.NumberColumn(
                "quality %", min_value=0.0, max_value=100.0, step=1.0,
                format="%.1f",
                help="Per-coil quality multiplier (0–100%). 100% = perfect. "
                     "Lowering this scales the coil's revenue contribution "
                     "and lowers all bid tiers proportionally.",
            ),
        },
        hide_index=True,
        use_container_width=True,
        key=f"slopt_quality_{lot}",
    )

    # Persist edits back to session_state.
    for row in edited:
        cid = row["coil_id"]
        q = float(row.get("quality_%") or 100) / 100
        y = row.get("year")
        prev = state.get(cid, {})
        if q != prev.get("quality", 1.0) or y != prev.get("year"):
            state[cid] = {"quality": q,
                          "year": int(y) if y is not None else None}


def _render_transport_override(r):
    """Per-lot transport-override inputs. Changing either value reruns the
    page, _enrich_record recomputes transport, and the tier ceilings refresh
    above. The cut plan is unchanged (optimizer never saw transport)."""
    lot = r["lot"]
    tx = r["transport_breakdown"]
    overrides = st.session_state.slopt_transport_overrides.setdefault(lot, {})
    st.caption(
        "Override the source-side transport for this lot below — the bid "
        "ceilings above refresh live. The cut plan is unchanged. Per-customer "
        "slitter→customer rates stay fixed (they don't depend on source)."
    )
    cols = st.columns(2)
    with cols[0]:
        new_kapson = st.number_input(
            f"Source → KAPSON (₹/kg) — {tx['kapson_kg']:,.0f} kg",
            min_value=0.0, max_value=20.0,
            value=float(overrides.get("kapson_rs_per_kg", 1.0)),
            step=0.1, key=f"slopt_kap_{lot}",
            help="Direct ship cost from this lot's source location to KAPSON. "
                 "Default ₹1/kg (Pune-near baseline).",
        )
        if new_kapson != overrides.get("kapson_rs_per_kg", 1.0):
            overrides["kapson_rs_per_kg"] = new_kapson
    with cols[1]:
        new_slitter = st.number_input(
            f"Source → OUR slitter (₹/kg) — {tx['slit_kg']:,.0f} kg",
            min_value=0.0, max_value=20.0,
            value=float(overrides.get("slitter_rs_per_kg", 0.0)),
            step=0.1, key=f"slopt_slt_{lot}",
            help="Cost to bring slit-bound material from source to OUR "
                 "slitter. Optional — defaults ₹0 (not previously counted).",
        )
        if new_slitter != overrides.get("slitter_rs_per_kg", 0.0):
            overrides["slitter_rs_per_kg"] = new_slitter
    # Breakdown table
    rows = []
    if tx["kapson_kg"] > 0:
        rows.append({"leg": "Source → KAPSON",
                     "kg": f"{tx['kapson_kg']:,.0f}",
                     "rate_₹/kg": f"{tx['kapson_rate']:.2f}",
                     "cost_₹": f"{tx['kapson_cost']:,.0f}"})
    if tx["slit_kg"] > 0:
        rows.append({"leg": "Source → OUR slitter",
                     "kg": f"{tx['slit_kg']:,.0f}",
                     "rate_₹/kg": f"{tx['slit_rate']:.2f}",
                     "cost_₹": f"{tx['slit_cost_source']:,.0f}"})
        rows.append({"leg": "Slitter → customers (fixed rates)",
                     "kg": f"{tx['slit_kg']:,.0f}",
                     "rate_₹/kg": "varies",
                     "cost_₹": f"{tx['cust_cost_slitter_to_customer']:,.0f}"})
    rows.append({"leg": "TOTAL transport",
                 "kg": f"{r['weight_kg']:,.0f}",
                 "rate_₹/kg": "—",
                 "cost_₹": f"{tx['total']:,.0f}"})
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_customer_fulfillment(records_summary, orders):
    if not records_summary:
        return
    st.html('<div class="bo-section-head">Customer fulfillment</div>')
    cust_to_lots = defaultdict(list)
    for r in records_summary:
        for cust, kg in r["by_cust"].items():
            cust_to_lots[cust].append((r["lot"], kg, r["bidable"]))
    for cust in sorted(cust_to_lots):
        rows = cust_to_lots[cust]
        total = sum(kg for _, kg, _ in rows)
        with st.expander(f"{cust} — {_fmt_kg(total)} across "
                         f"{len(rows)} lots"):
            st.dataframe(
                [{"lot": lot, "kg": f"{kg:,.0f}",
                  "status": "BID" if bidable else "SKIP"}
                 for lot, kg, bidable in sorted(rows)],
                use_container_width=True, hide_index=True,
            )


def _build_excel_blob(records, orders, customer_flags, auction_flags,
                      auction_name: str) -> bytes:
    """Assemble the data bundle measurement_report expects, then write the
    full multi-sheet workbook to a tmp file and return its bytes."""
    feas = [r for r in records if r["feasible"]]
    coils_all = [c for r in feas for c in r["coils"]]
    data = {
        "coils": coils_all,
        "orders": orders,
        "n_customers": len({o["customer"] for o in orders}),
        "lot_records": records,
        "auction_flags": auction_flags,
    }
    data["cust_lot_alloc"] = mr._customer_lot_alloc(data["lot_records"], orders)
    data["cust_totals"] = mr._customer_totals(data["cust_lot_alloc"], orders)
    data["min_qty_sim"] = mr._min_qty_sim(data["cust_lot_alloc"], "kg")
    data["min_qty_sim_cust"] = mr._min_qty_sim(data["cust_totals"], "total_kg")
    data["flags"] = mr._flags(data["lot_records"], data["coils"], orders,
                              data["auction_flags"], customer_flags)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        out_path = Path(f.name)
    try:
        mr.write_auction_workbook(auction_name, data, out_path)
        return out_path.read_bytes()
    finally:
        out_path.unlink(missing_ok=True)


def _excel_download_button(records, orders, customer_flags, auction_flags,
                           auction_name: str):
    blob = _build_excel_blob(records, orders, customer_flags, auction_flags,
                             auction_name)
    st.download_button(
        label="⬇ Download Excel report",
        data=blob,
        file_name=f"bid_optimizer_{auction_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=False,
    )


# ── Page sections ───────────────────────────────────────────────────────────

def _upload_section():
    st.html('<div class="bo-section-head">1 · Upload auction</div>')
    uploaded = st.file_uploader(
        "Auction Excel from Steelemart / JSW",
        type=["xlsx", "xls"],
        accept_multiple_files=False,
        help="Upload the per-lot/per-coil workbook the auction portal exports.",
    )
    if uploaded is not None and uploaded.name != st.session_state.slopt_uploaded_name:
        st.session_state.slopt_uploaded_name = uploaded.name
        st.session_state.slopt_auction_bytes = uploaded.read()
        st.session_state.slopt_lot_records = None
    if st.session_state.slopt_uploaded_name:
        st.caption(f"📁 {st.session_state.slopt_uploaded_name}  ·  "
                   f"{len(st.session_state.slopt_auction_bytes)/1024:.0f} KB")


def _solve_section(orders):
    st.html('<div class="bo-section-head">2 · Solve auction</div>')
    cols = st.columns([2, 1, 1])
    time_budget = cols[0].slider(
        "Per-lot time budget (seconds)",
        min_value=10, max_value=300, value=60, step=10,
        help="CP-SAT solve time limit per lot. Most lots finish in <2s; "
             "complex slit-heavy lots may need 60-180s.",
    )
    if cols[1].button("Solve auction", type="primary",
                      use_container_width=True,
                      disabled=st.session_state.slopt_auction_bytes is None):
        if _locked():
            return
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            f.write(st.session_state.slopt_auction_bytes)
            auction_path = Path(f.name)
        try:
            records = []
            with st.status("Solving auction…", expanded=True) as status:
                progress = st.progress(0.0)
                start_time = time.time()

                def _cb(lot, idx, total, rec):
                    # `idx` is 1-based; `rec is None` means this lot just
                    # STARTED, `rec is not None` means it just FINISHED.
                    completed = idx if rec is not None else idx - 1
                    remaining = total - completed
                    if rec is None:
                        st.write(f"▶ Solving lot {lot} ({idx}/{total})…")
                    elif rec.get("feasible"):
                        m = rec["metrics"]
                        st.write(
                            f"✓ Lot {lot} → max-bid ₹{m['max_bid']:.2f}/kg, "
                            f"{rec['solve_time_s']:.1f}s")
                    else:
                        st.write(f"✗ Lot {lot} → INFEASIBLE ({rec['status']})")
                    progress.progress(completed / max(total, 1))
                    # ETA: use observed avg if we have completed lots, otherwise
                    # the per-lot budget × remaining as the worst-case upper
                    # bound. Never goes below the current lot's remaining budget.
                    elapsed = time.time() - start_time
                    if completed > 0:
                        avg = elapsed / completed
                        eta = int(avg * remaining)
                    else:
                        eta = int(time_budget * remaining)
                    status.update(
                        label=f"Solving auction… {completed}/{total}  ·  "
                              f"~{eta}s remaining (upper bound)")

                records, auction_flags = _solve_auction(
                    auction_path, orders, _cb, time_budget)
                status.update(
                    label=f"✅ Solved {len(records)} lots in "
                          f"{time.time() - start_time:.0f}s",
                    state="complete")
            st.session_state.slopt_lot_records = records
            st.session_state.slopt_auction_flags = auction_flags
        except Exception as e:
            logger.exception("solve failed")
            st.error(f"Solve failed: {e}")
        finally:
            auction_path.unlink(missing_ok=True)
            st.session_state.slopt_solve_lock = 0.0
    if cols[2].button("Reset", use_container_width=True):
        _reset()
        st.rerun()


def _results_section(orders, customer_flags):
    records = st.session_state.slopt_lot_records
    if not records:
        return
    feasible = [r for r in records if r["feasible"]]
    overrides_all = st.session_state.slopt_transport_overrides
    quality_all = st.session_state.slopt_coil_quality
    enriched = [_enrich_record(r, orders,
                               overrides_all.get(r["lot"]),
                               quality_all.get(r["lot"]))
                for r in feasible]
    bidable = [r for r in enriched if r["bidable"]]
    skip = [r for r in enriched if not r["bidable"]]

    st.html('<div class="bo-section-head">3 · Results</div>')
    _render_header(enriched)
    _excel_download_button(
        records, orders, customer_flags,
        st.session_state.slopt_auction_flags or [],
        st.session_state.slopt_uploaded_name or "auction")

    if bidable:
        st.html('<div class="bo-section-head">Lots to bid</div>')
        for r in sorted(bidable, key=lambda x: -x["profit_primary"]):
            _render_lot_card(r)
            with st.expander(f"Details — Lot {r['lot']}"):
                t1, t2, t3, t4, t5 = st.tabs(["P&L by tier", "Cut plan",
                                              "Customer split",
                                              "Adjust transport ↻",
                                              "Adjust quality ↻"])
                with t1:
                    _render_pnl_table(r)
                with t2:
                    _render_cut_plan(r)
                with t3:
                    _render_customer_split(r)
                with t4:
                    _render_transport_override(r)
                with t5:
                    _render_quality_override(r)

    if skip:
        with st.expander(f"Lots to skip — {len(skip)}", expanded=False):
            for r in skip:
                _render_lot_card(r)

    _render_customer_fulfillment(enriched, orders)


# ── Entry point ─────────────────────────────────────────────────────────────

def render() -> None:
    _init_state()
    st.html(_CSS)
    st.html('<h1 class="bo-disp">Bid Optimizer</h1>')
    st.caption(
        "Upload an auction Excel · the engine solves each lot · per-lot cards "
        "show BID/SKIP with four tier ceilings (SAFE → CEILING) and "
        "expandable P&L / cut plan / customer split. Full Excel report "
        "downloadable from the header. The KAPSON whole-coil disposition, "
        "width-banded slitting (12 narrow / 19 wide), and transport-aware "
        "tiers are all live.")

    # Parse customer workbook once per session (cached factory below).
    orders, customer_flags = _load_orders()

    _upload_section()
    if st.session_state.slopt_auction_bytes is not None:
        _solve_section(orders)
    if st.session_state.slopt_lot_records:
        _results_section(orders, customer_flags)


@st.cache_data(show_spinner=False)
def _load_orders():
    """Parse the bundled customer workbook. Cached so we don't re-parse on
    every rerun. Returns (orders, flags)."""
    from app.repository import customer_repository as cr
    orders, flags = cr.parse_customers(str(_CUSTOMERS_PATH))
    if flags:
        logger.info("customer parse flags: %d", len(flags))
    return orders, flags
