"""Build a realistic SAMPLE customer workbook in the new (locked) format from
the existing validated `Slitting Plan Optimization - Customer Built.csv`.

Read-only on the source CSV (in the ERP tree — untouched). Writes
`data/sample_customers.xlsx`: one tab per customer, columns:
  Width(mm) | MonthlyQty(MT) | Rate(₹/kg) | Grades | Coatings |
  Thickness(mm) | MinCoilQty(kg) | Notes

This gives a faithful test input without manual data entry. Real usage: the
user maintains this workbook directly.

Run:  python -m tools.make_sample_customer_workbook
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.core.config import REPO_ROOT

SRC = Path("/Users/tirthmehta/Documents/Personal Files/Amba/AEL ERP/"
           "AEL_ERP_V1/AEL_ERP/Slitting Plan Optimization - Customer Built.csv")
OUT = REPO_ROOT / "data" / "sample_customers.xlsx"

_INVALID = re.compile(r"[\[\]:*?/\\]")


def _safe_sheet(name: str, used: set[str]) -> str:
    s = _INVALID.sub("-", str(name)).strip()[:31] or "Customer"
    base, i = s, 1
    while s in used:
        suf = f"~{i}"
        s = base[:31 - len(suf)] + suf
        i += 1
    used.add(s)
    return s


def main() -> None:
    df = pd.read_csv(SRC)
    # Customer,Width,Quantity,Rate,Grades,Coatings,Thickness,MinCoilQty
    used: set[str] = set()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT, engine="openpyxl") as xl:
        for customer, g in df.groupby("Customer", sort=True):
            out = pd.DataFrame({
                "Width(mm)": g["Width"],
                "MonthlyQty(MT)": g["Quantity"],
                "Rate(₹/kg)": g["Rate"],
                "Grades": g["Grades"],
                "Coatings": g["Coatings"],
                "Thickness(mm)": g["Thickness"],
                "MinCoilQty(kg)": g.get("MinCoilQty", 0),
                "Notes": "",
            })
            out.to_excel(xl, sheet_name=_safe_sheet(customer, used),
                         index=False)
    print(f"Wrote {OUT}  ({df['Customer'].nunique()} customer tabs, "
          f"{len(df)} rows)")


if __name__ == "__main__":
    main()
