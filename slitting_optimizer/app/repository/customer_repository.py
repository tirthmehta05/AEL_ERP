"""Parse the customer-requirement workbook → engine-ready order dicts.

Format (locked with the user): ONE workbook, ONE tab per customer (tab name =
customer). Each row is one spec line. Columns (header row, order-insensitive,
name-tolerant):

  Width(mm) | MonthlyQty(MT) | Rate(₹/kg) | Grades | Coatings |
  Thickness(mm) | MinCoilQty(kg) | Notes

Width(mm) accepts two forms:
  - Single number (e.g. "60") → SLIT mode: strip cut to exactly that width
  - Range "MIN-MAX" (e.g. "1000-1650") → ASIS mode: whole coil if width ∈ [MIN, MAX]

Grades / Coatings / Thickness are EXPLICIT pipe-separated accepted values —
no substitution-ladder logic, no defaults. What is typed is what is matched.
`MonthlyQty` is the monthly run-rate: it sets both demand and the holding-
slice width in the validated engine, so qty_g == monthly_g.

Output order dicts match engine.optimizer.load_customers exactly.
"""

from __future__ import annotations

import pandas as pd

from engine import optimizer as eng

# normalized-header keyword → canonical field
_HEADER_MAP = {
    "width": "width",
    "monthlyqty": "monthlyqty", "monthly": "monthlyqty", "qty": "monthlyqty",
    "quantity": "monthlyqty",
    "rate": "rate",
    "grade": "grades", "grades": "grades",
    "coating": "coatings", "coatings": "coatings",
    "thickness": "thickness", "thk": "thickness",
    "mincoil": "mincoilqty", "mincoilqty": "mincoilqty",
    "minweight": "mincoilqty",
    "note": "notes", "notes": "notes",
}
_REQUIRED = {"width", "monthlyqty", "rate", "grades", "coatings", "thickness"}


def _norm(h) -> str:
    return "".join(ch for ch in str(h).lower() if ch.isalnum())


def _resolve_columns(df) -> dict[str, object]:
    """canonical field -> actual df column label (best match)."""
    out: dict[str, object] = {}
    for col in df.columns:
        n = _norm(col)
        for key, field in _HEADER_MAP.items():
            if n == key or n.startswith(key):
                out.setdefault(field, col)
                break
    return out


def _pipes(v) -> set[str]:
    if v is None or (isinstance(v, float) and v != v):  # NaN
        return set()
    return {p.strip() for p in str(v).split("|") if p.strip()}


def _parse_width(v):
    """Detect single-value (slit) vs range (asis) Width spec.
    Returns (mode, width_cdmm, width_min_cdmm, width_max_cdmm). For slit mode,
    width_min/max are None. For asis mode, width_cdmm = 0 (unused)."""
    s = str(v).strip()
    if "-" in s:
        parts = [p.strip() for p in s.split("-")]
        if len(parts) != 2:
            raise ValueError(f"width '{s}' has more than one dash")
        try:
            lo, hi = float(parts[0]), float(parts[1])
        except (ValueError, TypeError):
            raise ValueError(f"width range '{s}' has non-numeric bounds")
        if lo > hi:
            raise ValueError(f"width range '{s}' has min > max")
        if lo == hi:
            # treat as single value
            return ("slit", int(round(lo * eng.WIDTH_SCALE)), None, None)
        return ("asis", 0,
                int(round(lo * eng.WIDTH_SCALE)),
                int(round(hi * eng.WIDTH_SCALE)))
    return ("slit", int(round(float(s) * eng.WIDTH_SCALE)), None, None)


def parse_customers(path) -> tuple[list[dict], list[str]]:
    """Return (orders, flags) from an .xlsx workbook path.

    Thin wrapper: reads every tab into a {tab_name: DataFrame} dict and
    delegates to parse_customer_frames. Kept for the CLI / tests / any
    file-based flow. The ERP page reads from Google Sheets instead (so the
    secret customer data never lives in the repo) and calls
    parse_customer_frames directly — see pages/bid_optimizer.py."""
    sheets = pd.read_excel(path, sheet_name=None)
    return parse_customer_frames(sheets)


def parse_customer_frames(sheets: dict) -> tuple[list[dict], list[str]]:
    """Return (orders, flags) from a {tab_name: DataFrame} mapping.

    Source-agnostic core: works identically whether the frames came from an
    .xlsx (pd.read_excel) or from Google Sheets. One tab per customer; each
    row is one spec line. Orders carry sequential ids across all tabs."""
    orders: list[dict] = []
    flags: list[str] = []
    oid = 0

    for tab, df in sheets.items():
        customer = str(tab).strip()
        if df.empty:
            continue
        cols = _resolve_columns(df)
        missing = _REQUIRED - cols.keys()
        if missing:
            flags.append(f"tab '{customer}' skipped — missing column(s): "
                         f"{sorted(missing)}")
            continue

        for i, r in df.iterrows():
            w, q, rate = r[cols["width"]], r[cols["monthlyqty"]], r[cols["rate"]]
            if pd.isna(w) or pd.isna(q) or pd.isna(rate):
                continue  # blank / spacer row
            try:
                mode, width_cdmm, w_min, w_max = _parse_width(w)
                qty_mt = float(q)
                rate_kg = int(round(float(rate)))
            except (ValueError, TypeError) as e:
                flags.append(f"{customer} row {i + 2}: {e} — skipped")
                continue

            # Lowercase grades for exact-string match against coil grades
            # (the auction parser lowercases on its side too). Customer files
            # should use the Thickness+C+Grade form ("50c600"); run
            # tools.migrate_customer_grades on legacy files first.
            grades = {g.lower() for g in _pipes(r[cols["grades"]])}
            coatings = _pipes(r[cols["coatings"]])
            ths = {eng._thk(float(t)) for t in _pipes(r[cols["thickness"]])}
            if not (grades and coatings and ths):
                flags.append(f"{customer} row {i + 2}: empty grades/"
                             f"coatings/thickness — skipped")
                continue
            min_kg = 0.0
            if "mincoilqty" in cols and not pd.isna(r[cols["mincoilqty"]]):
                try:
                    min_kg = float(r[cols["mincoilqty"]])
                except (ValueError, TypeError):
                    min_kg = 0.0

            qty_g = int(round(qty_mt * eng.MT_TO_GRAMS))
            orders.append({
                "id": oid,
                "customer": customer,
                "mode": mode,                # "slit" or "asis"
                "width_cdmm": width_cdmm,    # slit: exact strip width; asis: 0
                "width_min_cdmm": w_min,     # asis only
                "width_max_cdmm": w_max,     # asis only
                "qty_g": qty_g,
                "monthly_g": qty_g,        # monthly run-rate (validated model)
                "rate_per_kg": rate_kg,
                "grades": grades,
                "coatings": coatings,
                "thicknesses": ths,
                "min_coil_g": int(round(min_kg * 1000)),
            })
            oid += 1

    if not orders:
        flags.append("No customer rows parsed — check the workbook has one "
                     "tab per customer with the expected header row.")
    return orders, flags
