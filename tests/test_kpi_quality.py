"""Card quality gate and scoring-remark rules.

This gate is the primary constraint on card quality, since Amba deliberately
did not adopt the workbook's yearly KPI freeze — nothing else limits what a
manager writes each month.
"""

from __future__ import annotations

import pytest

from src.performance.models.performance_models import (
    Direction,
    ItemSource,
    KBDItem,
    KPICardItem,
    OutcomeType,
    Pillar,
    new_id,
)
from src.performance.service.kpi_quality import (
    Severity,
    blocking,
    summarise,
    validate_card,
    validate_remark,
    validate_scoring,
)

GOOD_REMARK = (
    "Produced 78 tonnes against a target of 80. The shortfall came from two "
    "days of slitter downtime in week three, which Vijay escalated the same "
    "shift and which was repaired within 24 hours."
)


def kpi(name="Production Volume", weight=100.0, **overrides) -> KPICardItem:
    fields = {
        "card_id": "CARD-1",
        "lineage_id": new_id("LIN"),
        "name": name,
        "direction": Direction.HIGHER.value,
        "unit": "tonnes",
        "target": 80.0,
        "weight": weight,
        "measurement_method": "Total despatched tonnage for the month",
        "data_source": "Production + dispatch records",
        "outcome_type": OutcomeType.OUTCOME.value,
    }
    fields.update(overrides)
    return KPICardItem(**fields)


def kbd(pillar=Pillar.BEHAVIOUR, text="Ownership", **overrides) -> KBDItem:
    fields = {
        "card_id": "CARD-1",
        "lineage_id": new_id("LIN"),
        "pillar": pillar.value if hasattr(pillar, "value") else pillar,
        "text": text,
        "weight": 1.0,
    }
    if fields["pillar"] == Pillar.KNOWLEDGE.value:
        fields.setdefault("evidence_expected", "Walk me through it unaided")
    fields.update(overrides)
    return KBDItem(**fields)


def good_kbd() -> list[KBDItem]:
    return [
        kbd(Pillar.KNOWLEDGE, "Learn basic production planning",
            evidence_expected="Produce next month's plan unaided"),
        kbd(Pillar.BEHAVIOUR, "Ownership"),
        kbd(Pillar.DISCIPLINE, "Attendance & Punctuality"),
    ]


def good_result() -> list[KPICardItem]:
    return [
        kpi("Production Volume", 40.0),
        kpi("On-Time Delivery", 35.0, unit="%", target=90.0),
        kpi("Scrap Rate", 25.0, unit="%", target=4.0,
            direction=Direction.LOWER.value),
    ]


def messages(findings) -> str:
    return " || ".join(f.message for f in findings)


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


def test_a_well_formed_card_passes():
    findings = validate_card(good_result(), good_kbd())
    assert not blocking(findings), messages(findings)


def test_summarise_counts_by_severity():
    counts = summarise(validate_card(good_result(), good_kbd()))
    assert counts["block"] == 0


# --------------------------------------------------------------------------
# Weights
# --------------------------------------------------------------------------


def test_weights_must_total_one_hundred():
    items = [kpi("A", 40.0), kpi("B", 30.0), kpi("C", 20.0)]
    findings = validate_card(items, good_kbd())
    assert any("must total 100" in f.message for f in blocking(findings))


def test_rounding_split_across_three_kpis_is_accepted():
    """33/33/34 is a sane split, not a mistake."""
    items = [kpi("A", 33.0), kpi("B", 33.0), kpi("C", 34.0)]
    assert not blocking(validate_card(items, good_kbd()))


def test_dominant_and_trivial_weights_warn_but_do_not_block():
    items = [kpi("A", 85.0), kpi("B", 8.0), kpi("C", 7.0)]
    findings = validate_card(items, good_kbd())
    assert not blocking(findings)
    warnings = [f for f in findings if f.severity is Severity.WARN]
    assert any("dominates" in f.message for f in warnings)
    assert any("cannot move the score" in f.message for f in warnings)


def test_zero_weight_blocks():
    items = [kpi("A", 100.0), kpi("B", 0.0), kpi("C", 0.0)]
    assert any("no weight" in f.message for f in blocking(validate_card(items, good_kbd())))


# --------------------------------------------------------------------------
# Count
# --------------------------------------------------------------------------


def test_too_few_kpis_blocks():
    items = [kpi("A", 50.0), kpi("B", 50.0)]
    assert any("at least 3" in f.message for f in blocking(validate_card(items, good_kbd())))


def test_more_than_six_kpis_blocks_because_the_workbook_has_six_slots():
    items = [kpi(f"KPI {i}", 100 / 7) for i in range(7)]
    findings = blocking(validate_card(items, good_kbd()))
    assert any("at most 6" in f.message for f in findings)


def test_exactly_six_kpis_is_allowed():
    items = [kpi(f"KPI {i}", 100 / 6) for i in range(6)]
    assert not blocking(validate_card(items, good_kbd()))


# --------------------------------------------------------------------------
# Per-KPI required fields
# --------------------------------------------------------------------------


@pytest.mark.parametrize("field,expected", [
    ("target", "no numeric target"),
    ("data_source", "no data source"),
    ("measurement_method", "no measurement method"),
    ("name", "needs a name"),
])
def test_missing_required_fields_block(field, expected):
    blank = {"target": None}.get(field, "")
    items = good_result()
    items[0] = kpi(weight=40.0, **{field: blank})
    findings = blocking(validate_card(items, good_kbd()))
    assert any(expected in f.message for f in findings), messages(findings)


def test_lower_is_better_with_a_zero_target_blocks():
    """Achievement divides by the actual, so a zero target is unscoreable."""
    items = good_result()
    items[2] = kpi("Scrap Rate", 25.0, direction=Direction.LOWER.value, target=0.0)
    findings = blocking(validate_card(items, good_kbd()))
    assert any("target of zero" in f.message for f in findings)


def test_range_kpi_needs_a_sane_upper_bound():
    items = good_result()
    items[0] = kpi("Stock cover", 40.0, direction=Direction.RANGE.value,
                   target=10.0, target_max=None)
    assert any("no upper bound" in f.message
               for f in blocking(validate_card(items, good_kbd())))

    items[0] = kpi("Stock cover", 40.0, direction=Direction.RANGE.value,
                   target=10.0, target_max=5.0)
    assert any("below its lower bound" in f.message
               for f in blocking(validate_card(items, good_kbd())))


def test_binary_kpi_needs_no_numeric_target():
    """Milestones are hit or missed; demanding a number would be noise."""
    items = [
        kpi("ERP milestone", 40.0, direction=Direction.BINARY.value, target=None),
        kpi("On-Time Delivery", 35.0, unit="%", target=90.0),
        kpi("Scrap Rate", 25.0, target=4.0, direction=Direction.LOWER.value),
    ]
    assert not blocking(validate_card(items, good_kbd()))


# --------------------------------------------------------------------------
# Balance and cascade
# --------------------------------------------------------------------------


def test_activity_heavy_card_warns():
    items = [
        kpi("Attend auctions", 50.0, outcome_type=OutcomeType.ACTIVITY.value),
        kpi("Send reports", 30.0, outcome_type=OutcomeType.ACTIVITY.value),
        kpi("Production Volume", 20.0),
    ]
    findings = validate_card(items, good_kbd())
    assert not blocking(findings)
    assert any("measures activity" in f.message for f in findings)


def test_card_with_no_business_need_link_warns_when_needs_exist():
    findings = validate_card(good_result(), good_kbd(), business_need_refs=["BN-1"])
    assert any("cascades from what the company needs" in f.message for f in findings)


def test_linking_one_kpi_to_a_business_need_clears_the_warning():
    items = good_result()
    items[0] = kpi("Production Volume", 40.0, business_need_ref="BN-1")
    findings = validate_card(items, good_kbd(), business_need_refs=["BN-1"])
    assert not any("cascades from" in f.message for f in findings)


def test_duplicate_kpi_names_warn():
    items = [kpi("Production Volume", 40.0), kpi("production  volume", 35.0),
             kpi("Scrap Rate", 25.0, target=4.0, direction=Direction.LOWER.value)]
    findings = validate_card(items, good_kbd())
    assert any("more than once" in f.message for f in findings)


# --------------------------------------------------------------------------
# Knowledge / Behaviour / Discipline
# --------------------------------------------------------------------------


@pytest.mark.parametrize("missing", [Pillar.KNOWLEDGE, Pillar.BEHAVIOUR, Pillar.DISCIPLINE])
def test_an_empty_qualitative_pillar_blocks(missing):
    items = [item for item in good_kbd() if item.pillar != missing.value]
    findings = blocking(validate_card(good_result(), items))
    assert any(missing.value in f.message and "no items" in f.message for f in findings)


def test_knowledge_goal_without_evidence_blocks():
    items = good_kbd()
    items[0] = kbd(Pillar.KNOWLEDGE, "Get better at planning", evidence_expected="")
    findings = blocking(validate_card(good_result(), items))
    assert any("what evidence proves it" in f.message for f in findings)


def test_too_many_knowledge_goals_warns():
    items = good_kbd() + [
        kbd(Pillar.KNOWLEDGE, f"Goal {i}", evidence_expected="Demonstrate it")
        for i in range(4)
    ]
    findings = validate_card(good_result(), items)
    assert not blocking(findings)
    assert any("is a lot" in f.message for f in findings)


def test_deleting_a_company_default_is_allowed_but_surfaced():
    items = good_kbd() + [
        kbd(Pillar.BEHAVIOUR, "Integrity",
            source=ItemSource.BUSINESS_NEED.value, change_type="deleted")
    ]
    findings = validate_card(good_result(), items)
    assert not blocking(findings), "managers own their cards"
    assert any("was removed from this card" in f.message for f in findings)


# --------------------------------------------------------------------------
# Staleness
# --------------------------------------------------------------------------


def test_long_carried_item_is_info_not_a_warning():
    """Reuse is encouraged here — this is a prompt, not a criticism."""
    items = good_result()
    findings = validate_card(
        items, good_kbd(), carried_streak={items[0].lineage_id: 5}
    )
    stale = [f for f in findings if f.field == "staleness"]
    assert stale and stale[0].severity is Severity.INFO
    assert "5 months" in stale[0].message


def test_short_carried_streak_is_silent():
    items = good_result()
    findings = validate_card(items, good_kbd(),
                             carried_streak={items[0].lineage_id: 2})
    assert not [f for f in findings if f.field == "staleness"]


# --------------------------------------------------------------------------
# Scoring remarks
# --------------------------------------------------------------------------


def test_a_real_remark_passes():
    assert not validate_remark(GOOD_REMARK)


def test_short_remark_blocks_and_reports_progress():
    findings = validate_remark("Did well this month.")
    assert findings and findings[0].blocking
    assert "of 100 characters" in findings[0].message


def test_empty_remark_blocks():
    assert blocking(validate_remark(""))
    assert blocking(validate_remark("      "))


def test_whitespace_padding_does_not_satisfy_the_length_floor():
    """Collapsing whitespace before counting stops the cheapest workaround."""
    assert blocking(validate_remark("Good work." + " " * 200))


@pytest.mark.parametrize("padding", [
    "a" * 150,
    "ab" * 80,
    "n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a n/a",
    "-" * 120,
])
def test_filler_is_rejected_even_when_long_enough(padding):
    findings = validate_remark(padding)
    assert findings and findings[0].blocking


def test_remark_duplicated_across_items_on_the_same_card_blocks():
    findings = validate_remark(GOOD_REMARK, other_remarks=[GOOD_REMARK])
    assert any("identical to another remark" in f.message for f in findings)


def test_remark_copied_from_last_month_blocks():
    findings = validate_remark(GOOD_REMARK, previous_remark=GOOD_REMARK)
    assert any("identical to last month" in f.message for f in findings)


def test_reworded_remark_is_accepted():
    reworded = GOOD_REMARK.replace("78 tonnes", "seventy-eight tonnes")
    assert not validate_remark(reworded, previous_remark=GOOD_REMARK)


def test_configurable_minimum_length():
    params = {"score.min_remark_chars": "20"}
    assert not validate_remark("A short but sufficient note here.", params)


def test_validate_scoring_checks_every_item_and_tags_lineage():
    entries = [("LIN-1", GOOD_REMARK), ("LIN-2", "too short"), ("LIN-3", GOOD_REMARK)]
    findings = validate_scoring(entries)
    by_lineage = {f.lineage_id for f in findings}
    assert "LIN-2" in by_lineage      # too short
    assert "LIN-3" in by_lineage      # duplicate of LIN-1
    assert "LIN-1" not in by_lineage


def test_validate_scoring_uses_previous_remarks_per_lineage():
    entries = [("LIN-1", GOOD_REMARK)]
    findings = validate_scoring(entries, previous_remarks={"LIN-1": GOOD_REMARK})
    assert any("identical to last month" in f.message for f in findings)
