"""AI prompt assembly and reply parsing.

The parser has to be forgiving — models wrap TSV in code fences, re-emit
headers, and sometimes fall back to markdown tables. Rejecting a paste over
formatting would just push the manager back to typing it by hand, which is
the thing the feature exists to avoid.
"""

from __future__ import annotations

import pytest

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
from src.performance.service.prompt_builder import build_prompt, parse_draft


@pytest.fixture
def employee() -> Employee:
    return Employee(
        emp_id="E05", name="Sneha Kadam", email="sneha@amba.com",
        designation="Sr. Associate - Manufacturing", level="Sr. Associate",
        department="Operations", reports_to_emp_id="E02",
    )


@pytest.fixture
def role() -> Role:
    return Role(
        role_id="R05", designation="Sr. Associate - Manufacturing",
        primary_ownership="Manufacturing output of the Pune plant.",
        not_responsible_for="Individual Associate errors on first occurrence.",
    )


def prev_kpi(name="Production Volume", **overrides) -> KPICardItem:
    fields = {
        "card_id": "CARD-1", "lineage_id": new_id("LIN"), "name": name,
        "direction": Direction.HIGHER.value, "unit": "tonnes", "target": 80.0,
        "weight": 40.0, "measurement_method": "Despatched tonnage",
        "data_source": "Production records",
    }
    fields.update(overrides)
    return KPICardItem(**fields)


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------


def test_prompt_includes_role_ownership_and_exclusions(employee, role):
    prompt = build_prompt(employee, "2026-09", role=role)
    assert "Manufacturing output of the Pune plant" in prompt
    assert "NOT accountable for" in prompt
    assert "Individual Associate errors" in prompt


def test_prompt_forbids_inventing_targets(employee, role):
    """The single most damaging thing a model could contribute here."""
    prompt = build_prompt(employee, "2026-09", role=role)
    assert "Do NOT invent target numbers" in prompt
    assert "worse than a blank one" in prompt


def test_prompt_explains_the_lower_is_better_trap(employee):
    # The prompt is wrapped prose, so compare with whitespace collapsed.
    prompt = " ".join(build_prompt(employee, "2026-09").split())
    assert "target/actual" in prompt
    assert "scores a missed target as an overachievement" in prompt


def test_prompt_lists_business_needs_with_references(employee):
    needs = [
        BusinessNeed(need_id="BN-1", period="2026-09", pillar=Pillar.RESULT.value,
                     area="Manufacturing", metric="Production Volume",
                     unit="tonnes", target="85"),
    ]
    prompt = build_prompt(employee, "2026-09", business_needs=needs)
    assert "[BN-1]" in prompt
    assert "Production Volume" in prompt
    assert "business_need_ref" in prompt


def test_prompt_shows_last_month_with_achievement(employee):
    item = prev_kpi(target=80.0)
    prompt = build_prompt(
        employee, "2026-09", previous_result=[item],
        previous_actuals={item.lineage_id: 72.0},
    )
    assert "72" in prompt
    assert "90%" in prompt      # 72/80


def test_lower_is_better_achievement_is_inverted_in_the_prompt(employee):
    """A 10% scrap against a 5% target is a 50% achievement, not 120%."""
    item = prev_kpi(name="Scrap Rate", direction=Direction.LOWER.value,
                    target=5.0, unit="%")
    prompt = build_prompt(employee, "2026-09", previous_result=[item],
                          previous_actuals={item.lineage_id: 10.0})
    assert "50%" in prompt
    assert "120%" not in prompt.split("Scrap Rate")[1].split("\n")[0]


def test_achievement_is_capped_at_120(employee):
    item = prev_kpi(target=50.0)
    prompt = build_prompt(employee, "2026-09", previous_result=[item],
                          previous_actuals={item.lineage_id: 200.0})
    assert "120%" in prompt


def test_prompt_handles_a_first_month_with_no_history(employee):
    prompt = build_prompt(employee, "2026-09")
    assert "first month for this person" in prompt


def test_prompt_names_the_six_values(employee):
    prompt = build_prompt(employee, "2026-09")
    for value in ("Integrity", "Ownership", "Customer First",
                  "Quality Without Compromise", "Drive & Discipline",
                  "Respect & Trust"):
        assert value in prompt


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

CLEAN_REPLY = """Here is my critique: the old card measured activity.

RESULT
pillar\tname\tdirection\tunit\ttarget\tweight\tmeasurement_method\tdata_source\toutcome_type\taccountability_layer
Result\tProduction Volume\thigher\ttonnes\t85\t40\tDespatched tonnage\tProduction records\toutcome\tL2 Supervision
Result\tScrap Rate\tlower\t%\t4\t35\tScrap / input weight\tProduction records\toutcome\tL2 Supervision
Result\tOn-Time Delivery\thigher\t%\t92\t25\tOn time / total\tDispatch log\toutcome\tL2 Supervision

KBD
pillar\ttext\tevidence_expected\tweight
Knowledge\tProduction planning in the ERP\tBuild next month's plan unaided\t1
Behaviour\tOwnership\t\t1
Discipline\tAttendance & Punctuality\t\t1

I tightened the scrap KPI and set direction correctly.
"""


def test_parses_a_clean_reply():
    draft = parse_draft(CLEAN_REPLY, "CARD-2")
    assert draft.ok, draft.errors
    assert len(draft.result_items) == 3
    assert len(draft.kbd_items) == 3

    scrap = next(i for i in draft.result_items if i.name == "Scrap Rate")
    assert scrap.direction == Direction.LOWER.value
    assert scrap.target == 4.0
    assert scrap.weight == 35.0
    assert scrap.accountability_layer == AccountabilityLayer.SUPERVISION.value

    knowledge = next(i for i in draft.kbd_items if i.pillar == Pillar.KNOWLEDGE.value)
    assert knowledge.evidence_expected == "Build next month's plan unaided"


def test_parsing_reattaches_lineage_for_kept_items():
    """An AI-assisted rewrite must not silently break an existing trend."""
    existing = [prev_kpi(name="Production Volume")]
    draft = parse_draft(CLEAN_REPLY, "CARD-2", existing_result=existing)

    carried = next(i for i in draft.result_items if i.name == "Production Volume")
    assert carried.lineage_id == existing[0].lineage_id
    assert draft.matched_lineage == 1

    fresh = next(i for i in draft.result_items if i.name == "Scrap Rate")
    assert fresh.lineage_id != existing[0].lineage_id


def test_lineage_matching_ignores_case_and_spacing():
    existing = [prev_kpi(name="production   VOLUME")]
    draft = parse_draft(CLEAN_REPLY, "CARD-2", existing_result=existing)
    carried = next(i for i in draft.result_items if i.name == "Production Volume")
    assert carried.lineage_id == existing[0].lineage_id


def test_kbd_lineage_matches_on_pillar_and_text():
    existing = [KBDItem(card_id="CARD-1", lineage_id="LIN-B",
                        pillar=Pillar.BEHAVIOUR.value, text="Ownership")]
    draft = parse_draft(CLEAN_REPLY, "CARD-2", existing_kbd=existing)
    item = next(i for i in draft.kbd_items if i.text == "Ownership")
    assert item.lineage_id == "LIN-B"


def test_parses_a_reply_wrapped_in_code_fences():
    fenced = CLEAN_REPLY.replace("RESULT\n", "```\nRESULT\n").replace(
        "\n\nKBD", "\n```\n\n```\nKBD"
    ) + "\n```"
    draft = parse_draft(fenced, "CARD-2")
    assert len(draft.result_items) == 3
    assert len(draft.kbd_items) == 3


def test_parses_a_markdown_table_fallback():
    reply = """RESULT
| pillar | name | direction | unit | target | weight | measurement_method | data_source | outcome_type | accountability_layer |
|---|---|---|---|---|---|---|---|---|---|
| Result | Production Volume | higher | tonnes | 85 | 100 | Despatched tonnage | Production records | outcome | L2 Supervision |
"""
    draft = parse_draft(reply, "CARD-2")
    assert len(draft.result_items) == 1
    assert draft.result_items[0].target == 85.0
    assert draft.result_items[0].weight == 100.0


def test_unknown_target_placeholder_becomes_blank_not_zero():
    """The prompt tells the model to use '?' rather than invent a number.
    Parsing that as 0.0 would be worse than leaving it empty."""
    reply = ("RESULT\npillar\tname\tdirection\tunit\ttarget\tweight\t"
             "measurement_method\tdata_source\toutcome_type\taccountability_layer\n"
             "Result\tTrading Volume\thigher\ttonnes\t?\t100\tTonnes sold\t"
             "Sales register\toutcome\tL1 Execution\n")
    draft = parse_draft(reply, "CARD-2")
    assert draft.result_items[0].target is None


@pytest.mark.parametrize("raw,expected", [
    ("85", 85.0), ("1,200", 1200.0), ("92%", 92.0), ("  40 ", 40.0),
    ("n/a", None), ("—", None), ("TBD", None), ("", None),
])
def test_number_parsing_handles_common_model_output(raw, expected):
    reply = ("RESULT\npillar\tname\tdirection\tunit\ttarget\tweight\t"
             "measurement_method\tdata_source\toutcome_type\taccountability_layer\n"
             f"Result\tX\thigher\tt\t{raw}\t100\tm\ts\toutcome\tL1 Execution\n")
    assert parse_draft(reply, "CARD-2").result_items[0].target == expected


@pytest.mark.parametrize("text,expected", [
    ("lower", Direction.LOWER.value),
    ("LOWER", Direction.LOWER.value),
    ("higher", Direction.HIGHER.value),
    ("binary", Direction.BINARY.value),
    ("nonsense", Direction.HIGHER.value),   # safe default
])
def test_direction_matching_is_forgiving(text, expected):
    reply = ("RESULT\npillar\tname\tdirection\tunit\ttarget\tweight\t"
             "measurement_method\tdata_source\toutcome_type\taccountability_layer\n"
             f"Result\tX\t{text}\tt\t10\t100\tm\ts\toutcome\tL1 Execution\n")
    assert parse_draft(reply, "CARD-2").result_items[0].direction == expected


@pytest.mark.parametrize("text,expected", [
    ("L1 Execution", AccountabilityLayer.EXECUTION.value),
    ("execution", AccountabilityLayer.EXECUTION.value),
    ("L2", AccountabilityLayer.SUPERVISION.value),
    ("supervision", AccountabilityLayer.SUPERVISION.value),
    ("L3 Design", AccountabilityLayer.DESIGN.value),
])
def test_accountability_layer_matching_is_forgiving(text, expected):
    reply = ("RESULT\npillar\tname\tdirection\tunit\ttarget\tweight\t"
             "measurement_method\tdata_source\toutcome_type\taccountability_layer\n"
             f"Result\tX\thigher\tt\t10\t100\tm\ts\toutcome\t{text}\n")
    assert parse_draft(reply, "CARD-2").result_items[0].accountability_layer == expected


def test_empty_paste_reports_a_useful_error():
    draft = parse_draft("", "CARD-2")
    assert not draft.ok
    assert "Nothing pasted" in draft.errors[0]


def test_reply_without_blocks_explains_what_is_missing():
    draft = parse_draft("Sure! Here are some ideas for KPIs.", "CARD-2")
    assert not draft.ok
    assert "No RESULT or KBD block" in draft.errors[0]


def test_row_without_a_name_is_reported_not_silently_dropped():
    reply = ("RESULT\npillar\tname\tdirection\tunit\ttarget\tweight\t"
             "measurement_method\tdata_source\toutcome_type\taccountability_layer\n"
             "Result\t\thigher\tt\t10\t100\tm\ts\toutcome\tL1 Execution\n")
    draft = parse_draft(reply, "CARD-2")
    assert any("no KPI name" in e for e in draft.errors)


def test_unrecognised_pillar_is_reported():
    reply = "KBD\npillar\ttext\tevidence_expected\tweight\nMotivation\tTry harder\t\t1\n"
    draft = parse_draft(reply, "CARD-2")
    assert any("unrecognised pillar" in e for e in draft.errors)


def test_parsed_items_belong_to_the_target_card():
    draft = parse_draft(CLEAN_REPLY, "CARD-99")
    assert all(i.card_id == "CARD-99" for i in draft.result_items)
    assert all(i.card_id == "CARD-99" for i in draft.kbd_items)


def test_parsed_draft_survives_the_quality_gate():
    """End to end: a good AI reply should produce a submittable card."""
    from src.performance.service.kpi_quality import blocking, validate_card

    draft = parse_draft(CLEAN_REPLY, "CARD-2")
    findings = validate_card(draft.result_items, draft.kbd_items)
    assert not blocking(findings), [f.message for f in blocking(findings)]
