"""
Parallel runner for the item-model slitting optimizer.

The 5 auction lots are independent optimization problems. Solving them in a
self-balancing process pool collapses wall time from sum(lot times) (~15 min
sequential) to ~max(lot time) (~5 min) — the slow master lots overlap instead
of queuing, and trivial lots (274053=0s) free their pool slot for the queue.

Per-lot solve is byte-for-byte the validated item model — only orchestration
changes. Sequential prototype_slitting_optimizer.py is left intact.

Runtime-dynamic core allocation (no hardcoding):
    cores            = os.cpu_count()
    usable           = max(1, cores - 1)            # leave 1 for OS/main
    parallel         = min(n_lots, max(1, usable // 2))   # >=2 workers/lot floor
    workers_per_lot  = min(8, max(1, usable // parallel)) # 8 = CP-SAT plateau

Run:
    conda activate slitting_opt
    python prototype_slitting_parallel.py
    SLIT_TIME_LIMIT=20 python prototype_slitting_parallel.py   # quick smoke test
"""

import io
import os
import time
import contextlib
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

from engine import optimizer as item


def _solve_lot(payload):
    """Runs in a worker process. Returns (lot, captured_report_text, wall_s).
    CP-SAT objects never cross the process boundary — only the formatted text."""
    lot, lot_coils, orders, n_workers = payload
    for i, c in enumerate(lot_coils):
        c["id"] = i
    t = time.time()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = item.solve(lot_coils, orders, n_workers=n_workers)
        item.report(lot, lot_coils, orders, res, show_plan=True)
    return lot, buf.getvalue(), time.time() - t


def main():
    coils = item.load_auction(item.AUCTION_CSV)
    orders = item.load_customers(item.CUSTOMER_CSV)
    by_lot = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)
    lots = sorted(by_lot)
    n_lots = len(lots)

    cores = os.cpu_count() or 4
    usable = max(1, cores - 1)
    parallel = min(n_lots, max(1, usable // 2))
    workers_per_lot = min(8, max(1, usable // parallel))

    print(f"cores={cores}  lots={n_lots}  ->  parallel={parallel}  "
          f"workers/lot={workers_per_lot}  (time limit "
          f"{item.SOLVE_TIME_LIMIT_S}s/lot)\n")

    item.diagnostic(coils, orders)  # cheap; run once in main

    payloads = [(lot, [dict(c) for c in by_lot[lot]], orders, workers_per_lot)
                for lot in lots]

    wall0 = time.time()
    texts = {}
    with ProcessPoolExecutor(max_workers=parallel) as ex:
        for lot, text, lot_s in ex.map(_solve_lot, payloads):
            texts[lot] = text
            print(f"  [done] lot {lot} in {lot_s:.1f}s", flush=True)
    total = time.time() - wall0

    print("\n" + "=" * 100)
    print("PER-LOT RESULTS (parallel)")
    print("=" * 100 + "\n")
    for lot in lots:
        print(texts[lot], end="")

    print(f"\nTotal wall time (parallel): {total:.1f}s across {parallel} workers "
          f"x {workers_per_lot} threads.")


if __name__ == "__main__":
    main()
