"""
Validation harness for prototype_slitting_incremental.

Proves the incremental re-pricer is CORRECT before any UI / restructuring work.

Two layers:
  1. SYNTHETIC FIXTURES — tiny, solve in ms, PROVEN OPTIMAL, every number
     hand-computed and asserted exactly. This is the rigorous proof of the
     wrapper logic itself, independent of solver scale.
  2. REAL-DATA SMOKE — the always-true invariants (conservation, no-oversell)
     on every real lot; the optimal-only invariants (monotonicity, oracle)
     gated on status==OPTIMAL, else reported "indeterminate (time-limited)".

Hard invariants
  R  Reduction    : first lot priced (no prior wins) == its standalone price.
  C  Conservation : after a WIN, total remaining demand drops by EXACTLY the
                     lot's consumed grams (cust [+inv]).
  N  No-oversell   : customer-delivered qty for any order, summed over won
                     lots, never exceeds its original demand.
  M  Monotonicity  : a lot priced after winning an overlapping prior lot has
                     model objective <= its standalone objective. Incremental
                     can NEVER price a lot above per-lot-independent.
  O  Oracle        : sum of sequential objectives <= joint optimum over the
                     same coils vs full demand (greedy cannot beat the joint
                     solve; incremental > joint would prove a double-count).
  F  Flag-inert    : under per-order consumption the include_inventory flag is
                     a no-op (inv>0 only after cust hit demand cap). Documents
                     that the only real axis is per-order vs shared-stock-pool
                     (a deliberately deferred v2).

Run:
    conda activate slitting_opt
    python validate_incremental.py
    SLIT_TIME_LIMIT=20 python validate_incremental.py   # quick gate
"""

import sys
import os
import io
import math
import contextlib
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

from ortools.sat.python import cp_model

from engine import optimizer as item
from engine import incremental as inc

WS = item.WIDTH_SCALE
MT = item.MT_TO_GRAMS
SCRAP_RATE = item.SCRAP_RATE

# Sweep only checks conservation/no-oversell (true at ANY feasible solution),
# so it runs cheap & sequential. The rigorous bound-based block runs at a
# bigger budget, but its independent heavy solves go in a process pool.
SWEEP_BUDGET_S = 20
RIGOR_BUDGET_S = int(os.environ.get("SLIT_TIME_LIMIT", 120))

_results = []


def _smoke_worker(p):
    """Top-level (picklable) pool worker. Returns only plain metrics dicts —
    CP-SAT objects never cross the process boundary. Worker processes re-import
    prototype_slitting_optimizer, which reads SLIT_TIME_LIMIT from the env the
    parent set before the pool was created (= RIGOR_BUDGET_S)."""
    kind, label, data, orders, nw = p
    with contextlib.redirect_stdout(io.StringIO()):
        if kind == "sa":
            _, _, m = inc.price_lot(label, data, orders, n_workers=nw)
            return (f"sa:{label}", m)
        if kind == "seq":
            a, b = label
            ca, cb = data
            tr = inc.run_sequence({a: ca, b: cb}, [a, b],
                                  {a: "won", b: "won"}, orders,
                                  n_workers=nw, verbose=False)
            return ("seq", [tr[0][1], tr[1][1]])
        a, b = label                       # kind == "joint"
        ca, cb = data
        _, _, mj = inc.joint_solve(ca + cb, orders, n_workers=nw)
        return ("joint", mj)


def _fin(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def _le(x, y):
    """x <= y, with a tolerance scaled to these ~1e8 integer objectives."""
    return x <= y + max(1.0, 1e-6 * max(abs(x), abs(y)))


def check(name, ok, detail=""):
    _results.append((name, bool(ok)))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  --  {detail}" if detail else ""))
    return ok


def close(a, b, tol=1.0):
    return abs(a - b) <= tol


# ---------------------------------------------------------------- builders ---
def coil(lot, w_mm, mt, price_kg, g="G", co="C5L", th=0.5, batch="B"):
    return {
        "id": 0, "lot": lot, "batch": batch,
        "width_cdmm": int(round(w_mm * WS)),
        "weight_g": int(round(mt * MT)),
        "price_per_kg": float(price_kg),
        "grade": g, "coating": co, "thickness": item._thk(th),
    }


def order(oid, cust, w_mm, mt, rate, g="G", co="C5L", th=0.5, min_kg=0):
    return {
        "id": oid, "customer": cust,
        "width_cdmm": int(round(w_mm * WS)),
        "qty_g": int(round(mt * MT)),
        "monthly_g": int(round(mt * MT)),  # mirror load_customers()
        "rate_per_kg": int(round(rate)),
        "grades": {g}, "coatings": {co}, "thicknesses": {item._thk(th)},
        "min_coil_g": int(round(min_kg * 1000)),
    }


def standalone(lot, lot_coils, orders):
    _, _, m = inc.price_lot(lot, lot_coils, orders)
    return m


# ---------------------------------------------------- FIXTURE A (exact) ------
def fixture_A():
    """Two identical 100mm / 1 MT coils as separate lots; ONE 100mm / 1 MT
    order @ rs80; coil cost rs50/kg; as-is (width==width).

    Hand maths (rs):
      standalone each lot : cust 80,000 - cost 50,000 = profit 30,000
                            max-bid = 80,000*0.92/1000 = 73.60/kg
      per-lot-independent sum = 60,000        <-- the overstatement
      incremental L1(won)->L2(won):
        L1 = 30,000 (cust), consumes O1 cust 1,000,000 g
        L2 vs remaining(=0): as-is -> ALL inventory @ 76 (=80*95//100)
             inv 76,000 - cost 50,000 = profit 26,000
             max-bid = 76,000*0.92/1000 = 69.92/kg
      incremental sum = 56,000   joint over both coils vs full O1 = 56,000
      the 4,000 gap vs independent = 1000 kg * (80-76) = corrected leak
    """
    print("\n--- FIXTURE A: identical coils, single order (exact numbers) ---")
    by_lot = {"L1": [coil("L1", 100, 1, 50, batch="A1")],
              "L2": [coil("L2", 100, 1, 50, batch="A2")]}
    O = [order(0, "Acme", 100, 1, 80)]

    sa1 = standalone("L1", by_lot["L1"], O)
    sa2 = standalone("L2", by_lot["L2"], O)
    check("A: standalone L1 PROVEN OPTIMAL", sa1["optimal"], sa1["status"])
    check("A: standalone L1 profit == 30,000",
          close(sa1["profit"], 30_000), f"{sa1['profit']:,.0f}")
    check("A: standalone L1 max-bid == 73.60",
          close(sa1["max_bid"], 73.60, 0.01), f"{sa1['max_bid']:.2f}")
    # T (usefulness): the model returns a TIGHT max-bid (proven optimal,
    # well above the rs50 coil cost), not a safe-but-useless floor. A
    # degenerate "bid <= starting price" model would FAIL this.
    check("A:T useful — max-bid 73.60 > coil cost 50 (real headroom)",
          sa1["optimal"] and sa1["max_bid"] > 51.0,
          f"headroom rs{sa1['max_bid'] - 50:.2f}/kg over cost")
    indep_sum = sa1["profit"] + sa2["profit"]
    check("A: per-lot-independent sum == 60,000 (the overstatement)",
          close(indep_sum, 60_000), f"{indep_sum:,.0f}")

    trail = inc.run_sequence(by_lot, ["L1", "L2"], {"L1": "won", "L2": "won"},
                             O, include_inventory=True, verbose=False)
    (_, m1, _, rem1), (_, m2, _, rem2) = trail

    # R: first lot, no prior wins, == standalone
    check("A:R first lot == standalone (obj)",
          m1["optimal"] and close(m1["obj"], sa1["obj"], 1.0),
          f"{m1['obj']:.0f} vs {sa1['obj']:.0f}")
    check("A: L1 incremental profit == 30,000",
          close(m1["profit"], 30_000), f"{m1['profit']:,.0f}")
    # C: conservation — O1 fully consumed by L1, remaining demand 0 kg
    check("A:C remaining demand after L1 won == 0 kg",
          close(rem1, 0.0, 1e-6), f"{rem1} kg")
    check("A: L1 consumed O1 cust == 1,000,000 g",
          m1["cust"].get(0, -1) == 1_000_000, str(m1["cust"]))
    # L2 vs zero demand -> all inventory
    check("A: L2 incremental profit == 26,000",
          close(m2["profit"], 26_000), f"{m2['profit']:,.0f}")
    check("A: L2 incremental max-bid == 69.92",
          close(m2["max_bid"], 69.92, 0.01), f"{m2['max_bid']:.2f}")
    check("A: L2 routed ALL to inventory (cust 0, inv 1,000,000)",
          m2["cust"].get(0, -1) == 0 and m2["inv"].get(0, -1) == 1_000_000,
          f"cust={m2['cust']} inv={m2['inv']}")
    # M: monotonicity vs standalone L2
    check("A:M L2 incremental obj <= standalone L2 obj",
          m2["optimal"] and sa2["optimal"] and m2["obj"] <= sa2["obj"] + 1.0,
          f"{m2['obj']:.0f} <= {sa2['obj']:.0f}")
    inc_sum = m1["profit"] + m2["profit"]
    check("A: incremental sum == 56,000 (leak corrected by 4,000)",
          close(inc_sum, 56_000), f"{inc_sum:,.0f}")
    # N: no-oversell
    total_cust = m1["cust"].get(0, 0) + m2["cust"].get(0, 0)
    check("A:N total cust to O1 (1,000,000) <= demand (1,000,000)",
          total_cust <= 1_000_000, f"{total_cust:,} g")
    # O: oracle — joint over both coils vs full demand
    _, _, mj = inc.joint_solve(by_lot["L1"] + by_lot["L2"], O)
    check("A:O joint PROVEN OPTIMAL", mj["optimal"], mj["status"])
    check("A:O incremental obj-sum <= joint obj",
          mj["optimal"] and (m1["obj"] + m2["obj"]) <= mj["obj"] + 1.0,
          f"sum={m1['obj']+m2['obj']:.0f} joint={mj['obj']:.0f}")
    check("A:O joint profit == 56,000", close(mj["profit"], 56_000),
          f"{mj['profit']:,.0f}")

    # F: include_inventory flag is inert under per-order consumption
    trail_ci = inc.run_sequence(by_lot, ["L1", "L2"],
                                {"L1": "won", "L2": "won"}, O,
                                include_inventory=False, verbose=False)
    same = close(trail_ci[1][1]["profit"], m2["profit"], 1.0)
    check("A:F include_inventory flag inert (cust-only == cust+inv)", same,
          f"cust-only L2 profit {trail_ci[1][1]['profit']:,.0f}")


# -------------------------------------- FIXTURE B (slit, two orders) --------
def fixture_B():
    """L1 = 203mm/1 MT (slits to 2x100mm + 3mm edge). L2 = 100mm/1 MT as-is.
    Orders: O_hi 100mm@rs100 (lucrative), O_lo 150mm@rs50. Coil cost rs30/kg.
    Relational invariants only (rounding makes exact hand maths brittle)."""
    print("\n--- FIXTURE B: slit mode + two orders (relational) ---")
    by_lot = {"L1": [coil("L1", 203, 1, 30, batch="B1")],
              "L2": [coil("L2", 100, 1, 30, batch="B2")]}
    O = [order(0, "Hi", 100, 1, 100), order(1, "Lo", 150, 1, 50)]

    sa1 = standalone("L1", by_lot["L1"], O)
    sa2 = standalone("L2", by_lot["L2"], O)
    trail = inc.run_sequence(by_lot, ["L1", "L2"], {"L1": "won", "L2": "won"},
                             O, include_inventory=True, verbose=False)
    (_, m1, _, rem1), (_, m2, _, rem2) = trail

    check("B:R first lot == standalone (obj)",
          m1["optimal"] and sa1["optimal"] and close(m1["obj"], sa1["obj"], 1),
          f"{m1['obj']:.0f} vs {sa1['obj']:.0f}")
    # C: remaining drop == consumed grams of L1
    base = sum(o["qty_g"] for o in O) / 1000
    consumed1 = sum(m1["cust"].get(o["id"], 0) + m1["inv"].get(o["id"], 0)
                    for o in O) / 1000
    check("B:C remaining == base - consumed(L1)",
          close(rem1, max(0.0, base - consumed1), 1.0),
          f"rem {rem1:,.0f} = base {base:,.0f} - used {consumed1:,.0f}")
    # N: per-order no-oversell
    ok_n = all(m1["cust"].get(o["id"], 0) + m2["cust"].get(o["id"], 0)
               <= o["qty_g"] for o in O)
    check("B:N no order over-sold to customers", ok_n)
    # M: both later lots <= their standalone
    check("B:M L2 incremental obj <= standalone L2 obj",
          m2["optimal"] and sa2["optimal"] and m2["obj"] <= sa2["obj"] + 1.0,
          f"{m2['obj']:.0f} <= {sa2['obj']:.0f}")
    # O: oracle
    _, _, mj = inc.joint_solve(by_lot["L1"] + by_lot["L2"], O)
    gap = mj["obj"] - (m1["obj"] + m2["obj"])
    check("B:O incremental obj-sum <= joint obj",
          mj["optimal"] and (m1["obj"] + m2["obj"]) <= mj["obj"] + 1.0,
          f"joint-greedy gap {gap:.0f} (>=0 expected)")


# ---------------------------------- FIXTURE C (tiered holding, exact) -------
def fixture_C():
    """One 100mm / 3 MT coil @ rs50/kg, as-is, vs ONE 100mm order whose
    MONTHLY demand is 1 MT @ rs80/kg.

      cust  : 1 MT @ rs80              = 80,000
      inv m1: 1 MT @ rs76 (80*95//100) = 76,000
      inv m2: 1 MT @ rs72 (80*90//100) = 72,000
      revenue 228,000 - cost (50*3000) 150,000 = profit 78,000
      (the OLD flat-95 model would have said 82,000 — the 4,000 drop is
       the 2nd month correctly valued at 90% not 95%.)
    Also pins the slice-coefficient ladder and the scrap-floor tail."""
    print("\n--- FIXTURE C: tiered holding, multi-month overproduction ---")

    coefs = item.inv_slice_coefs(80)
    check("C: slice ladder for rs80 == [76,72,68,64,60,56,52,48,44,40,36]",
          coefs == [76, 72, 68, 64, 60, 56, 52, 48, 44, 40, 36], str(coefs))

    by_lot = {"L1": [coil("L1", 100, 3, 50, batch="C1")]}
    O = [order(0, "Mono", 100, 1, 80)]
    lot_coils, res, m = inc.price_lot("L1", by_lot["L1"], O)

    check("C: PROVEN OPTIMAL", m["optimal"], m["status"])
    check("C: profit == 78,000 (tiered, not flat-95's 82,000)",
          close(m["profit"], 78_000), f"{m['profit']:,.0f}")
    check("C:T useful — max-bid > coil cost 50 (headroom, not a floor)",
          m["optimal"] and m["max_bid"] > 51.0,
          f"max-bid rs{m['max_bid']:.2f}, headroom rs{m['max_bid'] - 50:.2f}")
    check("C: customer got 1,000,000 g", m["cust"].get(0, -1) == 1_000_000,
          str(m["cust"]))
    sl = res["inv_slices"][0]
    sv = [res["solver"].Value(v) for _, v in sl]
    check("C: month-1 slice == 1,000,000 g @ rs76",
          sl[0][0] == 76 and sv[0] == 1_000_000, f"coef={sl[0][0]} g={sv[0]}")
    check("C: month-2 slice == 1,000,000 g @ rs72",
          sl[1][0] == 72 and sv[1] == 1_000_000, f"coef={sl[1][0]} g={sv[1]}")
    check("C: deeper slices + scrap tail all empty",
          all(x == 0 for x in sv[2:]) and sl[-1][0] == SCRAP_RATE,
          f"tail_coef={sl[-1][0]} rest={sv[2:]}")

    # Scrap-floor: 13 MT coil, 1 MT monthly demand -> 12 MT inventory; the
    # 11 priced months fill, the 12th MT lands in the rs34 scrap tail.
    by_lot2 = {"L1": [coil("L1", 100, 13, 50, batch="C2")]}
    _, res2, _ = inc.price_lot("L1", by_lot2["L1"], O)
    sl2 = res2["inv_slices"][0]
    sv2 = [res2["solver"].Value(v) for _, v in sl2]
    check("C: scrap-floor tail absorbs the 12th month (1,000,000 g @ rs34)",
          sl2[-1][0] == SCRAP_RATE and sv2[-1] == 1_000_000
          and all(x == 1_000_000 for x in sv2[:-1]),
          f"tail={sv2[-1]} priced={sv2[:-1]}")


# --------------------------------- env scoping helper for D/E fixtures -----
import contextlib  # noqa: E402  (kept local to the fixtures below)


@contextlib.contextmanager
def _env(**overrides):
    """Set env vars for the duration of a `with` block, then restore.
    The engine's band/salvage accessors read os.environ at solve-call time,
    so this is enough to test in-process."""
    old = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ------------------------------------ FIXTURE D (width-banded, exact) -------
def fixture_D():
    """Narrow band (≤650mm): knife 12, edge 3 mm, slit ₹2.5/kg.
       Wide   band (>650mm): knife 19, edge 5 mm, slit ₹1.3/kg.

    D-narrow: 500mm/1MT @ ₹50, single 100mm order @ ₹80 (demand 5MT).
      max strips = min(knife 12, 500/100=5) = 5; edge ≥3 forces y≥3mm,
      so 5 strips (y=0) infeasible -> 4 strips, y=100mm.
      cust = 4×200,000g @₹80 = ₹64,000 ; scrap g=20×10000 = 200kg @₹34 = ₹6,800
      slit cost = ₹2.5/kg × 1000kg = ₹2,500 ; lot ₹50,000
      profit = 64,000 + 6,800 − 50,000 − 2,500 = 18,300

    D-wide: 1000mm/1MT @ ₹50, single 50mm order @ ₹80 (demand 5MT).
      max strips = min(knife 19, 1000/50=20) = 19; edge ≥5 forces y≥5mm,
      19 strips → y=50mm OK.
      cust = 19×50,000g @₹80 = ₹76,000 ; scrap g=10×5000 = 50kg @₹34 = ₹1,700
      slit cost = ₹1.3/kg × 1000kg = ₹1,300 ; lot ₹50,000
      profit = 76,000 + 1,700 − 50,000 − 1,300 = 26,400
    """
    print("\n--- FIXTURE D: width-banded params (narrow + wide, exact) ---")
    with _env(SLIT_BAND_MM=650,
              SLIT_SLITTING_COST="2.5",
              SLIT_KNIFE_MAX_WIDE=19,
              SLIT_EDGE_TRIM_MM_WIDE=5,
              SLIT_SLITTING_COST_WIDE="1.3"):
        # narrow
        cn = [coil("Dn", 500, 1, 50, batch="DN1")]
        On = [order(0, "Cn", 100, 5, 80)]
        _, _, mn = inc.price_lot("Dn", cn, On)
        check("D-narrow PROVEN OPTIMAL", mn["optimal"], mn["status"])
        check("D-narrow profit == 18,300 (knife 12, edge 3, slit ₹2.5/kg)",
              close(mn["profit"], 18_300), f"{mn['profit']:,.0f}")
        # wide
        cw = [coil("Dw", 1000, 1, 50, batch="DW1")]
        Ow = [order(0, "Cw", 50, 5, 80)]
        _, _, mw = inc.price_lot("Dw", cw, Ow)
        check("D-wide   PROVEN OPTIMAL", mw["optimal"], mw["status"])
        check("D-wide   profit == 26,400 (knife 19, edge 5, slit ₹1.3/kg)",
              close(mw["profit"], 26_400), f"{mw['profit']:,.0f}")


# ----------------------------------------- FIXTURE E (salvage, exact) -------
def fixture_E():
    """Per-coating salvage at lot_start − delta. C6L coil, no real customer.
      coil 100mm/1MT @ ₹50, coating C6L; only order coats C5L (no match).

      NO salvage env (default): coil forced to slit (no width match → as-is=0)
        y = 100mm (full), scrap=full = ₹34×1000 = ₹34,000 rev
        slit cost ₹4/kg × 1000 = ₹4,000 ; lot ₹50,000
        profit = 34,000 − 50,000 − 4,000 = −20,000

      With SLIT_SALVAGE='C6L:2': salvage chosen
        rev = (50 − 2) × 1000 = ₹48,000 ; slit cost 0 ; scrap 0
        profit = 48,000 − 50,000 = −2,000      (salvage > scrap path)

      With a real C6L customer @ ₹200/kg as-is match: customer wins
        cust = 200 × 1000 = ₹200,000 ; profit = 200,000 − 50,000 = 150,000
    """
    print("\n--- FIXTURE E: per-coating salvage (exact) ---")

    # E-base: no-salvage default — confirms regression (validated behaviour)
    c_e = [coil("E1", 100, 1, 50, co="C6L", batch="E1")]
    o_x = [order(0, "X", 100, 1, 80, co="C5L")]   # mismatched coating
    _, _, m0 = inc.price_lot("E1", c_e, o_x)
    check("E:no-salvage default: profit == −20,000 (all-scrap fallback)",
          m0["optimal"] and close(m0["profit"], -20_000),
          f"{m0['profit']:,.0f}")

    # E-salvage chosen (salvage > scrap)
    with _env(SLIT_SALVAGE="C6L:2"):
        _, rs, ms = inc.price_lot("E1", c_e, o_x)
        check("E:salvage map parses to {'C6L': 2.0}",
              rs["salv_map"] == {"C6L": 2.0}, str(rs["salv_map"]))
        check("E:salvage CHOSEN (slit=0, as_is=0, salvage=1)",
              rs["solver"].Value(rs["salvage"][0]) == 1
              and rs["solver"].Value(rs["slit"][0]) == 0
              and rs["solver"].Value(rs["as_is"][0]) == 0)
        check("E:salvage profit == −2,000 (= (50−2)×1000 − 50,000)",
              ms["optimal"] and close(ms["profit"], -2_000),
              f"{ms['profit']:,.0f}")
        check("E:salvage consumes ZERO customer demand (N untouched)",
              all(v == 0 for v in ms["cust"].values()),
              str(ms["cust"]))

        # customer beats salvage
        o_p = [order(0, "P", 100, 1, 200, co="C6L")]   # 100mm matches as-is
        _, rp, mp = inc.price_lot("E1", c_e, o_p)
        check("E:customer beats salvage (as_is=1, salvage=0)",
              rp["solver"].Value(rp["as_is"][0]) == 1
              and rp["solver"].Value(rp["salvage"][0]) == 0)
        check("E:customer profit == 150,000 (200×1000 − 50,000)",
              mp["optimal"] and close(mp["profit"], 150_000),
              f"{mp['profit']:,.0f}")

        # safeguard flag fires when a customer order lists a salvage coating
        old_raw = os.environ.get("SLIT_SALVAGE", "")
        try:
            os.environ["SLIT_SALVAGE"] = "C6L:2"
            flags = item.salvage_safeguard_flags(o_p)
            check("E:safeguard flag fires for customer listing C6L",
                  len(flags) == 1 and "C6L" in flags[0],
                  flags[0] if flags else "(no flag)")
        finally:
            if old_raw:
                os.environ["SLIT_SALVAGE"] = old_raw
            else:
                os.environ.pop("SLIT_SALVAGE", None)


# ----------------------------------------------------- REAL-DATA SMOKE ------
def real_smoke():
    print(f"\n--- REAL-DATA SMOKE (sweep {SWEEP_BUDGET_S}s/solve seq; "
          f"rigor {RIGOR_BUDGET_S}s/solve parallel) ---")
    coils = item.load_auction(item.AUCTION_CSV)
    orders = item.load_customers(item.CUSTOMER_CSV)
    by_lot = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)
    lots = sorted(by_lot, key=lambda L: len(by_lot[L]))  # smallest first

    # ---- Always-true invariants: full all-won sweep, cheap & SEQUENTIAL.
    # The sweep is intrinsically ordered (lot k priced vs demand left after
    # k-1 won) so it cannot be parallelised; but C/N hold at ANY feasible
    # solution, so a short budget is fine.
    item.SOLVE_TIME_LIMIT_S = SWEEP_BUDGET_S
    base_total = sum(o["qty_g"] for o in orders)
    remaining = [dict(o) for o in orders]
    cum_cust = defaultdict(int)
    prev_total = base_total
    cons_ok = nos_ok = True
    for lot in lots:
        _, res, m = inc.price_lot(lot, by_lot[lot], remaining)
        if not m["feasible"]:
            check(f"smoke {lot}: feasible", False, m["status"])
            continue
        consumed = sum(m["cust"].get(o["id"], 0) + m["inv"].get(o["id"], 0)
                       for o in remaining)
        remaining = inc.consume(remaining, res, include_inventory=True)
        new_total = sum(o["qty_g"] for o in remaining)
        if not (0 <= prev_total - new_total <= consumed + 1):
            cons_ok = False
        prev_total = new_total
        for o in orders:
            cum_cust[o["id"]] += m["cust"].get(o["id"], 0)
        print(f"    {lot}: {m['status']:<10} max-bid rs{m['max_bid']:,.2f}/kg "
              f"profit rs{m['profit']:,.0f}  remaining {new_total/1000:,.0f} kg")
    for o in orders:
        if cum_cust[o["id"]] > o["qty_g"] + 1:
            nos_ok = False
    check("smoke:C conservation holds across full all-won sweep", cons_ok)
    check("smoke:N no order over-sold across full all-won sweep", nos_ok)

    # ---- Rigorous bound-based R/M/O on the two most DEMAND-HEAVY lots, so
    # monotonicity (M) is stress-tested on a real master priced AFTER winning
    # an overlapping master — not the trivial scrap lot. Engagement score =
    # # of (coil, compatible-order) pairs; scrap lots score ~0 and drop out.
    # Bound-based so valid even when masters never prove OPTIMAL. The four
    # heavy solves are independent -> process pool.
    eng = {L: sum(1 for c in by_lot[L] for o in orders if item.compat(c, o))
           for L in by_lot}
    a, b = sorted(by_lot, key=lambda L: eng[L], reverse=True)[:2]
    cores = os.cpu_count() or 4
    usable = max(1, cores - 1)
    par = min(4, max(1, usable))
    nw = min(8, max(1, usable // par))
    print(f"  rigor block: won={a} (eng {eng[a]}), M-stress={b} "
          f"(eng {eng[b]})  ({par} parallel x {nw} threads)")

    payloads = [
        ("sa", a, by_lot[a], orders, nw),
        ("sa", b, by_lot[b], orders, nw),
        ("seq", (a, b), (by_lot[a], by_lot[b]), orders, nw),
        ("joint", (a, b), (by_lot[a], by_lot[b]), orders, nw),
    ]
    # children inherit env at spawn -> they read this as their solve budget
    os.environ["SLIT_TIME_LIMIT"] = str(RIGOR_BUDGET_S)
    with ProcessPoolExecutor(max_workers=par) as ex:
        rmap = dict(ex.map(_smoke_worker, payloads))
    sa_a, sa_b = rmap[f"sa:{a}"], rmap[f"sa:{b}"]
    m_a, m_b = rmap["seq"]
    mj = rmap["joint"]

    if not all(d["feasible"] for d in (sa_a, sa_b, m_a, m_b, mj)):
        check("smoke: all rigor solves feasible", False,
              "a solve returned no solution — raise SLIT_TIME_LIMIT")
        return

    for tag, d in (("sa " + a, sa_a), ("sa " + b, sa_b),
                   ("seq[0]", m_a), ("seq[1]", m_b), ("joint", mj)):
        g = d.get("gap_pct")
        print(f"    {tag:<8} obj={d['obj']:,.0f} bound={d['bound']:,.0f}"
              f"  gap={g:.2f}%" if g is not None else f"    {tag}")

    # T (usefulness, budget-INDEPENDENT): on a demand-heavy master the chosen
    # plan must extract real customer value far above the scrap-everything
    # floor. A safe-but-useless "bid the floor / scrap all" model has
    # total_rev == scrap-only and FAILS this regardless of solve budget,
    # so it complements the one-sided safety checks R/M/O.
    scrap_only = SCRAP_RATE * sa_a["total_wt"]          # rs if all scrapped
    start_a = by_lot[a][0]["price_per_kg"]
    print(f"    T {a}: plan revenue rs{sa_a['total_rev']:,.0f} vs scrap-only "
          f"rs{scrap_only:,.0f};  max-bid rs{sa_a['max_bid']:,.2f} vs "
          f"start rs{start_a:,.2f}/kg")
    check(f"smoke:T {a} plan revenue >> scrap-only floor (useful, not a "
          f"degenerate floor-bid)",
          _fin(sa_a["total_rev"]) and sa_a["total_rev"] > 1.5 * scrap_only,
          f"{sa_a['total_rev']:,.0f} > 1.5 x {scrap_only:,.0f}")

    # R: first lot (no prior wins) and standalone solve the SAME problem ->
    # their [obj, bound] intervals must overlap (both bracket one optimum).
    okR = (_fin(m_a["obj"]) and _fin(m_a["bound"]) and _fin(sa_a["obj"])
           and _fin(sa_a["bound"])
           and _le(m_a["obj"], sa_a["bound"]) and _le(sa_a["obj"], m_a["bound"]))
    check(f"smoke:R {a} first-lot interval overlaps standalone (bound-based)",
          okR, f"incr[{m_a['obj']:,.0f},{m_a['bound']:,.0f}] "
               f"sa[{sa_a['obj']:,.0f},{sa_a['bound']:,.0f}]")

    # informational: the no-overbid effect on this real master lot
    if _fin(sa_b.get("max_bid")) and _fin(m_b.get("max_bid")):
        d = sa_b["max_bid"] - m_b["max_bid"]
        print(f"    M-stress {b}: standalone max-bid rs{sa_b['max_bid']:,.2f}"
              f" -> incremental rs{m_b['max_bid']:,.2f} after winning {a}"
              f"  (no-overbid drop rs{d:,.2f})")

    # M: incremental-b found value cannot exceed standalone-b's proven ceiling
    #    (incr.obj <= incr_opt <= standalone_opt <= standalone.bound).
    check(f"smoke:M {b} incr.obj <= standalone.bound (bound-based)",
          _fin(m_b["obj"]) and _fin(sa_b["bound"])
          and _le(m_b["obj"], sa_b["bound"]),
          f"{m_b['obj']:,.0f} <= {sa_b['bound']:,.0f}")

    # O: sum of sequential found values cannot exceed the joint proven ceiling
    #    (sum.obj <= sum_opt <= joint_opt <= joint.bound) -> no double-count.
    ssum = m_a["obj"] + m_b["obj"]
    check("smoke:O incr.obj-sum <= joint.bound (bound-based)",
          _fin(ssum) and _fin(mj["bound"]) and _le(ssum, mj["bound"]),
          f"sum={ssum:,.0f} <= joint.bound={mj['bound']:,.0f}")


def main():
    print("=" * 100)
    print("INCREMENTAL RE-PRICER — VALIDATION")
    print("=" * 100)
    fixture_A()
    fixture_B()
    fixture_C()
    fixture_D()
    fixture_E()
    real_smoke()

    print("\n" + "=" * 100)
    npass = sum(1 for _, ok in _results if ok)
    nfail = len(_results) - npass
    print(f"RESULT: {npass} passed, {nfail} failed, of {len(_results)} checks")
    if nfail:
        print("FAILED:")
        for name, ok in _results:
            if not ok:
                print(f"  - {name}")
    print("=" * 100)
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
