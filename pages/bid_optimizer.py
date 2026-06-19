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
    Returns (records, auction_flags)."""
    import os as _os
    coils, auction_flags = ar.parse_auction(auction_path)
    by_lot: dict[str, list[dict]] = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)
    lots = sorted(by_lot)
    records = []
    for i, lot in enumerate(lots, start=1):
        status_cb(lot, i, len(lots), None)
        old = _os.environ.get("SLIT_TIME_LIMIT", "")
        _os.environ["SLIT_TIME_LIMIT"] = str(time_limit_s)
        try:
            rec = mr._build_lot_record(lot, by_lot[lot], orders, time_limit_s)
        finally:
            if old:
                _os.environ["SLIT_TIME_LIMIT"] = old
            else:
                _os.environ.pop("SLIT_TIME_LIMIT", None)
        records.append(rec)
        status_cb(lot, i, len(lots), rec)
    return records, auction_flags


def _enrich_record(rec, orders) -> dict:
    """Compute tier bids, transport, headroom, customer split. Returns a flat dict
    of UI-ready fields keyed off the lot record. Idempotent — safe to re-call."""
    if not rec["feasible"]:
        return {"feasible": False, "lot": rec["lot"], "status": rec["status"]}
    m = rec["metrics"]
    coils = rec["coils"]
    weight = m["total_wt"]
    revenue = m["total_rev"]
    slit_cost = rec.get("slit_cost_rs", 0.0)
    start = coils[0]["price_per_kg"] if coils else 0.0
    # transport via the existing measurement-report helper (auction-wide bracket
    # attribution requires per-customer totals; we approximate per-lot using the
    # lot's own customer totals here for the UI — same as Excel).
    cust_totals = defaultdict(float)
    for oid, kg in rec.get("cust_alloc_kg", {}).items():
        cust = next(o["customer"] for o in orders if o["id"] == oid)
        cust_totals[cust] += kg
    transport = mr._lot_transport_cost(rec, orders, dict(cust_totals))
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
        "revenue": revenue, "slit_cost": slit_cost, "transport": transport,
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
    html = f"""
<div class="bo-card {status} bo-root">
  <div class="bo-card-head">
    <span class="bo-lot-no">LOT {r['lot']}</span>
    <span class="bo-status {status}">{'BID' if r['bidable'] else 'SKIP'}</span>
    <span class="bo-meta">{_fmt_t(r['weight_kg'])} · {r['n_coils']} coils · start ₹{r['start']:.2f}/kg · {coat_str}</span>
  </div>
  <div class="bo-grid">
    <div class="bo-spec">
      <div class="bo-mini-label">Headroom @ {r['primary_name']}</div>
      <div class="bo-mono" style="color:{headroom_color}; font-size:18px; font-weight:600; margin:2px 0 14px">
        {'+' if r['headroom']>=0 else ''}₹{r['headroom']:.2f} / kg
      </div>
      <div class="bo-mini-label">Profit @ {r['primary_name']}</div>
      <div class="bo-mono" style="font-size:16px; font-weight:600; margin:2px 0 14px">{_fmt_rs(r['profit_primary'])}</div>
      <div class="bo-mini-label">Margin (net / gross)</div>
      <div class="bo-mono" style="margin:2px 0 14px">{r['margin_net']:.2f}% / {r['margin_gross']:.2f}%</div>
      <div class="bo-mini-label">Transport %</div>
      <div class="bo-mono" style="margin:2px 0 14px">{r['transport_pct']:.2f}%</div>
      {f'<div style="margin-top:8px">{flags_html}</div>' if flags_html else ''}
    </div>
    <div>
      <div class="bo-mini-label" style="margin-bottom:6px">Bid tiers (post-transport net)</div>
      <table class="bo-tier-table">{"".join(tier_rows)}</table>
    </div>
  </div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


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
    st.markdown(f'<div class="bo-pattern">' + "\n\n".join(lines) + "</div>",
                unsafe_allow_html=True)


def _render_customer_split(r):
    rows = [{"customer": cust,
             "kg": f"{kg:,.0f}",
             "share": f"{100*kg/r['weight_kg']:.1f}%"}
            for cust, kg in sorted(r["by_cust"].items(), key=lambda x: -x[1])]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_customer_fulfillment(records_summary, orders):
    if not records_summary:
        return
    st.markdown('<div class="bo-section-head">Customer fulfillment</div>',
                unsafe_allow_html=True)
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
    st.markdown('<div class="bo-section-head">1 · Upload auction</div>',
                unsafe_allow_html=True)
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
    st.markdown('<div class="bo-section-head">2 · Solve auction</div>',
                unsafe_allow_html=True)
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
                    if rec is None:
                        st.write(f"▶ Solving lot {lot} ({idx}/{total})…")
                    elif rec.get("feasible"):
                        m = rec["metrics"]
                        st.write(
                            f"✓ Lot {lot} → max-bid ₹{m['max_bid']:.2f}/kg, "
                            f"{rec['solve_time_s']:.1f}s")
                    else:
                        st.write(f"✗ Lot {lot} → INFEASIBLE ({rec['status']})")
                    progress.progress(idx / max(total, 1))
                    elapsed = time.time() - start_time
                    eta = (elapsed / idx) * (total - idx) if idx else 0
                    status.update(
                        label=f"Solving auction… {idx}/{total}  ·  "
                              f"~{eta:.0f}s remaining")

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
    enriched = [_enrich_record(r, orders) for r in feasible]
    bidable = [r for r in enriched if r["bidable"]]
    skip = [r for r in enriched if not r["bidable"]]

    st.markdown('<div class="bo-section-head">3 · Results</div>',
                unsafe_allow_html=True)
    _render_header(enriched)
    _excel_download_button(
        records, orders, customer_flags,
        st.session_state.slopt_auction_flags or [],
        st.session_state.slopt_uploaded_name or "auction")

    if bidable:
        st.markdown('<div class="bo-section-head">Lots to bid</div>',
                    unsafe_allow_html=True)
        for r in sorted(bidable, key=lambda x: -x["profit_primary"]):
            _render_lot_card(r)
            with st.expander(f"Details — Lot {r['lot']}"):
                t1, t2, t3 = st.tabs(["P&L by tier", "Cut plan",
                                       "Customer split"])
                with t1:
                    _render_pnl_table(r)
                with t2:
                    _render_cut_plan(r)
                with t3:
                    _render_customer_split(r)

    if skip:
        with st.expander(f"Lots to skip — {len(skip)}", expanded=False):
            for r in skip:
                _render_lot_card(r)

    _render_customer_fulfillment(enriched, orders)


# ── Entry point ─────────────────────────────────────────────────────────────

def render() -> None:
    _init_state()
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown('<h1 class="bo-disp">Bid Optimizer</h1>',
                unsafe_allow_html=True)
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
