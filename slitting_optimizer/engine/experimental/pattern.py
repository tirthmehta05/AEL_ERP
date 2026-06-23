"""
Pattern-based Slitting Optimizer.

Same inputs/outputs/economics as prototype_slitting_optimizer.py (the item model),
but the cut is chosen from a pre-enumerated recipe book per coil class instead of
the solver building every strip from scratch. Breaks the symmetry that makes the
item model time out on wide master coils.

Coil class = (width, grade, coating, thickness). For each class we enumerate
*maximal* patterns: multisets of usable order-widths with
    sum <= class width,  strip count <= KNIFE_MAX,
    scrap in [edge trim, min usable width)     (>= min usable => dominated: fit
                                                another strip instead)
plus an "as-is" pattern when class width equals a usable order width
(ships whole: zero scrap, zero slit cost).

MILP: pick exactly one pattern per coil (z[c,P]); route produced kg of each width
to compatible orders (customer up to demand, surplus to inventory @ holding factor).

Validation: run this AND the item model on Lot 274049 (item model solves it to
true optimum) and compare PROFIT — must match within rounding.

Run:
    conda activate slitting_opt
    python prototype_slitting_pattern.py
"""

from collections import defaultdict, Counter
from ortools.sat.python import cp_model

from engine import optimizer as item  # reuse loaders / compat / constants

WIDTH_SCALE = item.WIDTH_SCALE
KNIFE_MAX = item.KNIFE_MAX
SCRAP_RATE = item.SCRAP_RATE
SLIT_COST = item.SLIT_COST
HOLDING_FACTOR_PCT = item.HOLDING_FACTOR_PCT
TARGET_MARGIN = item.TARGET_MARGIN
EDGE_TRIM_CDMM = item.EDGE_TRIM_MIN_MM * WIDTH_SCALE
MAX_PATTERNS_PER_CLASS = 40000


def class_key(c):
    return (c["width_cdmm"], c["grade"], c["coating"], c["thickness"])


def generate_patterns(width_cdmm, usable_widths, knife_max):
    """usable_widths: sorted-desc list of distinct order widths (cdmm) the class
    can serve. Returns list of (Counter{width:count}, scrap_cdmm, is_as_is)."""
    patterns = []
    if not usable_widths:
        return patterns
    min_w = min(usable_widths)

    # as-is: whole coil shipped as one strip of its own width
    if width_cdmm in usable_widths:
        patterns.append((Counter({width_cdmm: 1}), 0, True))

    uw = sorted(usable_widths, reverse=True)

    def dfs(idx, remaining, strips_left, cur):
        # maximal = cannot add the smallest usable strip anymore
        can_extend = strips_left > 0 and remaining >= min_w
        if not can_extend:
            used = width_cdmm - remaining
            scrap = remaining
            if cur and scrap >= EDGE_TRIM_CDMM and used > 0:
                patterns.append((Counter(cur), scrap, False))
                return
            if cur and scrap < EDGE_TRIM_CDMM:
                # leftover below edge-trim min: drop one of the largest strips
                # so scrap rises to a feasible value (rare; keeps set valid)
                return
            return
        if len(patterns) > MAX_PATTERNS_PER_CLASS:
            return
        progressed = False
        for j in range(idx, len(uw)):
            w = uw[j]
            if w <= remaining and strips_left > 0:
                progressed = True
                cur.append(w)
                dfs(j, remaining - w, strips_left - 1, cur)
                cur.pop()
        if not progressed and cur:
            scrap = remaining
            if scrap >= EDGE_TRIM_CDMM:
                patterns.append((Counter(cur), scrap, False))

    dfs(0, width_cdmm, knife_max, [])
    # dedupe
    seen, uniq = set(), []
    for cnt, scrap, asis in patterns:
        key = (tuple(sorted(cnt.items())), asis)
        if key not in seen:
            seen.add(key)
            uniq.append((cnt, scrap, asis))
    return uniq


def solve(coils, orders, patterns_by_class=None):
    """patterns_by_class: optional {class_key: [(Counter,scrap,is_as_is), ...]}.
    If None, patterns are brute-enumerated (bounded). Column generation injects
    a small high-quality set here instead."""
    model = cp_model.CpModel()

    # group coils into classes; usable widths per class via compat (class-uniform)
    classes = defaultdict(list)
    for c in coils:
        classes[class_key(c)].append(c)

    class_patterns = {}
    pat_stats = []
    for ck, cs in classes.items():
        rep = cs[0]
        usable = sorted({o["width_cdmm"] for o in orders if item.compat(rep, o)},
                        reverse=True)
        if patterns_by_class is not None:
            pats = patterns_by_class.get(ck, [])
        else:
            pats = generate_patterns(rep["width_cdmm"], usable, KNIFE_MAX)
        class_patterns[ck] = pats
        pat_stats.append((ck, len(cs), len(usable), len(pats)))

    # z[c,P] one pattern per coil
    z = {}
    for c in coils:
        pats = class_patterns[class_key(c)]
        for p in range(len(pats)):
            z[c["id"], p] = model.NewBoolVar(f"z_c{c['id']}_p{p}")
        if pats:
            model.Add(sum(z[c["id"], p] for p in range(len(pats))) == 1)

    # produced grams of width a from coil c (linear in z); routed to compatible orders
    # routed_g[c,o] integer grams of order o's width taken from coil c
    comp = {c["id"]: [o for o in orders if item.compat(c, o)] for c in coils}
    routed = {}
    for c in coils:
        for o in comp[c["id"]]:
            ub = c["weight_g"]
            routed[c["id"], o["id"]] = model.NewIntVar(0, ub, f"r_c{c['id']}_o{o['id']}")

    # conservation per (coil, EVERY compatible-order width).
    # produced(a) = 0 when no chosen pattern makes width a -> routed forced to 0,
    # which plugs the leak where a compat order width never appears in any pattern.
    for c in coils:
        cid = c["id"]
        pats = class_patterns[class_key(c)]
        W = c["width_cdmm"]
        widths = {o["width_cdmm"] for o in comp[cid]}
        for cnt, _, _ in pats:                 # include any pattern widths too
            widths.update(cnt)
        for a in widths:
            produced = sum(
                z[cid, p] * (cnt.get(a, 0) * a * c["weight_g"] // W)
                for p, (cnt, _, _) in enumerate(pats) if cnt.get(a, 0)
            )
            dests = [o for o in comp[cid] if o["width_cdmm"] == a]
            if dests:
                model.Add(sum(routed[cid, o["id"]] for o in dests) == produced)
            elif not isinstance(produced, int):
                model.Add(produced == 0)       # width with no buyer => forbid

    # scrap grams per coil
    scrap_g = {}
    for c in coils:
        cid = c["id"]
        pats = class_patterns[class_key(c)]
        W = c["width_cdmm"]
        sg = model.NewIntVar(0, c["weight_g"], f"sc_c{cid}")
        model.Add(sg == sum(z[cid, p] * (scrap * c["weight_g"] // W)
                            for p, (_, scrap, _) in enumerate(pats)))
        scrap_g[cid] = sg

    # slit cost: any non-as-is pattern incurs SLIT_COST on full coil weight
    slit_cost_terms = []
    for c in coils:
        cid = c["id"]
        pats = class_patterns[class_key(c)]
        for p, (_, _, asis) in enumerate(pats):
            if not asis:
                slit_cost_terms.append(SLIT_COST * c["weight_g"] * z[cid, p])

    # order fill: customer (<=demand) + inventory
    to_customer, to_inventory = {}, {}
    by_order = defaultdict(list)
    for c in coils:
        for o in comp[c["id"]]:
            by_order[o["id"]].append(c)
    for o in orders:
        oid = o["id"]
        if oid not in by_order:
            continue
        to_customer[oid] = model.NewIntVar(0, o["qty_g"], f"cust_o{oid}")
        ubinv = sum(c["weight_g"] for c in by_order[oid])
        to_inventory[oid] = model.NewIntVar(0, ubinv, f"inv_o{oid}")
        model.Add(sum(routed[c["id"], oid] for c in by_order[oid])
                  == to_customer[oid] + to_inventory[oid])

    cust_rev = sum(o["rate_per_kg"] * to_customer[o["id"]]
                   for o in orders if o["id"] in to_customer)
    inv_rev = sum((o["rate_per_kg"] * HOLDING_FACTOR_PCT // 100) * to_inventory[o["id"]]
                  for o in orders if o["id"] in to_inventory)
    scrap_rev = sum(SCRAP_RATE * scrap_g[c["id"]] for c in coils)
    lot_cost = sum(int(round(c["price_per_kg"])) * c["weight_g"] for c in coils)
    model.Maximize(cust_rev + inv_rev + scrap_rev - lot_cost - sum(slit_cost_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 120
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)
    return {
        "solver": solver, "status": status, "z": z, "scrap_g": scrap_g,
        "to_customer": to_customer, "to_inventory": to_inventory,
        "class_patterns": class_patterns, "pat_stats": pat_stats, "comp": comp,
        "routed": routed,
    }


def report(lot, coils, orders, res):
    s, status = res["solver"], res["status"]
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"LOT {lot}: NO SOLUTION ({s.StatusName(status)})")
        return None
    start_price = coils[0]["price_per_kg"]
    total_wt = sum(c["weight_g"] for c in coils) / 1000

    asis_n = slit_n = 0
    scrap_kg = sum(s.Value(res["scrap_g"][c["id"]]) for c in coils) / 1000
    for c in coils:
        pats = res["class_patterns"][class_key(c)]
        for p, (_, _, asis) in enumerate(pats):
            if (c["id"], p) in res["z"] and s.Value(res["z"][c["id"], p]):
                if asis:
                    asis_n += 1
                else:
                    slit_n += 1
                break

    cust_rev = sum(o["rate_per_kg"] * s.Value(res["to_customer"][o["id"]]) / 1000
                   for o in orders if o["id"] in res["to_customer"])
    inv_rev = sum((o["rate_per_kg"] * HOLDING_FACTOR_PCT // 100)
                  * s.Value(res["to_inventory"][o["id"]]) / 1000
                  for o in orders if o["id"] in res["to_inventory"])
    scrap_rev = SCRAP_RATE * scrap_kg
    slit_wt = 0.0
    for c in coils:
        pats = res["class_patterns"][class_key(c)]
        for p, (_, _, asis) in enumerate(pats):
            if (c["id"], p) in res["z"] and s.Value(res["z"][c["id"], p]) and not asis:
                slit_wt += c["weight_g"] / 1000
                break
    slit_cost = SLIT_COST * slit_wt
    lot_cost = start_price * total_wt
    total_rev = cust_rev + inv_rev + scrap_rev
    profit = total_rev - lot_cost - slit_cost
    margin = profit / total_rev * 100 if total_rev else 0
    npats = sum(st[3] for st in res["pat_stats"])

    print("=" * 100)
    print(f"LOT {lot} [PATTERN] | {len(coils)} coils | {total_wt/1000:.2f} MT | "
          f"{s.StatusName(status)} {s.WallTime():.1f}s | {len(res['pat_stats'])} classes, "
          f"{npats} patterns")
    print("=" * 100)
    print(f"  as-is {asis_n} | slit {slit_n} | scrap {scrap_kg:.1f}kg "
          f"({100*scrap_kg/total_wt:.2f}%)")
    print(f"  Revenue cust rs{cust_rev:,.0f} + inv rs{inv_rev:,.0f} + scrap rs{scrap_rev:,.0f}"
          f" = rs{total_rev:,.0f}")
    print(f"  Cost    lot rs{lot_cost:,.0f} + slit rs{slit_cost:,.0f}")
    print(f"  PROFIT @ start: rs{profit:,.0f}  margin {margin:.2f}%")
    if total_wt > 0:
        p_max = (total_rev * (1 - TARGET_MARGIN) - slit_cost) / total_wt
        print(f"  MAX BID for {TARGET_MARGIN*100:.0f}% margin: rs{p_max:,.2f}/kg")
    return profit


def main():
    coils = item.load_auction(item.AUCTION_CSV)
    orders = item.load_customers(item.CUSTOMER_CSV)
    by_lot = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)

    print("VALIDATION: Lot 274049 — pattern model vs item model (must match profit)\n")
    lc = [dict(c) for c in by_lot["274049"]]
    for i, c in enumerate(lc):
        c["id"] = i
    pat_profit = report("274049", lc, orders, solve(lc, orders))

    lc2 = [dict(c) for c in by_lot["274049"]]
    for i, c in enumerate(lc2):
        c["id"] = i
    ires = item.solve(lc2, orders)
    print()
    item.report("274049", lc2, orders, ires, show_plan=False)
    isolver = ires["solver"]
    # recompute item profit same way item.report does (printed there); compare flag
    print("\n" + "=" * 100)
    print(f"CROSS-CHECK: pattern profit rs{pat_profit:,.0f}  "
          f"(compare to item model PROFIT line above; should match within rounding)")
    print("=" * 100 + "\n")

    print("ALL LOTS [PATTERN MODEL]\n")
    for lot in sorted(by_lot):
        lcx = [dict(c) for c in by_lot[lot]]
        for i, c in enumerate(lcx):
            c["id"] = i
        report(lot, lcx, orders, solve(lcx, orders))


if __name__ == "__main__":
    main()
