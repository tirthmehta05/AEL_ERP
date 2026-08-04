"""Build a copy-paste AI prompt for drafting a card, and parse the reply back.

Deliberately no API call. The manager copies the prompt into Copilot or
ChatGPT, pastes the answer back, and remains the author — which keeps
performance data out of a third-party API, needs no key or cost approval, and
leaves the accountability where it belongs.

What the prompt is for and what it is not for:

* **For** — sharpening wording, making a vague goal measurable, naming the
  evidence that would prove a knowledge goal, checking a KPI is within the
  person's authority.
* **Not for** — inventing target numbers. Those cascade from the Scaling
  Plan's Monthly Targets and the published business needs. The prompt says
  so explicitly, because a plausible-looking invented target is the most
  damaging thing a model could contribute here.

The reply comes back as TSV. Parsing reattaches `lineage_id` for items the
manager kept, so an AI-assisted rewrite does not silently break the
month-over-month trend of an existing KPI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from src.performance.models.performance_models import (
    AccountabilityLayer,
    BusinessNeed,
    Direction,
    Employee,
    KBDItem,
    KPICardItem,
    OutcomeType,
    Pillar,
    Role,
    new_id,
)

RESULT_COLUMNS = [
    "pillar", "name", "direction", "unit", "target", "weight",
    "measurement_method", "data_source", "outcome_type",
    "accountability_layer",
]
KBD_COLUMNS = ["pillar", "text", "evidence_expected", "weight"]

VALUES = [
    "Integrity", "Ownership", "Customer First",
    "Quality Without Compromise", "Drive & Discipline", "Respect & Trust",
]


@dataclass
class ParsedDraft:
    result_items: list[KPICardItem] = field(default_factory=list)
    kbd_items: list[KBDItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    matched_lineage: int = 0

    @property
    def ok(self) -> bool:
        return bool(self.result_items or self.kbd_items) and not self.errors


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------


def build_prompt(
    employee: Employee,
    period: str,
    role: Optional[Role] = None,
    business_needs: Optional[list[BusinessNeed]] = None,
    previous_result: Optional[list[KPICardItem]] = None,
    previous_kbd: Optional[list[KBDItem]] = None,
    previous_actuals: Optional[dict[str, float]] = None,
    manager_name: str = "",
) -> str:
    """Assemble the full prompt. Pure string building — safe to unit test."""
    needs = business_needs or []
    actuals = previous_actuals or {}

    parts: list[str] = []
    parts.append(
        f"You are helping a manager at Amba Enterprises Limited write a "
        f"monthly performance card for one of their team, for {period}.\n"
    )

    parts.append("## The person\n")
    parts.append(
        f"- Name: {employee.name}\n"
        f"- Designation: {employee.designation or employee.level}\n"
        f"- Level: {employee.level}\n"
        f"- Department: {employee.department or 'n/a'}\n"
        f"- Manager: {manager_name or 'n/a'}\n"
    )

    if role and role.primary_ownership:
        parts.append(f"\n### What this role owns\n{role.primary_ownership}\n")
    if role and role.not_responsible_for:
        parts.append(
            f"\n### What this role is NOT accountable for\n"
            f"{role.not_responsible_for}\n"
            "Do not propose a KPI that falls in this list.\n"
        )

    result_needs = [n for n in needs if n.pillar == Pillar.RESULT.value]
    if result_needs:
        parts.append(f"\n## What the company needs in {period}\n")
        for need in result_needs:
            target = f" — target {need.target}" if need.target else ""
            unit = f" {need.unit}" if need.unit else ""
            note = f" ({need.note})" if need.note else ""
            parts.append(f"- [{need.need_id}] {need.area}: {need.metric}{target}{unit}{note}\n")
        parts.append(
            "\nWhere a KPI cascades from one of these, put its reference "
            "(e.g. BN-1) in the business_need_ref column.\n"
        )

    parts.append(_previous_section(previous_result, previous_kbd, actuals))

    parts.append(f"""
## The rules

**Result pillar (60% of the score)**
- Between 3 and 6 KPIs. Weights are whole numbers totalling exactly 100.
- No single KPI above 40% or below 10%.
- At least 60% of weight on Outcome or Output KPIs, not Activity.
- `direction` is one of: {', '.join(d.value for d in Direction)}.
  Use `lower` for anything where a smaller number is better — scrap rate,
  DSO, downtime, lead time, error counts. This matters: achievement is
  computed as target/actual for these, and getting it wrong scores a missed
  target as an overachievement.
- Every KPI needs a measurement_method (one line, how it is computed) and a
  data_source (where the number actually comes from at month end).
- `outcome_type` is one of: {', '.join(o.value for o in OutcomeType)}.
- `accountability_layer` is one of: {', '.join(l.value for l in AccountabilityLayer)}.
  Assign it honestly — a person is only accountable for what they have the
  authority, tools, information and training to control. If the KPI depends
  mostly on someone else's work, it belongs on that person's card.

**Knowledge (20%)** — 1 to 3 learning goals. Each must state the evidence
that would prove it was achieved at month end ("what will you show me?").
Avoid goals that cannot be demonstrated.

**Behaviour (10%)** — rated against Amba's six values:
{', '.join(VALUES)}.

**Discipline (10%)** — attendance and punctuality, end-of-day reporting,
SOP adherence, data accuracy and timeliness, review-rhythm compliance.

## Critical constraint on targets

Do NOT invent target numbers. Targets cascade from the company's Monthly
Targets and the business needs listed above. Where you do not have a number,
put `?` in the target column and say in your notes what the manager needs to
look up. A plausible-looking invented target is worse than a blank one.

## What I want from you

1. A short critique of last month's card: which KPIs are vague, unmeasurable,
   outside this person's control, or measuring activity rather than result.
2. A revised card as two TSV blocks, exactly in the formats below, with a
   header row and tab separators. No markdown table pipes, no extra commentary
   inside the blocks.

```
RESULT
{chr(9).join(RESULT_COLUMNS)}
Result{chr(9)}<name>{chr(9)}higher{chr(9)}tonnes{chr(9)}80{chr(9)}30{chr(9)}<how measured>{chr(9)}<source>{chr(9)}outcome{chr(9)}L1 Execution
```

```
KBD
{chr(9).join(KBD_COLUMNS)}
Knowledge{chr(9)}<goal>{chr(9)}<evidence that proves it>{chr(9)}1
Behaviour{chr(9)}<value or focus>{chr(9)}{chr(9)}1
Discipline{chr(9)}<expectation>{chr(9)}{chr(9)}1
```

3. Anything you changed and why, in two or three lines.

Keep the language plain and specific to steel manufacturing and trading.
Avoid corporate filler.
""")
    return "".join(parts)


def _previous_section(
    previous_result: Optional[list[KPICardItem]],
    previous_kbd: Optional[list[KBDItem]],
    actuals: dict[str, float],
) -> str:
    if not previous_result and not previous_kbd:
        return (
            "\n## Last month\n"
            "No previous card — this is the first month for this person.\n"
        )

    lines = ["\n## Last month's card, with how it went\n"]
    if previous_result:
        lines.append("\n**Result KPIs**\n\n")
        lines.append("| KPI | Direction | Target | Actual | Achieved | Weight |\n")
        lines.append("|---|---|---|---|---|---|\n")
        for item in previous_result:
            actual = actuals.get(item.lineage_id)
            achieved = _achievement_text(item, actual)
            actual_text = "—" if actual is None else f"{actual:g}"
            target_text = "—" if item.target is None else f"{item.target:g}"
            lines.append(
                f"| {item.name} | {item.direction} | {target_text} {item.unit} "
                f"| {actual_text} | {achieved} | {item.weight:g}% |\n"
            )
    if previous_kbd:
        lines.append("\n**Knowledge / Behaviour / Discipline**\n\n")
        for item in previous_kbd:
            evidence = f" (evidence: {item.evidence_expected})" if item.evidence_expected else ""
            lines.append(f"- {item.pillar}: {item.text}{evidence}\n")

    lines.append(
        "\nKeep what is still the right measure — reuse is fine and expected. "
        "Change what is not.\n"
    )
    return "".join(lines)


def _achievement_text(item: KPICardItem, actual: Optional[float]) -> str:
    if actual is None or item.target is None:
        return "—"
    try:
        if item.direction == Direction.LOWER.value:
            if actual == 0:
                return "120%"
            ratio = item.target / actual
        else:
            if item.target == 0:
                return "—"
            ratio = actual / item.target
    except ZeroDivisionError:
        return "—"
    return f"{min(120.0, ratio * 100):.0f}%"


# --------------------------------------------------------------------------
# Parsing the reply
# --------------------------------------------------------------------------


def parse_draft(
    text: str,
    card_id: str,
    existing_result: Optional[list[KPICardItem]] = None,
    existing_kbd: Optional[list[KBDItem]] = None,
) -> ParsedDraft:
    """Read the TSV blocks back into card items.

    Items whose name (or text) matches something already on the card inherit
    its `lineage_id`, so an AI-assisted rewrite keeps the trend history of a
    KPI the manager intended to keep.
    """
    draft = ParsedDraft()
    if not text or not text.strip():
        draft.errors.append("Nothing pasted.")
        return draft

    result_rows = _extract_block(text, "RESULT", RESULT_COLUMNS)
    kbd_rows = _extract_block(text, "KBD", KBD_COLUMNS)

    if not result_rows and not kbd_rows:
        draft.errors.append(
            "No RESULT or KBD block found. Paste the whole reply, including "
            "the header rows, and make sure columns are tab-separated."
        )
        return draft

    lineage_by_name = {
        _key(item.name): item.lineage_id for item in (existing_result or [])
    }
    lineage_by_text = {
        (item.pillar, _key(item.text)): item.lineage_id
        for item in (existing_kbd or [])
    }

    for index, row in enumerate(result_rows):
        item, error = _build_result_item(row, card_id, index, lineage_by_name)
        if error:
            draft.errors.append(f"Result row {index + 1}: {error}")
        elif item:
            if _key(item.name) in lineage_by_name:
                draft.matched_lineage += 1
            draft.result_items.append(item)

    for index, row in enumerate(kbd_rows):
        item, error = _build_kbd_item(row, card_id, index, lineage_by_text)
        if error:
            draft.errors.append(f"KBD row {index + 1}: {error}")
        elif item:
            if (item.pillar, _key(item.text)) in lineage_by_text:
                draft.matched_lineage += 1
            draft.kbd_items.append(item)

    return draft


def _extract_block(text: str, marker: str, columns: list[str]) -> list[dict[str, str]]:
    """Pull tab-separated rows following a block marker.

    Tolerant by design: models wrap output in code fences, add stray blank
    lines, or repeat the header. Rejecting the paste over formatting would
    just push the manager back to typing it by hand.
    """
    lines = [line.rstrip("\r") for line in text.splitlines()]
    rows: list[dict[str, str]] = []
    collecting = False

    for line in lines:
        stripped = line.strip().strip("`").strip()
        if not collecting:
            if stripped.upper() == marker:
                collecting = True
            continue

        if not stripped:
            continue
        if stripped.upper() in {"RESULT", "KBD"} and stripped.upper() != marker:
            break
        if stripped.startswith("#") or stripped.startswith("```"):
            if rows:
                break
            continue

        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) < 2:
            # Fall back to a markdown table row if the model used pipes.
            if "|" in line:
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
            else:
                if rows:
                    break
                continue
        if all(re.fullmatch(r"[-:\s]*", cell) for cell in cells):
            continue    # markdown separator row
        if _key(cells[0]) == _key(columns[0]) and _key(cells[1]) == _key(columns[1]):
            continue    # header row

        row = {columns[i]: cells[i] if i < len(cells) else ""
               for i in range(len(columns))}
        rows.append(row)

    return rows


def _build_result_item(
    row: dict[str, str], card_id: str, seq: int, lineage_by_name: dict[str, str]
) -> tuple[Optional[KPICardItem], str]:
    name = row.get("name", "").strip()
    if not name:
        return None, "no KPI name"

    direction = _match_enum(row.get("direction", ""), Direction, Direction.HIGHER)
    outcome = _match_enum(row.get("outcome_type", ""), OutcomeType, OutcomeType.OUTCOME)
    layer = _match_layer(row.get("accountability_layer", ""))

    return KPICardItem(
        card_id=card_id,
        lineage_id=lineage_by_name.get(_key(name), new_id("LIN")),
        seq=seq,
        source="custom",
        change_type="added",
        name=name,
        direction=direction,
        unit=row.get("unit", "").strip(),
        target=_number(row.get("target", "")),
        weight=_number(row.get("weight", "")) or 0.0,
        measurement_method=row.get("measurement_method", "").strip(),
        data_source=row.get("data_source", "").strip(),
        business_need_ref=row.get("business_need_ref", "").strip(),
        accountability_layer=layer,
        outcome_type=outcome,
    ), ""


def _build_kbd_item(
    row: dict[str, str], card_id: str, seq: int,
    lineage_by_text: dict[tuple[str, str], str],
) -> tuple[Optional[KBDItem], str]:
    text = row.get("text", "").strip()
    if not text:
        return None, "no text"

    pillar = _match_pillar(row.get("pillar", ""))
    if pillar is None:
        return None, f"unrecognised pillar '{row.get('pillar', '')}'"

    weight = _number(row.get("weight", ""))
    return KBDItem(
        card_id=card_id,
        lineage_id=lineage_by_text.get((pillar, _key(text)), new_id("LIN")),
        seq=seq,
        pillar=pillar,
        source="custom",
        change_type="added",
        text=text,
        evidence_expected=row.get("evidence_expected", "").strip(),
        weight=1.0 if weight is None else weight,
    ), ""


def _key(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _number(text: str) -> Optional[float]:
    cleaned = str(text or "").strip().replace(",", "").replace("%", "")
    if not cleaned or cleaned in {"?", "-", "—", "n/a", "na", "tbd"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group()) if match else None


def _match_enum(text: str, enum_cls, default):
    key = _key(text)
    for member in enum_cls:
        if _key(member.value) == key:
            return member.value
    return default.value


def _match_layer(text: str) -> str:
    key = _key(text)
    for member in AccountabilityLayer:
        if _key(member.value) == key or key in _key(member.value):
            return member.value
    if key.startswith("l1") or "execution" in key:
        return AccountabilityLayer.EXECUTION.value
    if key.startswith("l2") or "supervis" in key:
        return AccountabilityLayer.SUPERVISION.value
    if key.startswith("l3") or "design" in key:
        return AccountabilityLayer.DESIGN.value
    return AccountabilityLayer.EXECUTION.value


def _match_pillar(text: str) -> Optional[str]:
    key = _key(text)
    for pillar in (Pillar.KNOWLEDGE, Pillar.BEHAVIOUR, Pillar.DISCIPLINE):
        if _key(pillar.value) == key or key.startswith(pillar.value[:4].lower()):
            return pillar.value
    return None
