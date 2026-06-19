"""
Incremental (sequential-auction) re-pricer — wrapper over the item model.

WHY this exists
---------------
prototype_slitting_optimizer prices every lot against the FULL customer book.
On auction day lots open one at a time; if you WIN a lot, the demand it served
is gone, so a later lot must NOT be allowed to re-sell that same demand. Pricing
each lot independently therefore OVERSTATES later lots and risks overbidding.

This wrapper keeps a single mutable "remaining demand" book:
    - price the next lot to open against remaining demand  -> its live max-bid
    - if WON  : subtract what that lot's plan actually consumed, re-price the rest
    - if LOST : remaining demand unchanged, move on

The per-lot solve is the byte-for-byte validated item model. Only the demand
book is orchestrated here — no model maths is touched.

INVENTORY CARRYOVER (the one real modelling choice)
---------------------------------------------------
A won lot also OVER-produces some specs into inventory (booked at 95% rate).
That inventory is real future stock, so strictly it should also reduce a later
lot's remaining demand — otherwise the double-count leak just moves from
"customer qty" to "inventory qty". Controlled by `include_inventory`:
    True  (default) : remaining -= customer_qty + inventory_qty   (leak-tight)
    False           : remaining -= customer_qty only              (looser)
The validation prints BOTH so the choice is made on real numbers.

Per-order consumption only (inventory of a spec reduces THAT order's demand,
not a different same-spec order's). A shared physical stock pool is a v2 idea;
out of scope until this layer is validated.

Run:
    conda activate slitting_opt
    python prototype_slitting_incremental.py
"""

from collections import defaultdict

from ortools.sat.python import cp_model

from engine import optimizer as item

TARGET_MARGIN = item.TARGET_MARGIN
SCRAP_RATE = item.SCRAP_RATE
SLIT_COST = item.SLIT_COST


def extract(res):
    """Solver result -> {oid: grams} for customer-delivered and inventory."""
    s = res["solver"]
    cust = {oid: s.Value(v) for oid, v in res["qty_to_customer"].items()}
    inv = {oid: s.Value(v) for oid, v in res["qty_to_inventory"].items()}
    return cust, inv


def metrics(lot, coils, orders, res):
    """Human-facing numbers, reconstructed exactly as report() does, plus the
    raw solver objective/bound used for the rigorous (optimal-only) invariants."""
    s = res["solver"]
    status = res["status"]
    feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    cust, inv = extract(res) if feasible else ({}, {})

    if not feasible:
        return {"lot": lot, "feasible": False, "optimal": False,
                "status": s.StatusName(status), "cust": {}, "inv": {}}

    start_price = coils[0]["price_per_kg"]
    total_wt = sum(c["weight_g"] for c in coils) / 1000  # kg
    cust_rev = sum(o["rate_per_kg"] * cust.get(o["id"], 0) / 1000 for o in orders)
    inv_rev = item.inv_revenue_rs(res, s)  # tiered month-slices (shared)
    scrap_kg = sum(s.Value(res["scrap_g"][c["id"]]) for c in coils) / 1000
    scrap_rev = SCRAP_RATE * scrap_kg
    slit_cost = sum(item.slit_cost_for(c) * c["weight_g"] / 1000
                    for c in coils if s.Value(res["slit"][c["id"]]))
    salvage_rev = sum(
        round((c["price_per_kg"] - res["salv_map"][c["coating"]])
              * c["weight_g"]) / 1000
        for c in coils if s.Value(res["salvage"][c["id"]])
    )
    lot_cost = start_price * total_wt
    total_rev = cust_rev + inv_rev + scrap_rev + salvage_rev
    profit = total_rev - lot_cost - slit_cost
    max_bid = ((total_rev * (1 - TARGET_MARGIN) - slit_cost) / total_wt
               if total_wt else 0.0)

    obj = res.get("obj", 0.0)
    bound = res.get("bound", 0.0)
    gap = abs(bound - obj) / max(abs(obj), 1) * 100 if obj else None

    return {
        "lot": lot, "feasible": True,
        "optimal": status == cp_model.OPTIMAL,
        "status": s.StatusName(status),
        "obj": obj, "bound": bound, "gap_pct": gap,
        "profit": profit, "total_rev": total_rev, "max_bid": max_bid,
        "scrap_kg": scrap_kg, "total_wt": total_wt,
        "cust": cust, "inv": inv,
    }


def consume(orders, res, include_inventory=True):
    """Return a NEW order list with qty_g reduced by what this lot's plan used.
    ids stay stable; grade/coating/thk sets are shared (never mutated)."""
    cust, inv = extract(res)
    out = []
    for o in orders:
        used = cust.get(o["id"], 0)
        if include_inventory:
            used += inv.get(o["id"], 0)
        no = dict(o)
        no["qty_g"] = max(0, o["qty_g"] - used)
        out.append(no)
    return out


def price_lot(lot, lot_coils, orders, n_workers=8):
    """Solve one lot vs the given (possibly already-reduced) order book."""
    coils = [dict(c) for c in lot_coils]
    for i, c in enumerate(coils):
        c["id"] = i
    res = item.solve(coils, orders, n_workers=n_workers)
    return coils, res, metrics(lot, coils, orders, res)


def run_sequence(by_lot, lot_order, outcomes, base_orders,
                 include_inventory=True, n_workers=8, verbose=True):
    """Walk lots in auction order. outcomes: {lot: "won"|"lost"}.
    Returns [(lot, metrics, outcome, remaining_demand_kg_after)]."""
    remaining = [dict(o) for o in base_orders]
    trail = []
    for lot in lot_order:
        _, res, m = price_lot(lot, by_lot[lot], remaining, n_workers=n_workers)
        outcome = outcomes.get(lot, "lost")
        if outcome == "won" and m["feasible"]:
            remaining = consume(remaining, res, include_inventory)
        rem_kg = sum(o["qty_g"] for o in remaining) / 1000
        trail.append((lot, m, outcome, rem_kg))
        if verbose and m["feasible"]:
            print(f"  {lot}: max-bid rs{m['max_bid']:,.2f}/kg  "
                  f"profit@start rs{m['profit']:,.0f}  [{outcome}]  "
                  f"remaining demand {rem_kg:,.0f} kg")
    return trail


def joint_solve(coils_all, base_orders, n_workers=8):
    """One model over ALL given coils vs FULL demand — the upper-bound oracle:
    a sequential greedy can never beat the joint optimum."""
    coils = [dict(c) for c in coils_all]
    for i, c in enumerate(coils):
        c["id"] = i
    res = item.solve(coils, base_orders, n_workers=n_workers)
    return coils, res, metrics("JOINT", coils, base_orders, res)


def main():
    coils = item.load_auction(item.AUCTION_CSV)
    orders = item.load_customers(item.CUSTOMER_CSV)
    by_lot = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)
    lots = sorted(by_lot)

    print("=" * 100)
    print("INCREMENTAL RE-PRICER — demo (auction order, every lot WON)")
    print(f"  inventory carryover = ON  |  time limit {item.SOLVE_TIME_LIMIT_S}s/lot")
    print("=" * 100 + "\n")

    outcomes = {lot: "won" for lot in lots}
    run_sequence(by_lot, lots, outcomes, orders, include_inventory=True)


if __name__ == "__main__":
    main()
