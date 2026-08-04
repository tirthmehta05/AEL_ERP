"""Card lifecycle: build, carry forward, submit, acknowledge, go live, amend.

The lifecycle exists because Amba deliberately dropped the workbook's yearly
KPI freeze. Cards are freely editable *while being planned*, then locked when
they go live on the 1st, and after that change only through an approval flow:

    draft -> submitted -> acknowledged -> live -> [amended] -> locked
                                            \\_ day 1-10 only, approved
                                               one level up

Two ideas do most of the work:

**Lineage.** Every item carries a `lineage_id` that survives carry-forward and
editing. Without it, free monthly editing would destroy month-over-month
comparability — the price of dropping the freeze. With it, an edited KPI still
charts against its own history, while a delete-and-re-add correctly starts a
new series.

**One-level-up approval.** An amendment to a card is approved by the *setting
manager's* own manager, matching the Accountability Framework's rule that
accountability escalates exactly one level and never leapfrogs. Nobody can
approve their own request.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Iterable, Optional

from src.performance.models.performance_models import (
    AmendmentRequest,
    AuditEntry,
    BusinessNeed,
    CardStatus,
    ChangeType,
    Direction,
    Employee,
    ItemSource,
    KBDItem,
    KPICard,
    KPICardItem,
    KPILibraryEntry,
    OutcomeType,
    Pillar,
    new_id,
)
from src.performance.service.cycle_service import period_date, shift_period
from src.performance.service.org_service import OrgChart
from src.shared.utils.logger_config import setup_logger

logger = setup_logger(__name__)

DEFAULT_AMENDMENT_CLOSE_DAY = 10


class CardError(Exception):
    """A lifecycle rule was violated — wrong state, wrong actor, or too late."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Building a card
# --------------------------------------------------------------------------


def build_card(emp_id: str, period: str, set_by: str) -> KPICard:
    return KPICard(
        card_id=new_id("CARD"),
        emp_id=emp_id,
        period=period,
        status=CardStatus.DRAFT.value,
        version=1,
        set_by=set_by,
        set_at=_now(),
    )


def carry_forward(
    card_id: str,
    previous_result: list[KPICardItem],
    previous_kbd: list[KBDItem],
) -> tuple[list[KPICardItem], list[KBDItem]]:
    """Seed a new card from last month's, preserving lineage.

    Targets carry across unchanged on purpose: the manager should look at
    last month's actual and decide the number deliberately, rather than
    starting from a blank the system silently pre-filled.
    """
    result_items = [
        item.model_copy(update={
            "card_id": card_id,
            "source": ItemSource.CARRIED.value,
            "change_type": ChangeType.KEPT.value,
        })
        for item in previous_result
    ]
    kbd_items = [
        item.model_copy(update={
            "card_id": card_id,
            "source": ItemSource.CARRIED.value,
            "change_type": ChangeType.KEPT.value,
        })
        for item in previous_kbd
    ]
    return result_items, kbd_items


def item_from_library(
    card_id: str, entry: KPILibraryEntry, seq: int, target: Optional[float] = None
) -> KPICardItem:
    return KPICardItem(
        card_id=card_id,
        lineage_id=new_id("LIN"),
        seq=seq,
        kpi_id=entry.kpi_id,
        source=ItemSource.LIBRARY.value,
        change_type=ChangeType.ADDED.value,
        name=entry.name,
        direction=entry.direction,
        unit=entry.unit,
        target=target,
        weight=entry.default_weight,
        measurement_method=entry.measurement_method,
        data_source=entry.data_source,
        accountability_layer=entry.accountability_layer,
        outcome_type=entry.outcome_type,
    )


def blank_item(card_id: str, seq: int) -> KPICardItem:
    return KPICardItem(
        card_id=card_id,
        lineage_id=new_id("LIN"),
        seq=seq,
        source=ItemSource.CUSTOM.value,
        change_type=ChangeType.ADDED.value,
        direction=Direction.HIGHER.value,
        outcome_type=OutcomeType.OUTCOME.value,
    )


def blank_kbd_item(card_id: str, pillar: str, seq: int) -> KBDItem:
    return KBDItem(
        card_id=card_id,
        lineage_id=new_id("LIN"),
        seq=seq,
        pillar=pillar,
        source=ItemSource.CUSTOM.value,
        change_type=ChangeType.ADDED.value,
        weight=1.0,
    )


def kbd_from_business_needs(
    card_id: str, needs: Iterable[BusinessNeed], start_seq: int = 0
) -> list[KBDItem]:
    """Company-wide Behaviour and Discipline items for the month.

    Applied automatically so a manager who does nothing still has a valid
    B/D set, rather than an empty pillar scoring zero.
    """
    out: list[KBDItem] = []
    seq = start_seq
    for need in needs:
        if need.pillar not in (Pillar.BEHAVIOUR.value, Pillar.DISCIPLINE.value):
            continue
        if not need.is_company_default:
            continue
        out.append(KBDItem(
            card_id=card_id,
            lineage_id=new_id("LIN"),
            seq=seq,
            pillar=need.pillar,
            source=ItemSource.BUSINESS_NEED.value,
            change_type=ChangeType.ADDED.value,
            text=need.metric,
            evidence_expected=need.note,
            weight=1.0,
        ))
        seq += 1
    return out


def seed_new_card(
    emp_id: str,
    period: str,
    set_by: str,
    previous_result: Optional[list[KPICardItem]] = None,
    previous_kbd: Optional[list[KBDItem]] = None,
    business_needs: Optional[list[BusinessNeed]] = None,
) -> tuple[KPICard, list[KPICardItem], list[KBDItem]]:
    """Create a card pre-filled from last month plus this month's baseline.

    Company B/D defaults are only added for pillars the previous card did not
    already supply, so carrying forward does not duplicate them.
    """
    card = build_card(emp_id, period, set_by)
    result_items, kbd_items = carry_forward(
        card.card_id, previous_result or [], previous_kbd or []
    )

    have = {item.pillar for item in kbd_items}
    baseline = [
        item for item in kbd_from_business_needs(
            card.card_id, business_needs or [], start_seq=len(kbd_items)
        )
        if item.pillar not in have
    ]
    return card, result_items, kbd_items + baseline


def mark_changes(
    current: list[KPICardItem] | list[KBDItem],
    original: list[KPICardItem] | list[KBDItem],
) -> list:
    """Record what the manager did to each item this month.

    Drives the audit trail and the exception review — "what changed" is the
    question management actually asks when reviewing a cascade.
    """
    originals = {item.lineage_id: item for item in original}
    out: list = []
    for item in current:
        previous = originals.get(item.lineage_id)
        if previous is None:
            change = ChangeType.ADDED.value
        elif _differs(item, previous):
            change = ChangeType.EDITED.value
        else:
            change = ChangeType.KEPT.value
        out.append(item.model_copy(update={"change_type": change}))
    return out


def deleted_items(
    current: list, original: list
) -> list:
    """Items present last month and dropped this month."""
    kept = {item.lineage_id for item in current}
    return [
        item.model_copy(update={"change_type": ChangeType.DELETED.value})
        for item in original if item.lineage_id not in kept
    ]


_COMPARED_FIELDS = (
    "name", "direction", "unit", "target", "target_max", "weight",
    "measurement_method", "data_source", "business_need_ref",
    "accountability_layer", "outcome_type", "text", "evidence_expected",
)


def _differs(left, right) -> bool:
    for field in _COMPARED_FIELDS:
        if hasattr(left, field) and getattr(left, field) != getattr(right, field, None):
            return True
    return False


# --------------------------------------------------------------------------
# State transitions
# --------------------------------------------------------------------------


def submit(card: KPICard, actor: str) -> KPICard:
    """Manager finishes setting the card and sends it to the employee."""
    if card.status not in (CardStatus.DRAFT.value, CardStatus.SUBMITTED.value):
        raise CardError(
            f"A card in '{card.status}' cannot be submitted."
        )
    return card.model_copy(update={
        "status": CardStatus.SUBMITTED.value,
        "set_by": actor,
        "submitted_at": _now(),
    })


def acknowledge(card: KPICard, actor: str) -> KPICard:
    """Employee confirms they have read and accepted the card.

    Only the employee may acknowledge — a manager acknowledging on someone's
    behalf would make the whole step meaningless.
    """
    if actor != card.emp_id:
        raise CardError("Only the employee can acknowledge their own card.")
    if card.status not in (CardStatus.SUBMITTED.value, CardStatus.AMENDED.value):
        raise CardError(
            f"A card in '{card.status}' is not awaiting acknowledgement."
        )
    return card.model_copy(update={
        "status": CardStatus.ACKNOWLEDGED.value,
        "acknowledged_at": _now(),
    })


def go_live(card: KPICard) -> KPICard:
    """Lock the card for the month. Called on the 1st."""
    if card.status not in (CardStatus.ACKNOWLEDGED.value, CardStatus.SUBMITTED.value):
        raise CardError(f"A card in '{card.status}' cannot go live.")
    return card.model_copy(update={
        "status": CardStatus.LIVE.value,
        "went_live_at": _now(),
    })


def lock(card: KPICard) -> KPICard:
    """Close the month after scoring."""
    if card.status not in (CardStatus.LIVE.value, CardStatus.AMENDED.value):
        raise CardError(f"A card in '{card.status}' cannot be locked.")
    return card.model_copy(update={
        "status": CardStatus.LOCKED.value,
        "locked_at": _now(),
    })


def is_editable(card: KPICard) -> bool:
    """Free editing is confined to the planning window."""
    return card.status in (CardStatus.DRAFT.value, CardStatus.SUBMITTED.value)


# --------------------------------------------------------------------------
# Amendments
# --------------------------------------------------------------------------


def amendment_window_open(
    period: str, today: Optional[date] = None, close_day: int = DEFAULT_AMENDMENT_CLOSE_DAY
) -> bool:
    """True from the 1st to the close day of the live month.

    After it shuts, a change belongs to next month's card. That is the point
    of a locked card — a target nobody can move mid-month is what makes the
    score mean anything.
    """
    reference = today or date.today()
    if f"{reference.year:04d}-{reference.month:02d}" != period:
        return False
    return reference <= period_date(period, close_day)


def request_amendment(
    card: KPICard,
    chart: OrgChart,
    requested_by: str,
    rationale: str,
    changes: dict,
    today: Optional[date] = None,
    close_day: int = DEFAULT_AMENDMENT_CLOSE_DAY,
) -> AmendmentRequest:
    """Raise a change against a live card. Does not apply it."""
    if card.status not in (CardStatus.LIVE.value, CardStatus.AMENDED.value):
        raise CardError(
            f"Only a live card can be amended; this one is '{card.status}'."
        )
    if not amendment_window_open(card.period, today, close_day):
        raise CardError(
            f"The amendment window for {card.period} closed on day "
            f"{close_day}. This change belongs on next month's card."
        )
    if not chart.is_direct_manager(requested_by, card.emp_id):
        raise CardError(
            "Only the employee's direct manager can request an amendment."
        )
    if not rationale.strip():
        raise CardError("An amendment needs a written rationale.")

    approver = chart.amendment_approver(requested_by)
    if approver is None:
        raise CardError(
            "Nobody sits above the requester, so this amendment has no "
            "approver. Escalate outside the system instead of self-approving."
        )

    return AmendmentRequest(
        amendment_id=new_id("AMD"),
        card_id=card.card_id,
        emp_id=card.emp_id,
        period=card.period,
        requested_by=requested_by,
        requested_at=_now(),
        rationale=rationale.strip(),
        changes_json=json.dumps(changes, default=str),
        status="pending",
        approver_emp_id=approver.emp_id,
    )


def decide_amendment(
    amendment: AmendmentRequest,
    chart: OrgChart,
    actor: str,
    approve: bool,
    note: str = "",
) -> AmendmentRequest:
    """Approve or reject. The requester can never decide their own request."""
    if amendment.status != "pending":
        raise CardError(f"This amendment is already '{amendment.status}'.")
    if actor == amendment.requested_by:
        raise CardError("An amendment cannot be approved by the person who raised it.")
    if actor != amendment.approver_emp_id:
        expected = chart.get(amendment.approver_emp_id)
        name = expected.name if expected else amendment.approver_emp_id
        raise CardError(
            f"Only {name} can decide this amendment — approval sits exactly "
            "one level above the requester."
        )
    return amendment.model_copy(update={
        "status": "approved" if approve else "rejected",
        "decided_at": _now(),
        "decision_note": note.strip(),
    })


def apply_amendment(card: KPICard, amendment: AmendmentRequest) -> KPICard:
    """Bump the version and send the card back for re-acknowledgement.

    Re-acknowledgement matters: the employee agreed to a specific set of
    targets, and a changed card is not the one they agreed to.
    """
    if amendment.status != "approved":
        raise CardError("Only an approved amendment can be applied.")
    return card.model_copy(update={
        "status": CardStatus.AMENDED.value,
        "version": card.version + 1,
        "acknowledged_at": "",
    })


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------


def carried_streak(
    lineage_ids: Iterable[str],
    history: dict[str, list[str]],
) -> dict[str, int]:
    """How many consecutive months each item has been carried unchanged.

    `history` maps lineage_id to the change_types recorded for it, most
    recent first. Feeds the staleness prompt in the quality gate.
    """
    out: dict[str, int] = {}
    for lineage_id in lineage_ids:
        streak = 0
        for change in history.get(lineage_id, []):
            if change == ChangeType.KEPT.value:
                streak += 1
            else:
                break
        out[lineage_id] = streak
    return out


def audit_card_changes(
    actor: str,
    card: KPICard,
    current: list,
    original: list,
    entity: str,
) -> list[AuditEntry]:
    """One audit row per item added, edited or deleted."""
    entries: list[AuditEntry] = []
    originals = {item.lineage_id: item for item in original}
    stamp = _now()

    for item in current:
        previous = originals.get(item.lineage_id)
        if previous is None:
            action, old, new = "create", "", _describe(item)
        elif _differs(item, previous):
            action, old, new = "update", _describe(previous), _describe(item)
        else:
            continue
        entries.append(AuditEntry(
            audit_id=new_id("AUD"), timestamp=stamp, actor=actor,
            entity=entity, entity_id=item.lineage_id, action=action,
            old_value=old, new_value=new,
            note=f"card {card.card_id} {card.period} v{card.version}",
        ))

    for item in deleted_items(current, original):
        entries.append(AuditEntry(
            audit_id=new_id("AUD"), timestamp=stamp, actor=actor,
            entity=entity, entity_id=item.lineage_id, action="delete",
            old_value=_describe(item), new_value="",
            note=f"card {card.card_id} {card.period} v{card.version}",
        ))
    return entries


def _describe(item) -> str:
    if isinstance(item, KPICardItem):
        return (
            f"{item.name} | {item.direction} | target={item.target} "
            f"{item.unit} | wt={item.weight}"
        )
    return f"{item.pillar}: {item.text} | wt={item.weight}"


def previous_period(period: str) -> str:
    return shift_period(period, -1)
