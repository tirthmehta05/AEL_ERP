# Bug Fix Plan: Weight Receipt "Set" Count Shows 1 Instead of Actual Sets

## Root Cause

**File:** `pages/weight_receipt.py`, lines 479–480

In the `else` branch (non-CORE_BUILDING orders like Loose Strips), `sets_for_this_receipt`
is **hardcoded to `1`**:

```python
sets_for_this_receipt = 1
sets_for_this_receipt = 1   # duplicate, clearly a mistake
```

This value is immediately written to session state at line 491:
```python
st.session_state.wr_sets_for_receipt = sets_for_this_receipt  # always 1
```

When the receipt is saved (line 819), it reads from session state:
```python
sets=st.session_state.get('wr_sets_for_receipt', 0),  # always 1
```

So the receipt record is persisted with `Sets=1` regardless of how many sets the
user entered per-design in Itemized Mode (e.g., 3 sets per design).

The PDF summary row at `pdf_service.py:838` reads this stored value directly:
```python
pdf.cell(set_w, 8, f"Set: {receipt_data.get('Sets', 'N/A')}", ...)
```
→ Prints `Set: 1`, when the correct value is `3`.

Meanwhile, the individual line-item descriptions correctly show "(3 sets)" because
they read from per-design `item.get('sets')` in `WeighedDesignDetail`.

## Data Flow Summary

```
User enters "3" in Sets column (per-design, Itemized Mode)
  ↓ stored in st.session_state.wr_design_sets[idx] = 3

sets_for_this_receipt = 1  ← hardcoded BUG
  ↓
st.session_state.wr_sets_for_receipt = 1
  ↓
WeightReceiptRequest(sets=1, ...)  ← saved to sheet
  ↓
PDF: "Set: 1"  ← wrong
```

## Fix

**Location:** `pages/weight_receipt.py`, just before the `WeightReceiptRequest` instantiation
(around line ~810, in the Loose Strips save block)

Derive receipt-level `sets` from the individual `weighed_designs` when in itemized mode,
instead of using the hardcoded-to-1 session state value:

```python
# Compute receipt-level sets from per-design sets in itemized mode
if is_itemized_mode and weighed_designs:
    design_sets_vals = [d.sets for d in weighed_designs if d.sets is not None]
    receipt_sets = max(design_sets_vals) if design_sets_vals else st.session_state.get('wr_sets_for_receipt', 0)
else:
    receipt_sets = st.session_state.get('wr_sets_for_receipt', 0)
```

Then change line 819:
```python
# Before:
sets=st.session_state.get('wr_sets_for_receipt', 0),
# After:
sets=receipt_sets,
```

## Files to Change

1. **`pages/weight_receipt.py`** — One targeted change at save time in the Loose Strips block

## No Changes Needed

- `src/pdf_generator/service/pdf_service.py` — PDF correctly reads `receipt_data.get('Sets')`; fix is upstream
- `src/data_entry/service/weight_receipt_service.py` — No change needed
- `src/data_entry/models/weight_receipt_models.py` — No change needed
