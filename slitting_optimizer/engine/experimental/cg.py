"""
Column-generation slitting optimizer (price-and-branch).

Instead of brute-enumerating every pattern (explodes on wide coils), we:
  1. seed each coil class with a few sensible patterns,
  2. solve the master LP relaxation (GLOP, continuous routing = "Lever 1"),
  3. read demand dual prices, run a per-class knapsack to PRICE the most
     valuable missing pattern, add it,
  4. iterate until no class yields an improving pattern,
  5. do ONE exact integer solve (CP-SAT) over the discovered columns
     via prototype_slitting_pattern.solve(patterns_by_class=...).

Validation: run on Lot 274049 and compare PROFIT to the item model
(prototype_slitting_optimizer), which solves that lot to true optimum.

Run:
    conda activate slitting_opt
    python prototype_slitting_cg.py
"""

import time
from collections import defaultdict, Counter
from ortools.linear_solver import pywraplp

from engine import optimizer as item
from engine.experimental import pattern as P

KNIFE_MAX = item.KNIFE_MAX
SCRAP_RATE = item.SCRAP_RATE
SLIT_COST = item.SLIT_COST
HOLDING = item.HOLDING_FACTOR_PCT / 100.0
EDGE = item.EDGE_TRIM_MIN_MM * item.WIDTH_SCALE
MAX_ROUNDS = 25
PATTERN_CAP = 60  # safety cap per class


def knapsack_pattern(W, widths, value, knife, min_w):
    """Best multiset: maximize sum(count_a * value[a]), sum(a) <= W,
    count <= knife, leftover (W - used) >= EDGE (slit) or used == W (exact).
    DP over used-width in cdmm (coarsened by gcd-ish step = min_w to bound size)."""
    # coarsen capacity to keep DP small: step = max(1, min_w // 4)
    step = max(1, min_w // 4)
    cap = W // step
    NEG = -1e18
    # dp[u][k] = best value using exactly k strips filling 'u' steps
    dp = [[NEG] * (knife + 1) for _ in range(cap + 1)]
    pick = [[None] * (knife + 1) for _ in range(cap + 1)]
    dp[0][0] = 0.0
    for u in range(cap + 1):
        for k in range(knife + 1):
            if dp[u][k] == NEG:
                continue
            for a in widths:
                ua = u + a // step
                if ua <= cap and k + 1 <= knife:
                    nv = dp[u][k] + value[a]
                    if nv > dp[ua][k + 1]:
                        dp[ua][k + 1] = nv
                        pick[ua][k + 1] = (u, k, a)
    best = None
    best_val = 0.0
    for u in range(cap + 1):
        used = u * step
        scrap = W - used
        if used == 0:
            continue
        feasible = (scrap >= EDGE) or (scrap == 0)
        if not feasible:
            continue
        for k in range(1, knife + 1):
            if dp[u][k] > best_val + 1e-9:
                best_val = dp[u][k]
                best = (u, k)
    if best is None:
        return None
    cnt = Counter()
    u, k = best
    while pick[u][k] is not None:
        pu, pk, a = pick[u][k]
        cnt[a] += 1
        u, k = pu, pk
    used = sum(w * n for w, n in cnt.items())
    scrap = W - used
    if not cnt or (scrap < EDGE and scrap != 0):
        return None
    return (cnt, scrap, scrap == 0 and len(cnt) == 1 and next(iter(cnt)) == W)


def seed_patterns(W, usable, knife):
    """as-is + a few greedy low-scrap patterns (width-desc, then medium, small)."""
    pats = []
    if W in usable:
        pats.append((Counter({W: 1}), 0, True))
    for order in (sorted(usable, reverse=True), sorted(usable),
                  sorted(usable, key=lambda a: -a)[1:]):
        rem, k, cnt = W, knife, Counter()
        for a in order:
            while a <= rem and k > 0:
                cnt[a] += 1
                rem -= a
                k -= 1
        scrap = W - sum(w * n for w, n in cnt.items())
        if cnt and (scrap >= EDGE or scrap == 0):
            pats.append((Counter(cnt), scrap, False))
    return _dedupe(pats)


def _dedupe(pats):
    seen, out = set(), []
    for cnt, scrap, asis in pats:
        key = (tuple(sorted(cnt.items())), asis)
        if key not in seen:
            seen.add(key)
            out.append((cnt, scrap, asis))
    return out


def build_master(coils, orders, class_pats):
    """Continuous LP relaxation. Returns (solver, demand_constraints)."""
    s = pywraplp.Solver.CreateSolver("GLOP")
    s.SetTimeLimit(60000)
    by_class = defaultdict(list)
    for c in coils:
        by_class[P.class_key(c)].append(c)
    comp = {c["id"]: [o for o in orders if item.compat(c, o)] for c in coils}

    y = {}
    for c in coils:
        ck = P.class_key(c)
        for p in range(len(class_pats[ck])):
            y[c["id"], p] = s.NumVar(0, 1, f"y{c['id']}_{p}")
        if class_pats[ck]:
            s.Add(sum(y[c["id"], p] for p in range(len(class_pats[ck]))) == 1)

    route = {}
    for c in coils:
        for o in comp[c["id"]]:
            route[c["id"], o["id"]] = s.NumVar(0, c["weight_g"], f"rt{c['id']}_{o['id']}")

    for c in coils:
        cid = c["id"]
        ck = P.class_key(c)
        W = c["width_cdmm"]
        pats = class_pats[ck]
        widths = {o["width_cdmm"] for o in comp[cid]}
        for cnt, _, _ in pats:
            widths.update(cnt)
        for a in widths:
            prod = s.Sum([y[cid, p] * (cnt.get(a, 0) * a * c["weight_g"] / W)
                          for p, (cnt, _, _) in enumerate(pats) if cnt.get(a, 0)])
            dests = [o for o in comp[cid] if o["width_cdmm"] == a]
            if dests:
                s.Add(s.Sum([route[cid, o["id"]] for o in dests]) == prod)

    cust, inv, dem_ct = {}, {}, {}
    by_order = defaultdict(list)
    for c in coils:
        for o in comp[c["id"]]:
            by_order[o["id"]].append(c)
    obj = []
    for o in orders:
        oid = o["id"]
        if oid not in by_order:
            continue
        cust[oid] = s.NumVar(0, o["qty_g"], f"cu{oid}")
        inv[oid] = s.NumVar(0, sum(c["weight_g"] for c in by_order[oid]), f"in{oid}")
        s.Add(s.Sum([route[c["id"], oid] for c in by_order[oid]])
              == cust[oid] + inv[oid])
        dc = s.Add(cust[oid] <= o["qty_g"])
        dem_ct[oid] = dc
        obj.append(o["rate_per_kg"] * cust[oid])
        obj.append(o["rate_per_kg"] * HOLDING * inv[oid])

    for c in coils:
        cid = c["id"]
        ck = P.class_key(c)
        W = c["width_cdmm"]
        for p, (cnt, scrap, asis) in enumerate(class_pats[ck]):
            obj.append(SCRAP_RATE * (scrap * c["weight_g"] / W) * y[cid, p])
            if not asis:
                obj.append(-SLIT_COST * c["weight_g"] * y[cid, p])
        obj.append(-int(round(c["price_per_kg"])) * c["weight_g"])
    s.Maximize(s.Sum(obj))
    return s, dem_ct, cust


def column_generation(coils, orders, verbose=True):
    by_class = defaultdict(list)
    for c in coils:
        by_class[P.class_key(c)].append(c)
    class_usable, class_pats = {}, {}
    for ck, cs in by_class.items():
        rep = cs[0]
        usable = sorted({o["width_cdmm"] for o in orders if item.compat(rep, o)},
                        reverse=True)
        class_usable[ck] = usable
        class_pats[ck] = seed_patterns(rep["width_cdmm"], usable, KNIFE_MAX) if usable else []

    for rnd in range(MAX_ROUNDS):
        s, dem_ct, _ = build_master(coils, orders, class_pats)
        st = s.Solve()
        if st not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            if verbose:
                print(f"  round {rnd}: master LP status {st}, stop")
            break
        # demand dual = marginal value of one more kg to that order
        pi = {}
        for oid, ct in dem_ct.items():
            try:
                pi[oid] = ct.dual_value()
            except Exception:
                pi[oid] = 0.0
        added = 0
        for ck, cs in by_class.items():
            rep = cs[0]
            W = rep["width_cdmm"]
            usable = class_usable[ck]
            if not usable:
                continue
            # marginal rs/kg worth of width a = best compat order's (rate - pi) ,
            # floored at inventory value 0.95*rate (pi small => near rate)
            vbar = {}
            for a in usable:
                best = 0.0
                for o in orders:
                    if o["width_cdmm"] == a and item.compat(rep, o):
                        r = o["rate_per_kg"]
                        v = max(r - pi.get(o["id"], 0.0), HOLDING * r)
                        best = max(best, v)
                vbar[a] = best
            val = {a: a * vbar[a] for a in usable}  # value of one strip of width a
            cand = knapsack_pattern(W, usable, val, KNIFE_MAX, min(usable))
            if cand is None:
                continue
            key = (tuple(sorted(cand[0].items())), cand[2])
            existing = {(tuple(sorted(cn.items())), aa)
                        for cn, _, aa in class_pats[ck]}
            if key not in existing and len(class_pats[ck]) < PATTERN_CAP:
                class_pats[ck].append(cand)
                added += 1
        if verbose:
            tot = sum(len(v) for v in class_pats.values())
            print(f"  round {rnd}: LP obj rs{s.Objective().Value()/1:,.0f}, "
                  f"+{added} patterns (total {tot})")
        if added == 0:
            break
    return class_pats


def run(lot_label, coils, orders):
    for i, c in enumerate(coils):
        c["id"] = i
    t = time.time()
    cps = column_generation(coils, orders)
    gen_t = time.time() - t
    res = P.solve(coils, orders, patterns_by_class=cps)
    npat = sum(len(v) for v in cps.values())
    print(f"  [CG] {len(cps)} classes, {npat} patterns, gen {gen_t:.1f}s")
    return P.report(lot_label, coils, orders, res)


def main():
    coils = item.load_auction(item.AUCTION_CSV)
    orders = item.load_customers(item.CUSTOMER_CSV)
    by_lot = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)

    print("VALIDATION — Lot 274049: CG vs item model (must match profit)\n")
    cg_profit = run("274049", [dict(c) for c in by_lot["274049"]], orders)
    lc = [dict(c) for c in by_lot["274049"]]
    for i, c in enumerate(lc):
        c["id"] = i
    item.report("274049", lc, orders, item.solve(lc, orders), show_plan=False)
    print(f"\nCROSS-CHECK: CG profit rs{cg_profit:,.0f} vs item PROFIT line above\n")

    print("ALL LOTS [CG]\n")
    for lot in sorted(by_lot):
        run(lot, [dict(c) for c in by_lot[lot]], orders)


if __name__ == "__main__":
    main()
