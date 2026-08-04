"""Card lifecycle: carry-forward, lineage, state transitions, amendments.

The rules under test are the ones that make a dropped yearly KPI freeze safe:
lineage keeps month-over-month comparability alive through free editing, and
a live card can only change via an approval sitting exactly one level above
the requester.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.performance.models.performance_models import (
    BusinessNeed,
    CardStatus,
    ChangeType,
    Direction,
    Employee,
    ItemSource,
    KBDItem,
    KPICardItem,
    KPILibraryEntry,
    Pillar,
    new_id,
)
from src.performance.service import card_service as cards
from src.performance.service.card_service import CardError
from src.performance.service.org_service import OrgChart

REAL_TREE = [
    ("E01", "Ketan Mehta", "MD", ""),
    ("E02", "Sarika Bhise", "Director", "E01"),
    ("E03", "Tirth Mehta", "VP", "E01"),
    ("E05", "Sneha Kadam", "Sr. Associate", "E02"),
    ("E07", "Vijay", "Sr. Associate", "E05"),
]


@pytest.fixture
def chart() -> OrgChart:
    return OrgChart([
        Employee(emp_id=e, name=n, email=f"{n.split()[0].lower()}@amba.com",
                 level=lv, reports_to_emp_id=m, status="active")
        for e, n, lv, m in REAL_TREE
    ], as_of=date(2026, 9, 30))


def kpi(card_id="CARD-1", name="Production Volume", **overrides) -> KPICardItem:
    fields = {
        "card_id": card_id, "lineage_id": new_id("LIN"), "name": name,
        "direction": Direction.HIGHER.value, "unit": "tonnes", "target": 80.0,
        "weight": 50.0, "measurement_method": "Despatched tonnage",
        "data_source": "Production records",
    }
    fields.update(overrides)
    return KPICardItem(**fields)


def kbd(card_id="CARD-1", pillar=Pillar.BEHAVIOUR, text="Ownership", **overrides):
    fields = {"card_id": card_id, "lineage_id": new_id("LIN"),
              "pillar": pillar.value, "text": text, "weight": 1.0}
    fields.update(overrides)
    return KBDItem(**fields)


def live_card(period="2026-09", emp_id="E07", set_by="E05"):
    card = cards.build_card(emp_id, period, set_by)
    return card.model_copy(update={"status": CardStatus.LIVE.value})


# --------------------------------------------------------------------------
# Carry-forward and lineage
# --------------------------------------------------------------------------


def test_carry_forward_preserves_lineage_and_retargets_the_card():
    previous = [kpi(name="Production Volume"), kpi(name="Scrap Rate")]
    result, _ = cards.carry_forward("CARD-2", previous, [])

    assert [i.lineage_id for i in result] == [i.lineage_id for i in previous]
    assert all(i.card_id == "CARD-2" for i in result)
    assert all(i.source == ItemSource.CARRIED.value for i in result)
    assert all(i.change_type == ChangeType.KEPT.value for i in result)


def test_carry_forward_keeps_last_months_target_for_deliberate_review():
    """Targets carry across so the manager changes the number on purpose,
    rather than starting from a blank the system quietly pre-filled."""
    previous = [kpi(target=80.0)]
    result, _ = cards.carry_forward("CARD-2", previous, [])
    assert result[0].target == 80.0


def test_editing_a_carried_item_keeps_its_lineage():
    previous = [kpi(name="Production Volume", target=80.0)]
    result, _ = cards.carry_forward("CARD-2", previous, [])
    edited = [result[0].model_copy(update={"target": 95.0, "name": "Output Volume"})]

    marked = cards.mark_changes(edited, previous)
    assert marked[0].lineage_id == previous[0].lineage_id
    assert marked[0].change_type == ChangeType.EDITED.value


def test_delete_and_readd_starts_a_new_lineage():
    """The correct behaviour: a re-added item is not the same series."""
    previous = [kpi(name="Production Volume")]
    fresh = cards.blank_item("CARD-2", 0)
    fresh = fresh.model_copy(update={"name": "Production Volume"})

    assert fresh.lineage_id != previous[0].lineage_id
    marked = cards.mark_changes([fresh], previous)
    assert marked[0].change_type == ChangeType.ADDED.value
    assert cards.deleted_items([fresh], previous)[0].lineage_id == previous[0].lineage_id


def test_unchanged_item_is_marked_kept():
    previous = [kpi()]
    result, _ = cards.carry_forward("CARD-2", previous, [])
    assert cards.mark_changes(result, previous)[0].change_type == ChangeType.KEPT.value


def test_deleted_items_reports_what_was_dropped():
    previous = [kpi(name="A"), kpi(name="B"), kpi(name="C")]
    kept = [previous[0], previous[2]]
    dropped = cards.deleted_items(kept, previous)
    assert [d.name for d in dropped] == ["B"]
    assert dropped[0].change_type == ChangeType.DELETED.value


def test_carried_streak_counts_consecutive_kept_months():
    history = {
        "LIN-A": ["kept", "kept", "kept", "edited", "kept"],
        "LIN-B": ["edited", "kept", "kept"],
        "LIN-C": [],
    }
    streaks = cards.carried_streak(["LIN-A", "LIN-B", "LIN-C"], history)
    assert streaks == {"LIN-A": 3, "LIN-B": 0, "LIN-C": 0}


# --------------------------------------------------------------------------
# Seeding a new card
# --------------------------------------------------------------------------


def test_company_defaults_are_applied_so_no_pillar_is_left_empty():
    needs = [
        BusinessNeed(need_id="BN-1", period="2026-09", pillar=Pillar.BEHAVIOUR.value,
                     metric="Integrity", is_company_default=True),
        BusinessNeed(need_id="BN-2", period="2026-09", pillar=Pillar.DISCIPLINE.value,
                     metric="Attendance", is_company_default=True),
        BusinessNeed(need_id="BN-3", period="2026-09", pillar=Pillar.RESULT.value,
                     metric="Trading volume", target="80", is_company_default=True),
    ]
    _, result, kbd_items = cards.seed_new_card("E07", "2026-09", "E05",
                                               business_needs=needs)
    assert result == []
    pillars = {i.pillar for i in kbd_items}
    assert pillars == {Pillar.BEHAVIOUR.value, Pillar.DISCIPLINE.value}
    assert all(i.source == ItemSource.BUSINESS_NEED.value for i in kbd_items)


def test_defaults_are_not_duplicated_when_a_previous_card_already_has_them():
    needs = [BusinessNeed(need_id="BN-1", period="2026-09",
                          pillar=Pillar.BEHAVIOUR.value, metric="Integrity",
                          is_company_default=True)]
    previous_kbd = [kbd(pillar=Pillar.BEHAVIOUR, text="Integrity")]

    _, _, kbd_items = cards.seed_new_card(
        "E07", "2026-09", "E05", previous_kbd=previous_kbd, business_needs=needs
    )
    behaviour = [i for i in kbd_items if i.pillar == Pillar.BEHAVIOUR.value]
    assert len(behaviour) == 1
    assert behaviour[0].source == ItemSource.CARRIED.value


def test_non_default_business_needs_are_not_pushed_onto_cards():
    needs = [BusinessNeed(need_id="BN-1", period="2026-09",
                          pillar=Pillar.BEHAVIOUR.value, metric="Ad-hoc focus",
                          is_company_default=False)]
    _, _, kbd_items = cards.seed_new_card("E07", "2026-09", "E05",
                                          business_needs=needs)
    assert kbd_items == []


def test_item_from_library_copies_the_definition_but_not_the_target():
    entry = KPILibraryEntry(
        kpi_id="K033", name="Scrap Rate", direction=Direction.LOWER.value,
        unit="%", measurement_method="Scrap / input weight",
        data_source="Production records", default_weight=10,
    )
    item = cards.item_from_library("CARD-1", entry, seq=0)
    assert item.kpi_id == "K033"
    assert item.direction == Direction.LOWER.value
    assert item.weight == 10
    assert item.target is None, "the target is the manager's decision each month"
    assert item.source == ItemSource.LIBRARY.value


# --------------------------------------------------------------------------
# State transitions
# --------------------------------------------------------------------------


def test_happy_path_through_the_lifecycle():
    card = cards.build_card("E07", "2026-09", "E05")
    assert cards.is_editable(card)

    card = cards.submit(card, "E05")
    assert card.status == CardStatus.SUBMITTED.value

    card = cards.acknowledge(card, "E07")
    assert card.status == CardStatus.ACKNOWLEDGED.value

    card = cards.go_live(card)
    assert card.status == CardStatus.LIVE.value
    assert not cards.is_editable(card), "a live card is locked for the month"

    card = cards.lock(card)
    assert card.status == CardStatus.LOCKED.value


def test_only_the_employee_can_acknowledge_their_own_card():
    card = cards.submit(cards.build_card("E07", "2026-09", "E05"), "E05")
    with pytest.raises(CardError, match="Only the employee"):
        cards.acknowledge(card, "E05")


def test_a_live_card_cannot_be_submitted_or_relive():
    card = live_card()
    with pytest.raises(CardError):
        cards.submit(card, "E05")
    with pytest.raises(CardError):
        cards.go_live(card)


def test_a_locked_card_cannot_be_reopened():
    card = cards.lock(live_card())
    for action in (lambda: cards.submit(card, "E05"),
                   lambda: cards.go_live(card),
                   lambda: cards.lock(card)):
        with pytest.raises(CardError):
            action()


# --------------------------------------------------------------------------
# Amendment window
# --------------------------------------------------------------------------


@pytest.mark.parametrize("day,expected", [
    (1, True), (5, True), (10, True), (11, False), (28, False),
])
def test_amendment_window_spans_days_one_to_ten(day, expected):
    assert cards.amendment_window_open("2026-09", date(2026, 9, day)) is expected


def test_amendment_window_is_closed_outside_the_live_month():
    assert not cards.amendment_window_open("2026-09", date(2026, 8, 5))
    assert not cards.amendment_window_open("2026-09", date(2026, 10, 5))


def test_amendment_close_day_is_configurable():
    assert cards.amendment_window_open("2026-09", date(2026, 9, 14), close_day=15)
    assert not cards.amendment_window_open("2026-09", date(2026, 9, 16), close_day=15)


# --------------------------------------------------------------------------
# Amendment requests
# --------------------------------------------------------------------------


def test_manager_can_request_an_amendment_inside_the_window(chart):
    request = cards.request_amendment(
        live_card(), chart, requested_by="E05",
        rationale="Slitter down for a week; volume target no longer reachable.",
        changes={"LIN-1": {"target": [80, 60]}}, today=date(2026, 9, 4),
    )
    assert request.status == "pending"
    assert request.approver_emp_id == "E02", "one level above Sneha is Sarika"


def test_amendment_after_day_ten_is_refused(chart):
    with pytest.raises(CardError, match="closed on day 10"):
        cards.request_amendment(
            live_card(), chart, requested_by="E05", rationale="Late change",
            changes={}, today=date(2026, 9, 11),
        )


def test_only_the_direct_manager_can_request(chart):
    with pytest.raises(CardError, match="direct manager"):
        cards.request_amendment(
            live_card(), chart, requested_by="E02",   # Sarika is two levels up
            rationale="Skip-level change", changes={}, today=date(2026, 9, 4),
        )


def test_amendment_needs_a_rationale(chart):
    with pytest.raises(CardError, match="rationale"):
        cards.request_amendment(
            live_card(), chart, requested_by="E05", rationale="   ",
            changes={}, today=date(2026, 9, 4),
        )


def test_a_draft_card_is_not_amended_it_is_simply_edited(chart):
    draft = cards.build_card("E07", "2026-09", "E05")
    with pytest.raises(CardError, match="Only a live card"):
        cards.request_amendment(draft, chart, requested_by="E05",
                                rationale="x" * 30, changes={},
                                today=date(2026, 9, 4))


def test_md_set_card_has_no_approver_and_says_so(chart):
    """Nobody sits above the MD, so the system refuses rather than letting a
    self-approval slip through."""
    card = live_card(emp_id="E02", set_by="E01")
    with pytest.raises(CardError, match="no approver"):
        cards.request_amendment(card, chart, requested_by="E01",
                                rationale="Change of plan", changes={},
                                today=date(2026, 9, 4))


# --------------------------------------------------------------------------
# Amendment decisions
# --------------------------------------------------------------------------


def _pending(chart):
    return cards.request_amendment(
        live_card(), chart, requested_by="E05",
        rationale="Slitter down for a week.", changes={"LIN-1": {"target": [80, 60]}},
        today=date(2026, 9, 4),
    )


def test_requester_cannot_approve_their_own_amendment(chart):
    with pytest.raises(CardError, match="cannot be approved by the person who raised it"):
        cards.decide_amendment(_pending(chart), chart, actor="E05", approve=True)


def test_approval_must_come_from_exactly_one_level_up(chart):
    request = _pending(chart)
    # The MD is two levels above Sneha — too senior, and leapfrogging is
    # exactly what the Accountability Framework forbids.
    with pytest.raises(CardError, match="one level above"):
        cards.decide_amendment(request, chart, actor="E01", approve=True)

    approved = cards.decide_amendment(request, chart, actor="E02", approve=True)
    assert approved.status == "approved"


def test_rejection_is_recorded_with_its_note(chart):
    decided = cards.decide_amendment(
        _pending(chart), chart, actor="E02", approve=False,
        note="Target stands; recover the volume in week four.",
    )
    assert decided.status == "rejected"
    assert "week four" in decided.decision_note


def test_an_amendment_is_decided_only_once(chart):
    approved = cards.decide_amendment(_pending(chart), chart, actor="E02", approve=True)
    with pytest.raises(CardError, match="already"):
        cards.decide_amendment(approved, chart, actor="E02", approve=False)


def test_applying_an_approved_amendment_bumps_version_and_resets_acknowledgement(chart):
    card = live_card().model_copy(update={"acknowledged_at": "2026-08-28T10:00:00"})
    approved = cards.decide_amendment(_pending(chart), chart, actor="E02", approve=True)

    amended = cards.apply_amendment(card, approved)
    assert amended.version == card.version + 1
    assert amended.status == CardStatus.AMENDED.value
    assert amended.acknowledged_at == "", "the employee must re-accept a changed card"


def test_a_rejected_amendment_cannot_be_applied(chart):
    rejected = cards.decide_amendment(_pending(chart), chart, actor="E02", approve=False)
    with pytest.raises(CardError, match="approved"):
        cards.apply_amendment(live_card(), rejected)


def test_amended_card_can_be_reacknowledged_and_locked(chart):
    card = live_card()
    approved = cards.decide_amendment(_pending(chart), chart, actor="E02", approve=True)
    card = cards.apply_amendment(card, approved)
    card = cards.acknowledge(card, "E07")
    assert card.status == CardStatus.ACKNOWLEDGED.value
    assert cards.lock(cards.go_live(card)).status == CardStatus.LOCKED.value


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


def test_audit_records_adds_edits_and_deletes(chart):
    original = [kpi(name="A", target=10.0), kpi(name="B", target=20.0)]
    current = [
        original[0].model_copy(update={"target": 15.0}),   # edited
        kpi(name="C", target=30.0),                        # added
    ]                                                       # B deleted

    entries = cards.audit_card_changes("E05", live_card(), current, original, "KPICardItem")
    actions = {e.action for e in entries}
    assert actions == {"update", "create", "delete"}
    edited = next(e for e in entries if e.action == "update")
    assert "target=10.0" in edited.old_value and "target=15.0" in edited.new_value


def test_audit_is_silent_when_nothing_changed(chart):
    original = [kpi(name="A")]
    unchanged, _ = cards.carry_forward("CARD-1", original, [])
    assert cards.audit_card_changes("E05", live_card(), unchanged, original,
                                    "KPICardItem") == []
