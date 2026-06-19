"""
Slitting Plan Optimizer — Prototype
1.5D-RCSPUL with as-is + slit modes for CRNO coil auctions.

Inputs (enriched, built by build_*_csv.py):
  Slitting Plan Optimization - Auction Built.csv
      Lot,Batch,Width,Quantity,Starting Price,Grade,Coating,Thickness
  Slitting Plan Optimization - Customer Built.csv
      Customer,Width,Quantity,Rate,Grades,Coatings,Thickness

Matching rule (compat):
  order.width <= coil.width
  AND coil.grade     in order.grades
  AND coil.coating   in order.coatings
  AND coil.thickness in order.thicknesses

Runs each auction Lot independently against full customer demand.

Run:
    conda activate slitting_opt
    python prototype_slitting_optimizer.py
"""

import csv
import os
from collections import defaultdict
from pathlib import Path
from ortools.sat.python import cp_model

# Operation parameters — operator-tunable via environment variables (no code
# edit, no image rebuild; just set the env / .env and restart). Defaults equal
# the validated values, so behaviour is byte-identical when the env is unset
# (the 39/39 harness still holds). The engine reads os.environ DIRECTLY to
# remain a pure module (no dependency on the app/config layer).
EDGE_TRIM_MIN_MM = int(os.environ.get("SLIT_EDGE_TRIM_MM", 3))      # min edge trim, mm
KNIFE_MAX = int(os.environ.get("SLIT_KNIFE_MAX", 12))              # max strips/cuts per coil
SCRAP_RATE = int(os.environ.get("SLIT_SCRAP_RATE", 34))           # rs/kg scrap sells for
SLIT_COST = float(os.environ.get("SLIT_SLITTING_COST", 4))        # rs/kg, slit-mode coils (float; e.g. 2.5)
HOLDING_FACTOR_PCT = int(os.environ.get("SLIT_HOLDING_FACTOR_PCT", 95))  # month-1 inv value %
HOLDING_STEP_PCT = int(os.environ.get("SLIT_HOLDING_STEP_PCT", 5))       # -% per extra month
TARGET_MARGIN = float(os.environ.get("SLIT_TARGET_MARGIN", 0.08))       # max-bid margin
SOLVE_TIME_LIMIT_S = int(os.environ.get("SLIT_TIME_LIMIT", 300))  # per-lot solve budget, s

# Scaling: widths in centi-mm (cdmm), weights in grams
WIDTH_SCALE = 100        # mm -> cdmm (handles decimals like 76.2)
MT_TO_GRAMS = 1_000_000

BASE = Path("/Users/tirthmehta/Documents/Personal Files/Amba/AEL ERP/AEL_ERP_V1/AEL_ERP")
AUCTION_CSV = BASE / "Slitting Plan Optimization - Auction Built.csv"
CUSTOMER_CSV = BASE / "Slitting Plan Optimization - Customer Built.csv"


# --- Operator-tunable width-banded & salvage accessors --------------------
# Read at SOLVE-CALL time (not import) so they're testable in-process and
# truly runtime-tunable. Wide-band vars DEFAULT to the narrow value, so an
# unset env reproduces the flat, validated behaviour exactly (39/39 holds).
def _envi(name, default):
    return int(os.environ.get(name, default))


def _envf(name, default):
    return float(os.environ.get(name, default))


def _band(width_cdmm):
    return ("narrow" if width_cdmm / WIDTH_SCALE
            <= _envf("SLIT_BAND_MM", 650) else "wide")


def knife_max_for(c):
    n = _envi("SLIT_KNIFE_MAX", 12)
    return n if _band(c["width_cdmm"]) == "narrow" \
        else _envi("SLIT_KNIFE_MAX_WIDE", n)


def edge_trim_mm_for(c):
    n = _envi("SLIT_EDGE_TRIM_MM", 3)
    return n if _band(c["width_cdmm"]) == "narrow" \
        else _envi("SLIT_EDGE_TRIM_MM_WIDE", n)


def slit_cost_for(c):                       # rs/kg (float)
    n = _envf("SLIT_SLITTING_COST", 4)
    return n if _band(c["width_cdmm"]) == "narrow" \
        else _envf("SLIT_SLITTING_COST_WIDE", n)


def max_inv_months():
    """Cap on inventory months PER ORDER, applied ONLY to orders whose
    accepted coatings are entirely in the salvage map. Prevents over-stocking
    of salvage-only inventory at premium tier rates when real absorption is
    limited. Default 999 = effectively no cap = today's behaviour (so the
    51 invariants remain a live regression guard when this env is unset)."""
    return _envi("SLIT_MAX_INV_MONTHS", 999)


def _salvage_map():
    """'C6L:2,C3H:2,UC:4' -> {coating: delta_rs}. Empty => no salvage,
    so behaviour is unchanged (regression guard)."""
    out = {}
    for part in os.environ.get("SLIT_SALVAGE", "").split(","):
        part = part.strip()
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        try:
            out[k.strip()] = float(v)
        except ValueError:
            continue
    return out


def salvage_safeguard_flags(orders):
    """Loud-flag customer orders that list a SALVAGE-only coating.
    A real customer offer for these coatings would inflate the bid above
    the safe salvage value (start − delta) — i.e. the model's safety only
    holds with accurate input. Better to fail noisy than silently overbid."""
    salv = set(_salvage_map().keys())
    if not salv:
        return []
    flags = []
    for o in orders:
        overlap = sorted(o["coatings"] & salv)
        if overlap:
            flags.append(
                f"Customer '{o['customer']}' row "
                f"(w{o['width_cdmm'] / WIDTH_SCALE:g}, "
                f"grades {sorted(o['grades'])}) lists salvage-only coating(s) "
                f"{overlap} — remove these or the bid will be inflated.")
    return flags


def _thk(v):
    return round(float(v), 3)


def inv_slice_coefs(rate):
    """Per-kg value of each 'month' of leftover stock for a customer paying
    `rate`. Month 1 = rate*95/100, month 2 = rate*90/100, ... dropping 5%
    per month. Stops once it would reach scrap value; everything deeper is
    valued at scrap (the 'tail', added by the caller). Concave by design:
    the solver fills the richest month first with no ordering variables."""
    coefs = []
    k = 1
    while True:
        factor = HOLDING_FACTOR_PCT - HOLDING_STEP_PCT * (k - 1)
        if factor <= 0:
            break
        c = rate * factor // 100
        if c <= SCRAP_RATE:
            break
        coefs.append(c)
        k += 1
    return coefs


def load_auction(path):
    coils = []
    with open(path) as f:
        for i, row in enumerate(csv.DictReader(f)):
            coils.append({
                "id": i,
                "lot": row["Lot"].strip(),
                "batch": row["Batch"].strip(),
                "width_cdmm": int(round(float(row["Width"]) * WIDTH_SCALE)),
                "weight_g": int(round(float(row["Quantity"]) * MT_TO_GRAMS)),
                "price_per_kg": float(row["Starting Price"]) / 1000,  # rs/MT -> rs/kg
                "grade": row["Grade"].strip(),
                "coating": row["Coating"].strip(),
                "thickness": _thk(row["Thickness"]),
            })
    return coils


def load_customers(path):
    orders = []
    with open(path) as f:
        for i, row in enumerate(csv.DictReader(f)):
            qty_key = "Quantity" if "Quantity" in row else "Quantiy"
            orders.append({
                "id": i,
                "customer": row["Customer"].strip(),
                "mode": "slit",
                "width_cdmm": int(round(float(row["Width"]) * WIDTH_SCALE)),
                "width_min_cdmm": None,
                "width_max_cdmm": None,
                "qty_g": int(round(float(row[qty_key]) * MT_TO_GRAMS)),
                # original MONTHLY run-rate; qty_g may later be reduced by the
                # incremental re-pricer as won lots source it, but monthly_g
                # stays put — holding cost tracks consumption rate, not what's
                # already been sourced (see slice width in solve()).
                "monthly_g": int(round(float(row[qty_key]) * MT_TO_GRAMS)),
                "rate_per_kg": int(round(float(row["Rate"]))),
                "grades": {g.strip() for g in row["Grades"].split("|") if g.strip()},
                "coatings": {c.strip() for c in row["Coatings"].split("|") if c.strip()},
                "thicknesses": {_thk(t) for t in row["Thickness"].split("|") if t.strip()},
                # min weight (grams) of EACH delivered coil; 0 = no minimum
                "min_coil_g": int(round(float(row.get("MinCoilQty", 0) or 0) * 1000)),
            })
    return orders


def compat(c, o):
    if not (c["grade"] in o["grades"]
            and c["coating"] in o["coatings"]
            and c["thickness"] in o["thicknesses"]):
        return False
    if o.get("mode") == "asis":
        # asis: coil width in [min, max]; whole coil consumed as-is
        return (o["width_min_cdmm"] <= c["width_cdmm"] <= o["width_max_cdmm"]
                and c["weight_g"] >= o["min_coil_g"])
    # slit (existing): strip cut to o.width from a wider coil
    strip_coil_g = o["width_cdmm"] / c["width_cdmm"] * c["weight_g"]
    return (
        o["width_cdmm"] <= c["width_cdmm"]
        and strip_coil_g >= o["min_coil_g"]
    )


def diagnostic(coils, orders):
    """Per-lot compatibility report; flags coils that match zero orders."""
    print("=" * 100)
    print("COMPATIBILITY DIAGNOSTIC")
    print("=" * 100)
    by_lot = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)
    for lot, cs in by_lot.items():
        zero = []
        total_match = 0
        for c in cs:
            n = sum(1 for o in orders if compat(c, o))
            total_match += n
            if n == 0:
                zero.append(c)
        avg = total_match / len(cs) if cs else 0
        print(f"Lot {lot}: {len(cs)} coils, avg {avg:.1f} compatible orders/coil, "
              f"{len(zero)} coils match ZERO orders")
        if zero:
            sample = ", ".join(f"{z['batch']}(w{z['width_cdmm']/WIDTH_SCALE},"
                               f"g{z['grade']},{z['coating']},t{z['thickness']})"
                               for z in zero[:6])
            print(f"   zero-match e.g.: {sample}{' ...' if len(zero) > 6 else ''}")
    print()


def solve(coils, orders, n_workers=8):
    model = cp_model.CpModel()
    salv_map = _salvage_map()

    # Precompute compatible orders per coil
    comp = {c["id"]: [o for o in orders if compat(c, o)] for c in coils}

    x = {}
    asis_alloc = {}
    for c in coils:
        for o in comp[c["id"]]:
            if o.get("mode") == "asis":
                # whole-coil disposition; one boolean per (coil, asis order)
                asis_alloc[c["id"], o["id"]] = model.NewBoolVar(
                    f"asisAlloc_c{c['id']}_o{o['id']}")
            else:
                max_strips = min(knife_max_for(c), c["width_cdmm"] // o["width_cdmm"])
                x[c["id"], o["id"]] = model.NewIntVar(
                    0, max_strips, f"x_c{c['id']}_o{o['id']}")

    y = {c["id"]: model.NewIntVar(0, c["width_cdmm"], f"y_c{c['id']}") for c in coils}

    as_is, slit, salvage = {}, {}, {}
    for c in coils:
        cid = c["id"]
        has_slit_exact = any(o.get("mode") != "asis" and o["width_cdmm"] == c["width_cdmm"]
                             for o in comp[cid])
        has_asis_match = any(o.get("mode") == "asis" for o in comp[cid])
        as_is[cid] = model.NewBoolVar(f"asis_c{cid}")
        slit[cid] = model.NewBoolVar(f"slit_c{cid}")
        salvage[cid] = model.NewBoolVar(f"salv_c{cid}")
        if not has_slit_exact and not has_asis_match:
            model.Add(as_is[cid] == 0)
        if c["coating"] not in salv_map:        # salvage only for tagged coatings
            model.Add(salvage[cid] == 0)
        model.Add(as_is[cid] + slit[cid] + salvage[cid] == 1)

    for c in coils:
        cid = c["id"]
        co = comp[cid]
        slit_orders = [o for o in co if o.get("mode") != "asis"]
        asis_orders = [o for o in co if o.get("mode") == "asis"]
        # whole-coil "consumed" indicator: salvage OR an asis order took the coil.
        # When set, all slit x's = 0 and y = 0 (no strips, no scrap).
        whole_to_asis = (sum(asis_alloc[cid, o["id"]] for o in asis_orders)
                         if asis_orders else 0)
        model.Add(
            sum(o["width_cdmm"] * x[cid, o["id"]] for o in slit_orders) + y[cid]
            == c["width_cdmm"] * (1 - salvage[cid]) - c["width_cdmm"] * whole_to_asis
        )
        model.Add(y[cid] >= edge_trim_mm_for(c) * WIDTH_SCALE * slit[cid])
        model.Add(y[cid] <= c["width_cdmm"] * slit[cid])
        model.Add(sum(x[cid, o["id"]] for o in slit_orders) <= knife_max_for(c))
        # Gate asis_alloc: only fires when as_is disposition is chosen
        for o in asis_orders:
            model.Add(asis_alloc[cid, o["id"]] <= as_is[cid])
        # Gate slit exact-width strips (existing as-is path)
        matching = [o for o in slit_orders if o["width_cdmm"] == c["width_cdmm"]]
        for o in matching:
            model.Add(x[cid, o["id"]] <= as_is[cid])
        if matching or asis_orders:
            model.Add(
                sum(x[cid, o["id"]] for o in matching)
                + sum(asis_alloc[cid, o["id"]] for o in asis_orders)
                == as_is[cid]
            )

    strip_g = {}
    for c in coils:
        for o in comp[c["id"]]:
            if o.get("mode") == "asis":
                continue   # asis orders take the whole coil — no strip_g
            strip_g[c["id"], o["id"]] = int(round(
                o["width_cdmm"] * c["weight_g"] / c["width_cdmm"]
            ))

    qty_to_customer, qty_to_inventory, inv_slices = {}, {}, {}
    coils_for_order = defaultdict(list)
    for c in coils:
        for o in comp[c["id"]]:
            coils_for_order[o["id"]].append(c)
    for o in orders:
        oid = o["id"]
        cfo = coils_for_order.get(oid, [])
        if not cfo:
            continue
        # customer sale capped at REMAINING demand (won lots already sourced
        # some of it in the incremental flow); inventory slices below are
        # sized by the ORIGINAL monthly run-rate instead.
        qty_to_customer[oid] = model.NewIntVar(0, o["qty_g"], f"toCust_o{oid}")
        if o.get("mode") == "asis":
            ub_inv = sum(c["weight_g"] for c in cfo)
        else:
            ub_inv = sum(
                strip_g[c["id"], oid] * min(knife_max_for(c),
                                            c["width_cdmm"] // o["width_cdmm"])
                for c in cfo
            )
        # Tiered holding value. Each slice is one MONTH of this customer's
        # run-rate (monthly_g, NOT the shrunk qty_g) wide; deeper slices are
        # cheaper; anything past the last priced month falls to the scrap
        # 'tail'. Concave coefs => richest slice fills first automatically.
        month_g = o.get("monthly_g", o["qty_g"])
        slices = []
        for i, coef in enumerate(inv_slice_coefs(o["rate_per_kg"])):
            slices.append((coef,
                           model.NewIntVar(0, month_g, f"inv_o{oid}_m{i + 1}")))
        slices.append((SCRAP_RATE,
                       model.NewIntVar(0, ub_inv, f"inv_o{oid}_tail")))
        qty_to_inventory[oid] = model.NewIntVar(0, ub_inv, f"toInv_o{oid}")
        model.Add(qty_to_inventory[oid] == sum(v for _, v in slices))
        inv_slices[oid] = slices
        # Cap inventory for orders that accept ONLY salvage-eligible coatings.
        # Prevents over-stocking of risky stock at premium tier rates when
        # real absorption is limited; overflow falls through to salvage rate
        # (cheaper than tier 1 but still way above scrap). Default cap = 999
        # months = effectively no cap = today's behaviour preserved.
        if salv_map and o["coatings"] and o["coatings"] <= salv_map.keys():
            model.Add(qty_to_inventory[oid] <= max_inv_months() * month_g)
        if o.get("mode") == "asis":
            produced = sum(c["weight_g"] * asis_alloc[c["id"], oid] for c in cfo)
        else:
            produced = sum(strip_g[c["id"], oid] * x[c["id"], oid] for c in cfo)
        model.Add(produced == qty_to_customer[oid] + qty_to_inventory[oid])

    scrap_g = {}
    for c in coils:
        cid = c["id"]
        coef = max(1, int(round(c["weight_g"] / c["width_cdmm"])))
        scrap_g[cid] = model.NewIntVar(0, coef * c["width_cdmm"], f"scrapG_c{cid}")
        model.Add(scrap_g[cid] == coef * y[cid])

    customer_rev = sum(o["rate_per_kg"] * qty_to_customer[o["id"]]
                       for o in orders if o["id"] in qty_to_customer)
    inventory_rev = sum(coef * v
                        for slices in inv_slices.values()
                        for coef, v in slices)
    scrap_rev = sum(SCRAP_RATE * scrap_g[c["id"]] for c in coils)
    # float slit cost -> integer constant coefficient on the boolean
    # (weight_g ~1e6 g, so rounding error is negligible)
    slit_cost_total = sum(int(round(slit_cost_for(c) * c["weight_g"]))
                          * slit[c["id"]] for c in coils)
    # whole-coil salvage for hard-to-sell coatings at lot_start - delta;
    # no demand / inventory / scrap interaction (no-oversell untouched)
    salvage_rev = sum(
        int(round((c["price_per_kg"] - salv_map[c["coating"]])
                  * c["weight_g"])) * salvage[c["id"]]
        for c in coils if c["coating"] in salv_map
    )
    lot_cost = sum(int(round(c["price_per_kg"])) * c["weight_g"] for c in coils)

    model.Maximize(customer_rev + inventory_rev + scrap_rev + salvage_rev
                   - lot_cost - slit_cost_total)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVE_TIME_LIMIT_S
    solver.parameters.num_search_workers = n_workers
    status = solver.Solve(model)
    return {
        "solver": solver, "status": status, "x": x, "y": y, "as_is": as_is, "slit": slit,
        "salvage": salvage, "salv_map": salv_map, "asis_alloc": asis_alloc,
        "qty_to_customer": qty_to_customer, "qty_to_inventory": qty_to_inventory,
        "inv_slices": inv_slices, "scrap_g": scrap_g, "comp": comp,
        "obj": solver.ObjectiveValue(), "bound": solver.BestObjectiveBound(),
    }


def inv_revenue_rs(res, s):
    """Realised inventory revenue (rs), summed over the tiered month-slices.
    Shared by report() and the incremental wrapper so they never drift."""
    return sum(coef * s.Value(v) / 1000
               for slices in res["inv_slices"].values()
               for coef, v in slices)


def report(lot, coils, orders, res, show_plan=True):
    s = res["solver"]
    status = res["status"]
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"  Lot {lot}: NO SOLUTION (status={s.StatusName(status)})")
        return
    start_price = coils[0]["price_per_kg"]

    asis_n = slit_n = salv_n = 0
    total_scrap_g = 0
    plan_lines = []
    for c in coils:
        cid = c["id"]
        if s.Value(res["salvage"][cid]):
            salv_n += 1
            d = res["salv_map"].get(c["coating"], 0)
            plan_lines.append(f"  {c['batch']:<11} w{c['width_cdmm']/WIDTH_SCALE:<6} "
                              f"{c['weight_g']/1000:>7.3f}kg salvage-> "
                              f"{c['coating']} @ rs{c['price_per_kg']-d:.2f}/kg "
                              f"(start-{d:g})")
        elif s.Value(res["as_is"][cid]):
            asis_n += 1
            dest = "(none)"
            for o in orders:
                if (cid, o["id"]) in res["x"] and s.Value(res["x"][cid, o["id"]]) > 0:
                    dest = f"{o['customer']} #{o['id']} ({o['width_cdmm']/WIDTH_SCALE}mm @ rs{o['rate_per_kg']})"
                    break
            plan_lines.append(f"  {c['batch']:<11} w{c['width_cdmm']/WIDTH_SCALE:<6} "
                              f"{c['weight_g']/1000:>7.3f}kg as-is -> {dest}")
        else:
            slit_n += 1
            strips = []
            for o in orders:
                if (cid, o["id"]) in res["x"]:
                    n = s.Value(res["x"][cid, o["id"]])
                    if n > 0:
                        strips.append(f"{n}x{o['width_cdmm']/WIDTH_SCALE}")
            sc = s.Value(res["y"][cid]) / WIDTH_SCALE
            plan_lines.append(f"  {c['batch']:<11} w{c['width_cdmm']/WIDTH_SCALE:<6} "
                              f"{c['weight_g']/1000:>7.3f}kg slit  -> "
                              f"{' + '.join(strips) if strips else '(none)'} + {sc:.2f}mm scrap")
        total_scrap_g += s.Value(res["scrap_g"][cid])

    total_wt = sum(c["weight_g"] for c in coils) / 1000
    cust_rev = sum(o["rate_per_kg"] * s.Value(res["qty_to_customer"][o["id"]]) / 1000
                   for o in orders if o["id"] in res["qty_to_customer"])
    inv_rev = inv_revenue_rs(res, s)
    scrap_kg = total_scrap_g / 1000
    scrap_rev = SCRAP_RATE * scrap_kg
    slit_cost = sum(slit_cost_for(c) * c["weight_g"] / 1000
                    for c in coils if s.Value(res["slit"][c["id"]]))
    salvage_rev = sum(
        round((c["price_per_kg"] - res["salv_map"][c["coating"]])
              * c["weight_g"]) / 1000
        for c in coils if s.Value(res["salvage"][c["id"]])
    )
    lot_cost = start_price * total_wt
    total_rev = cust_rev + inv_rev + scrap_rev + salvage_rev
    profit = total_rev - lot_cost - slit_cost
    margin = profit / total_rev * 100 if total_rev else 0

    # optimality gap: how far the found solution is from the proven best bound
    obj, bound = res.get("obj", 0.0), res.get("bound", 0.0)
    if status == cp_model.OPTIMAL:
        surety = "PROVEN OPTIMAL"
    elif obj and bound:
        gap = abs(bound - obj) / max(abs(obj), 1) * 100
        surety = f"within {gap:.2f}% of optimal (safe: max-bid is a conservative floor)"
    else:
        surety = "no proven bound"

    print("=" * 100)
    print(f"LOT {lot}  |  {len(coils)} coils  |  {total_wt/1000:.2f} MT  |  "
          f"{s.StatusName(status)}  {s.WallTime():.1f}s  |  {surety}")
    print("=" * 100)
    if show_plan:
        for ln in plan_lines:
            print(ln)
    print(f"  as-is {asis_n} | slit {slit_n} | salvage {salv_n} | "
          f"scrap {scrap_kg:.1f}kg ({100*scrap_kg/total_wt:.2f}%)")
    print(f"  Revenue  cust rs{cust_rev:,.0f} + inv rs{inv_rev:,.0f} + "
          f"salvage rs{salvage_rev:,.0f} + scrap rs{scrap_rev:,.0f} "
          f"= rs{total_rev:,.0f}")
    print(f"  Cost     lot rs{lot_cost:,.0f} (@rs{start_price}/kg) + slit rs{slit_cost:,.0f}")
    print(f"  PROFIT @ start: rs{profit:,.0f}   margin {margin:.2f}%")
    if total_wt > 0:
        p_max = (total_rev * (1 - TARGET_MARGIN) - slit_cost) / total_wt
        print(f"  MAX BID for {TARGET_MARGIN*100:.0f}% margin: rs{p_max:,.2f}/kg "
              f"(rs{p_max*1000:,.0f}/MT)")

    # customer-level coverage
    cov = defaultdict(lambda: [0.0, 0.0])  # customer -> [demand, filled]
    for o in orders:
        cov[o["customer"]][0] += o["qty_g"] / 1000
        if o["id"] in res["qty_to_customer"]:
            cov[o["customer"]][1] += s.Value(res["qty_to_customer"][o["id"]]) / 1000
    print("  Coverage by customer (filled / demand kg):")
    for cust, (d, fdone) in sorted(cov.items()):
        print(f"    {cust:<20} {fdone:>10,.0f} / {d:>10,.0f}  ({100*fdone/d if d else 0:.1f}%)")
    print()


def main():
    coils = load_auction(AUCTION_CSV)
    orders = load_customers(CUSTOMER_CSV)
    print(f"Loaded {len(coils)} coils, {len(orders)} orders, "
          f"{len(set(c['lot'] for c in coils))} lots.\n")

    diagnostic(coils, orders)

    by_lot = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)

    print("=" * 100)
    print("PER-LOT OPTIMIZATION (each lot vs FULL demand, independent)")
    print("=" * 100 + "\n")
    for lot in sorted(by_lot):
        lot_coils = [dict(c) for c in by_lot[lot]]
        for i, c in enumerate(lot_coils):  # reindex 0..n for this sub-solve
            c["id"] = i
        res = solve(lot_coils, orders)
        report(lot, lot_coils, orders, res, show_plan=True)


if __name__ == "__main__":
    main()
