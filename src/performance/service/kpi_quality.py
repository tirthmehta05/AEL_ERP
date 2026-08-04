"""Card quality gate and scoring-remark rules.

Pure — no I/O, no Streamlit — so every rule is directly testable.

Because Amba deliberately did not adopt the workbook's yearly KPI freeze,
nothing else constrains what a manager writes on a card each month. This
module is therefore the primary quality control, and it runs live while the
manager edits rather than only at submit.

Three severities:

* **BLOCK** — submission is refused. Reserved for things that make the card
  arithmetically wrong or unscoreable.
* **WARN** — allowed, but routed into the management exception review. These
  are judgement calls, not errors; blocking them would push managers into
  gaming the rule rather than thinking.
* **INFO** — worth a look, no consequence.

On remarks: a 100-character floor stops one-word justifications but cannot
force substance, and padding defeats it. The duplicate and filler checks
raise that cost a little. What actually makes remarks real is that they are
shown verbatim in calibration and in the quarterly review, next to the score
they defend — the length rule just sets a floor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from src.performance.models.performance_models import (
    Direction,
    KBDItem,
    KPICardItem,
    OutcomeType,
    Pillar,
)


class Severity(str, Enum):
    BLOCK = "block"
    WARN = "warn"
    INFO = "info"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    field: str
    message: str
    lineage_id: str = ""

    @property
    def blocking(self) -> bool:
        return self.severity is Severity.BLOCK


# Defaults mirror the seeded `Parameters` rows; the caller passes the live
# values so the gate can be retuned without a deploy.
DEFAULTS: dict[str, float] = {
    "card.min_kpis": 3,
    "card.max_kpis": 6,
    "card.max_single_weight": 40,
    "card.min_single_weight": 10,
    "card.min_outcome_weight_pct": 60,
    "score.min_remark_chars": 100,
}

# A weight total this far from 100 is treated as a rounding artefact rather
# than a mistake, so a manager splitting 3 ways as 33/33/34 is not blocked.
WEIGHT_TOLERANCE = 0.01


def _param(params: Optional[dict[str, str]], key: str) -> float:
    if params and key in params:
        try:
            return float(str(params[key]).strip())
        except (TypeError, ValueError):
            pass
    return DEFAULTS[key]


# --------------------------------------------------------------------------
# Card composition
# --------------------------------------------------------------------------


def validate_card(
    result_items: list[KPICardItem],
    kbd_items: list[KBDItem],
    params: Optional[dict[str, str]] = None,
    business_need_refs: Optional[Iterable[str]] = None,
    carried_streak: Optional[dict[str, int]] = None,
) -> list[Finding]:
    """Check a whole card. Returns findings ordered BLOCK, WARN, INFO."""
    findings: list[Finding] = []
    findings += _validate_result_pillar(result_items, params, business_need_refs)
    findings += _validate_kbd_pillars(kbd_items, params)
    findings += _validate_staleness(result_items, kbd_items, carried_streak or {})

    order = {Severity.BLOCK: 0, Severity.WARN: 1, Severity.INFO: 2}
    return sorted(findings, key=lambda f: order[f.severity])


def _validate_result_pillar(
    items: list[KPICardItem],
    params: Optional[dict[str, str]],
    business_need_refs: Optional[Iterable[str]],
) -> list[Finding]:
    findings: list[Finding] = []
    min_kpis = int(_param(params, "card.min_kpis"))
    max_kpis = int(_param(params, "card.max_kpis"))

    if len(items) < min_kpis:
        findings.append(Finding(
            Severity.BLOCK, "result",
            f"A card needs at least {min_kpis} Result KPIs; this one has "
            f"{len(items)}.",
        ))
    if len(items) > max_kpis:
        findings.append(Finding(
            Severity.BLOCK, "result",
            f"A card may have at most {max_kpis} Result KPIs — the "
            f"Performance Master has {max_kpis} slots. This one has "
            f"{len(items)}.",
        ))

    if not items:
        return findings

    total_weight = sum(item.weight for item in items)
    if abs(total_weight - 100) > WEIGHT_TOLERANCE:
        findings.append(Finding(
            Severity.BLOCK, "result.weight",
            f"Result weights must total 100, not {total_weight:g}. The score "
            "is a weighted sum, so anything else silently scales everyone's "
            "result up or down.",
        ))

    max_single = _param(params, "card.max_single_weight")
    min_single = _param(params, "card.min_single_weight")

    for item in items:
        label = item.name or "(unnamed KPI)"

        if not item.name.strip():
            findings.append(Finding(
                Severity.BLOCK, "result.name",
                "Every KPI needs a name.", item.lineage_id,
            ))

        needs_target = item.direction in (Direction.HIGHER.value, Direction.LOWER.value,
                                          Direction.RANGE.value)
        if needs_target and item.target is None:
            findings.append(Finding(
                Severity.BLOCK, "result.target",
                f"'{label}' has no numeric target, so it cannot be scored.",
                item.lineage_id,
            ))
        if item.direction == Direction.LOWER.value and item.target == 0:
            findings.append(Finding(
                Severity.BLOCK, "result.target",
                f"'{label}' is lower-is-better with a target of zero. "
                "Achievement divides by the actual, and a zero target cannot "
                "be scored — use a small positive target instead.",
                item.lineage_id,
            ))
        if item.direction == Direction.RANGE.value and item.target_max is None:
            findings.append(Finding(
                Severity.BLOCK, "result.target",
                f"'{label}' is a range KPI but has no upper bound.",
                item.lineage_id,
            ))
        if (item.direction == Direction.RANGE.value and item.target is not None
                and item.target_max is not None and item.target_max < item.target):
            findings.append(Finding(
                Severity.BLOCK, "result.target",
                f"'{label}' has an upper bound below its lower bound.",
                item.lineage_id,
            ))

        if not item.direction:
            findings.append(Finding(
                Severity.BLOCK, "result.direction",
                f"'{label}' has no direction. Without it the score cannot "
                "tell a beaten target from a missed one.",
                item.lineage_id,
            ))
        if not item.data_source.strip():
            findings.append(Finding(
                Severity.BLOCK, "result.data_source",
                f"'{label}' has no data source. At scoring time nobody will "
                "know where the actual came from.",
                item.lineage_id,
            ))
        if not item.measurement_method.strip():
            findings.append(Finding(
                Severity.BLOCK, "result.measurement",
                f"'{label}' has no measurement method.", item.lineage_id,
            ))

        if item.weight > max_single:
            findings.append(Finding(
                Severity.WARN, "result.weight",
                f"'{label}' carries {item.weight:g}% of the card. Above "
                f"{max_single:g}% one metric dominates the month.",
                item.lineage_id,
            ))
        if 0 < item.weight < min_single:
            findings.append(Finding(
                Severity.WARN, "result.weight",
                f"'{label}' carries only {item.weight:g}%. Below "
                f"{min_single:g}% it cannot move the score enough to be worth "
                "tracking.",
                item.lineage_id,
            ))
        if item.weight <= 0:
            findings.append(Finding(
                Severity.BLOCK, "result.weight",
                f"'{label}' has no weight.", item.lineage_id,
            ))

    # Outcome balance — a card of pure activity measures effort, not results.
    min_outcome = _param(params, "card.min_outcome_weight_pct")
    outcome_weight = sum(
        item.weight for item in items
        if item.outcome_type in (OutcomeType.OUTCOME.value, OutcomeType.OUTPUT.value)
    )
    if total_weight > 0:
        share = outcome_weight / total_weight * 100
        if share < min_outcome:
            findings.append(Finding(
                Severity.WARN, "result.outcome_type",
                f"Only {share:.0f}% of weight sits on Outcome or Output KPIs "
                f"(target {min_outcome:.0f}%). The rest measures activity, "
                "which rewards effort rather than result.",
            ))

    refs = {ref for ref in (business_need_refs or []) if ref}
    if refs and not any(item.business_need_ref for item in items):
        findings.append(Finding(
            Severity.WARN, "result.business_need",
            "No KPI is linked to a published business need, so nothing on "
            "this card visibly cascades from what the company needs this "
            "month.",
        ))

    duplicates = _duplicate_names(item.name for item in items)
    for name in duplicates:
        findings.append(Finding(
            Severity.WARN, "result.name",
            f"'{name}' appears more than once. Two rows measuring the same "
            "thing double-count its weight.",
        ))
    return findings


def _validate_kbd_pillars(
    items: list[KBDItem], params: Optional[dict[str, str]]
) -> list[Finding]:
    findings: list[Finding] = []
    by_pillar: dict[str, list[KBDItem]] = {}
    for item in items:
        by_pillar.setdefault(item.pillar, []).append(item)

    for pillar in (Pillar.KNOWLEDGE, Pillar.BEHAVIOUR, Pillar.DISCIPLINE):
        pillar_items = by_pillar.get(pillar.value, [])
        if not pillar_items:
            findings.append(Finding(
                Severity.BLOCK, pillar.value.lower(),
                f"{pillar.value} has no items. It carries weight in the "
                "monthly score, so an empty pillar scores zero.",
            ))
            continue

        for item in pillar_items:
            if not item.text.strip():
                findings.append(Finding(
                    Severity.BLOCK, f"{pillar.value.lower()}.text",
                    f"A {pillar.value} item has no text.", item.lineage_id,
                ))
            if item.weight <= 0:
                findings.append(Finding(
                    Severity.BLOCK, f"{pillar.value.lower()}.weight",
                    f"'{item.text[:40] or 'item'}' has no weight.",
                    item.lineage_id,
                ))

        # Knowledge is the pillar a manager is most likely to leave vague,
        # and the one where "what will you show me" does the real work.
        if pillar is Pillar.KNOWLEDGE:
            for item in pillar_items:
                if not item.evidence_expected.strip():
                    findings.append(Finding(
                        Severity.BLOCK, "knowledge.evidence",
                        f"'{item.text[:50] or 'goal'}' does not say what "
                        "evidence proves it was achieved. Without that it "
                        "cannot be rated honestly at month end.",
                        item.lineage_id,
                    ))
            if len(pillar_items) > 4:
                findings.append(Finding(
                    Severity.WARN, "knowledge",
                    f"{len(pillar_items)} knowledge goals in one month is a "
                    "lot; two or three is usually more achievable.",
                ))

        # Deleting a company-wide default is allowed — managers own their
        # cards — but management should see it happen.
        removed = [
            item for item in pillar_items
            if item.source == "business_need" and item.change_type == "deleted"
        ]
        for item in removed:
            findings.append(Finding(
                Severity.WARN, f"{pillar.value.lower()}.default",
                f"Company-wide {pillar.value} item '{item.text[:40]}' was "
                "removed from this card.",
                item.lineage_id,
            ))

    return findings


def _validate_staleness(
    result_items: list[KPICardItem],
    kbd_items: list[KBDItem],
    carried_streak: dict[str, int],
) -> list[Finding]:
    """Flag items carried unchanged for several months.

    Informational only. Reuse is explicitly encouraged here — the whole point
    of carry-forward — so this is a prompt to re-examine, not a criticism.
    """
    findings: list[Finding] = []
    labels: dict[str, str] = {}
    for item in result_items:
        labels[item.lineage_id] = item.name
    for item in kbd_items:
        labels[item.lineage_id] = item.text[:40]

    for lineage_id, months in carried_streak.items():
        if months >= 3 and lineage_id in labels:
            findings.append(Finding(
                Severity.INFO, "staleness",
                f"'{labels[lineage_id]}' has been carried unchanged for "
                f"{months} months. Still the right measure?",
                lineage_id,
            ))
    return findings


def _duplicate_names(names: Iterable[str]) -> list[str]:
    seen: dict[str, int] = {}
    for name in names:
        key = " ".join(name.lower().split())
        if key:
            seen[key] = seen.get(key, 0) + 1
    return [name for name, count in seen.items() if count > 1]


# --------------------------------------------------------------------------
# Scoring remarks
# --------------------------------------------------------------------------

_FILLER = re.compile(r"^(.{1,6}?)\1{4,}$", re.DOTALL)


def validate_remark(
    remark: str,
    params: Optional[dict[str, str]] = None,
    other_remarks: Optional[Iterable[str]] = None,
    previous_remark: str = "",
) -> list[Finding]:
    """Check one scoring justification.

    `other_remarks` are the remarks already entered elsewhere on the same
    card; `previous_remark` is last month's for the same lineage.
    """
    findings: list[Finding] = []
    minimum = int(_param(params, "score.min_remark_chars"))
    text = (remark or "").strip()
    collapsed = " ".join(text.split())

    if not text:
        return [Finding(
            Severity.BLOCK, "remark",
            f"A written justification of at least {minimum} characters is "
            "required.",
        )]

    if len(collapsed) < minimum:
        findings.append(Finding(
            Severity.BLOCK, "remark",
            f"{len(collapsed)} of {minimum} characters. Say what happened "
            "and why it earned this score.",
        ))

    if _is_filler(collapsed):
        findings.append(Finding(
            Severity.BLOCK, "remark",
            "This looks like padding rather than a justification.",
        ))

    normalised = collapsed.lower()
    for other in other_remarks or []:
        if normalised and " ".join(str(other).split()).lower() == normalised:
            findings.append(Finding(
                Severity.BLOCK, "remark",
                "This is identical to another remark on the same card. Each "
                "item needs its own assessment.",
            ))
            break

    if previous_remark and normalised == " ".join(previous_remark.split()).lower():
        findings.append(Finding(
            Severity.BLOCK, "remark",
            "This is identical to last month's remark for the same item. If "
            "the assessment genuinely has not changed, say so in your own "
            "words for this month.",
        ))

    return findings


def _is_filler(text: str) -> bool:
    """Detect padding that clears a length floor without saying anything."""
    if not text:
        return True
    stripped = text.replace(" ", "")
    if len(set(stripped)) <= 3:
        return True
    if _FILLER.match(stripped):
        return True
    words = [w for w in text.lower().split() if w]
    # "n/a n/a n/a ..." — long enough, but only one distinct word.
    if len(words) >= 8 and len(set(words)) <= 2:
        return True
    return False


def validate_scoring(
    entries: list[tuple[str, str]],
    params: Optional[dict[str, str]] = None,
    previous_remarks: Optional[dict[str, str]] = None,
) -> list[Finding]:
    """Check every remark on a card at once.

    `entries` is [(lineage_id, remark)]. Applied identically at self,
    manager and calibration stages — a calibration override that changes a
    score needs justifying just as much as the original.
    """
    findings: list[Finding] = []
    previous = previous_remarks or {}
    seen: list[str] = []

    for lineage_id, remark in entries:
        for finding in validate_remark(
            remark, params,
            other_remarks=seen,
            previous_remark=previous.get(lineage_id, ""),
        ):
            findings.append(Finding(
                finding.severity, finding.field, finding.message, lineage_id
            ))
        if remark and remark.strip():
            seen.append(remark)
    return findings


def blocking(findings: Iterable[Finding]) -> list[Finding]:
    return [f for f in findings if f.blocking]


def summarise(findings: Iterable[Finding]) -> dict[str, int]:
    counts = {severity.value: 0 for severity in Severity}
    for finding in findings:
        counts[finding.severity.value] += 1
    return counts
