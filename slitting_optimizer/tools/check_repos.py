"""Prove the new repository layer produces engine-IDENTICAL data.

Mirrors the project's "prove equivalence before trusting it" discipline:

  auction_repository.parse_auction(CRNO .xlsx)
      must equal  engine.optimizer.load_auction("Auction Built.csv")

  customer_repository.parse_customers(sample_customers.xlsx)
      must equal  engine.optimizer.load_customers("Customer Built.csv")

If these match, the service feeds the validated engine exactly what the
39/39-proven path fed it — only the input *format* changed, not the data.

Run:  python -m tools.check_repos
"""

from __future__ import annotations

from pathlib import Path

from engine import optimizer as eng
from app.repository import auction_repository as ar
from app.repository import customer_repository as cr
from tools import make_sample_customer_workbook as mk

ERP = Path("/Users/tirthmehta/Documents/Personal Files/Amba/AEL ERP/"
           "AEL_ERP_V1/AEL_ERP")
CRNO_XLSX = ERP / "CRNO 11.4.2026.xlsx"
AUCTION_CSV = ERP / "Slitting Plan Optimization - Auction Built.csv"
CUSTOMER_CSV = ERP / "Slitting Plan Optimization - Customer Built.csv"

_fail = 0


def _check(name, ok, detail=""):
    global _fail
    mark = "PASS" if ok else "FAIL"
    if not ok:
        _fail += 1
    print(f"  [{mark}] {name}" + (f"  --  {detail}" if detail else ""))


def _coil_key(c):
    return (c["lot"], c["batch"], c["width_cdmm"], c["weight_g"],
            round(c["price_per_kg"], 6), c["grade"], c["coating"],
            c["thickness"])


def _order_key(o):
    return (o["customer"], o["width_cdmm"], o["qty_g"], o["monthly_g"],
            o["rate_per_kg"], frozenset(o["grades"]),
            frozenset(o["coatings"]), frozenset(o["thicknesses"]),
            o["min_coil_g"])


def main():
    print("REPOSITORY EQUIVALENCE CHECK")

    # ---- auction: xlsx parser vs validated CSV loader ----
    coils, aflags = ar.parse_auction(CRNO_XLSX)
    base_coils = eng.load_auction(AUCTION_CSV)
    _check("auction: coil count matches validated CSV",
           len(coils) == len(base_coils),
           f"xlsx={len(coils)} csv={len(base_coils)}")
    _check("auction: coil multiset identical to validated CSV",
           sorted(map(_coil_key, coils)) == sorted(map(_coil_key, base_coils)))
    print(f"    lots={sorted({c['lot'] for c in coils})}  "
          f"flags={len(aflags)}")
    for f in aflags[:6]:
        print(f"      - {f}")

    # ---- customers: new workbook parser vs validated CSV loader ----
    mk.main()  # build data/sample_customers.xlsx from the validated CSV
    orders, cflags = cr.parse_customers(mk.OUT)
    base_orders = eng.load_customers(CUSTOMER_CSV)
    _check("customers: order count matches validated CSV",
           len(orders) == len(base_orders),
           f"xlsx={len(orders)} csv={len(base_orders)}")
    _check("customers: order multiset identical to validated CSV",
           sorted(map(_order_key, orders))
           == sorted(map(_order_key, base_orders)))
    print(f"    customers={len(set(o['customer'] for o in orders))}  "
          f"flags={len(cflags)}")
    for f in cflags[:6]:
        print(f"      - {f}")

    print(f"\nRESULT: {'ALL PASS' if not _fail else f'{_fail} FAILED'}")
    raise SystemExit(1 if _fail else 0)


if __name__ == "__main__":
    main()
