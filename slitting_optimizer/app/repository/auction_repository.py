"""Parse the raw auction workbook (`CRNO <date>.xlsx`) into engine-ready coil
dicts + anomaly flags.

Authoritative input = the **summary "Lots" sheet** (the Steelemart auction
list). In production the user works only from that sheet; the per-lot
`Sheet1..N` are derived and may not exist. So we parse exactly one sheet — the
summary — which contains ALL lots as repeated `Lot No` / `Batch No` sections.

Produces coils in the EXACT shape the validated engine expects
(engine.optimizer.load_auction), so engine behaviour is identical to the
proven path — only the source (xlsx vs built CSV) differs.

Column layout:
  - lot value row: col0=lot#  col10=start price (₹/MT). Consistent.
  - coil row: column POSITIONS vary across lots in the same workbook
    (e.g. some sections include a `Major Defect` column, others don't).
    So we read the `Batch No` header row in each section and map columns
    by NAME — fragile-to-position-shift wisdom from Tirth, 2026-05-22.

  Header names we depend on (case-insensitive):
    Batch No, Thk, Width, Qty, Tin Temper, Insulation Type
  Note: JSW reuses tinplate-template columns for CRNO; "Tin Temper" carries
  the `<thk>C<grade>` designation (e.g. "50C1000"), and "Insulation Type"
  carries the coating (e.g. "C6L").
"""

from __future__ import annotations

import re
from collections import defaultdict

import pandas as pd

from engine import optimizer as eng

KNOWN_COATINGS = {"C5L", "C3L", "C3H", "C5H", "C6L"}
_GRADE_RE = re.compile(r"(\d+)\s*C\s*(\d+)")

# Header label (normalised: lower, stripped) → our internal field name.
_HEADER_FIELD = {
    "batch no": "batch",
    "thk": "thickness",
    "width": "width",
    "qty": "qty",
    "tin temper": "grade",        # JSW puts <thk>C<grade> here for CRNO
    "insulation type": "coating",  # JSW puts C5L/C6L/etc. here for CRNO
}
_REQUIRED_FIELDS = {"thickness", "width", "qty", "grade", "coating"}


def _norm(v) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip().lower()


def _build_coil_cmap(header_row) -> dict[str, int]:
    """{internal_field: col_idx} from a coil-section header row."""
    cmap: dict[str, int] = {}
    for col_idx in range(len(header_row)):
        name = _norm(header_row[col_idx])
        if name in _HEADER_FIELD:
            cmap.setdefault(_HEADER_FIELD[name], col_idx)
    return cmap


def _is_num(v) -> bool:
    try:
        f = float(v)
        return f == f  # reject NaN (NaN != NaN)
    except (ValueError, TypeError):
        return False


def _count_lot_headers(df) -> int:
    return int((df[0].astype(str).str.strip() == "Lot No").sum())


def _pick_summary_sheet(xls) -> tuple[str, list[str]]:
    """The summary sheet is the one listing ALL lots. Prefer a sheet literally
    named 'Lots'; else the sheet with the most `Lot No` sections (a per-lot
    sheet has exactly one). Tolerant to the exporter renaming the sheet."""
    flags: list[str] = []
    by_name = {s.strip().lower(): s for s in xls.sheet_names}
    if "lots" in by_name:
        return by_name["lots"], flags
    counts = {s: _count_lot_headers(pd.read_excel(xls, sheet_name=s,
                                                  header=None))
              for s in xls.sheet_names}
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        flags.append("No sheet contains a 'Lot No' section — unexpected "
                     "workbook layout.")
    elif sum(1 for v in counts.values() if v == counts[best]) > 1:
        flags.append(f"No 'Lots' sheet; multiple sheets tie on lot count — "
                     f"using '{best}'. Name the summary sheet 'Lots'.")
    else:
        flags.append(f"No 'Lots' sheet; using '{best}' (most lots).")
    return best, flags


def parse_auction(path) -> tuple[list[dict], list[str]]:
    """Return (coils, flags). One summary sheet, multiple lot sections."""
    xls = pd.ExcelFile(path)
    sheet, flags = _pick_summary_sheet(xls)
    df = pd.read_excel(xls, sheet_name=sheet, header=None)

    coils: list[dict] = []
    cid = 0
    lot_no = None
    start_price = None
    in_coils = False
    seen_lot_header = False
    cmap: dict[str, int] = {}        # current coil-section column map

    for _, r in df.iterrows():
        c0 = str(r[0]).strip() if not pd.isna(r[0]) else ""

        if c0 == "Lot No":                       # new lot section begins
            seen_lot_header = True
            in_coils = False
            continue
        if seen_lot_header and _is_num(r[0]):    # the lot's value row
            lot_no = str(int(float(r[0])))
            start_price = float(r[10]) if _is_num(r[10]) else None
            seen_lot_header = False
            if start_price is None:
                flags.append(f"lot {lot_no}: no start price (col10) — "
                             f"priced at 0")
            continue
        if c0 == "Batch No":
            in_coils = True
            cmap = _build_coil_cmap(r)
            missing = _REQUIRED_FIELDS - cmap.keys()
            if missing:
                flags.append(
                    f"lot {lot_no or '?'}: coil header missing column(s) "
                    f"{sorted(missing)} — section may be unparseable")
            continue

        if in_coils:
            if not cmap or not c0:
                in_coils = False
                continue
            try:
                thk_raw = r[cmap["thickness"]]
                width_raw = r[cmap["width"]]
                qty_raw = r[cmap["qty"]]
            except (IndexError, KeyError):
                in_coils = False
                continue
            if not (_is_num(thk_raw) and _is_num(width_raw)
                    and _is_num(qty_raw)):
                in_coils = False                 # blank / trailing summary
                continue
            if lot_no is None:
                flags.append(f"coil '{c0}' before any 'Lot No' — skipped")
                continue
            batch = c0
            thk = float(thk_raw)
            width = float(width_raw)
            qty = float(qty_raw)
            # Grade / coating may be missing if this section's header doesn't
            # carry those columns (some lot exports omit Insulation Type).
            # Treat as empty — the coil simply won't match any customer or
            # salvage rule, which is the safe failure mode.
            g_idx = cmap.get("grade")
            c_idx = cmap.get("coating")
            grade_raw = ""
            coating = ""
            if g_idx is not None and not pd.isna(r[g_idx]):
                grade_raw = str(r[g_idx]).strip()
            if c_idx is not None and not pd.isna(r[c_idx]):
                coating = str(r[c_idx]).strip()

            # Exact-string matching against customer grades (also lowercased).
            # The full form (e.g. "50c600") survives — keeps CRNO "50c600"
            # distinct from a CRGO "50cr600" so future material families don't
            # silently conflate. Auction format is *already* full form on disk.
            m = _GRADE_RE.match(grade_raw)
            if m:
                thk_from_grade = int(m.group(1)) / 100.0
                if abs(thk_from_grade - thk) > 1e-6:
                    flags.append(f"{batch}: thk col={thk} vs grade "
                                 f"'{grade_raw}'={thk_from_grade}")
            else:
                flags.append(f"{batch}: grade '{grade_raw}' not "
                             f"<thk>C<grade> form — kept raw")
            grade = grade_raw.strip().lower()

            if coating not in KNOWN_COATINGS:
                flags.append(f"{batch}: coating '{coating}' outside known "
                             f"{sorted(KNOWN_COATINGS)} — matches nobody")

            coils.append({
                "id": cid,
                "lot": lot_no,
                "batch": batch,
                "width_cdmm": int(round(width * eng.WIDTH_SCALE)),
                "weight_g": int(round(qty * eng.MT_TO_GRAMS)),
                "price_per_kg": (float(start_price) / 1000
                                 if start_price else 0.0),
                "grade": grade,
                "coating": coating,
                "thickness": eng._thk(thk),
            })
            cid += 1

    if not coils:
        flags.append("No coils parsed — is this the expected CRNO .xlsx "
                     "summary sheet ('Lot No' / 'Batch No' sections)?")
    return coils, flags


def summarize_lots(coils: list[dict]) -> list[dict]:
    """Per-lot aggregates for the parse preview."""
    by_lot: dict[str, list[dict]] = defaultdict(list)
    for c in coils:
        by_lot[c["lot"]].append(c)
    out = []
    for lot in sorted(by_lot):
        cs = by_lot[lot]
        ws = [c["width_cdmm"] / eng.WIDTH_SCALE for c in cs]
        out.append({
            "lot": lot,
            "coils": len(cs),
            "total_mt": round(sum(c["weight_g"] for c in cs)
                              / eng.MT_TO_GRAMS, 3),
            "start_price_per_kg": cs[0]["price_per_kg"],
            "width_range_mm": f"{min(ws):g}-{max(ws):g}",
            "grades": sorted({c["grade"] for c in cs}),
            "coatings": sorted({c["coating"] for c in cs}),
        })
    return out
