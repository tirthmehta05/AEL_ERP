"""My Work tab — your card, your deadlines, your approvals.

Acknowledgement is the step that makes a card an agreement rather than an
instruction, so this tab shows the whole card before the button, including
what changed since last month. Only the employee can acknowledge their own
card; a manager clicking it on someone's behalf would make the step
meaningless.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from src.performance.models.performance_models import (
    AuditEntry,
    CardStatus,
    ChangeType,
    Direction,
    Pillar,
    TaskStatus,
    new_id,
)
from src.performance.repository.performance_repository import (
    PerformanceRepositoryError,
)
from src.performance.service import card_service as cards
from src.performance.service.cycle_service import days_late, period_date
from pages.performance_shared import PerformanceContext, clear_caches, period_selector

STAGE_LABELS = {
    "publish_needs": "Publish business needs",
    "set_cards": "Set card",
    "acknowledge": "Acknowledge your card",
    "exception_review": "Exception review",
    "self_score": "Self-score",
    "manager_score": "Score",
    "calibrate": "Calibration",
    "lock": "Lock the month",
    "check_in": "Mid-month check-in",
    "quarterly_review": "Quarterly review",
    "quarter_validate": "Validate the quarter",
}


def render(ctx: PerformanceContext) -> None:
    _render_open_actions(ctx)
    st.markdown("---")
    _render_pending_approvals(ctx)

    period = period_selector("Month", key="perf_mywork_period")
    card = ctx.repo.get_card(ctx.emp_id, period)

    if card is None:
        st.info(
            f"No card has been set for you for {period} yet. Your manager "
            "sets it during the previous month."
        )
        return

    _render_card(ctx, card, period)


# --------------------------------------------------------------------------
# Open actions
# --------------------------------------------------------------------------


def _render_open_actions(ctx: PerformanceContext) -> None:
    st.markdown("#### Your open actions")
    try:
        tasks = ctx.repo.get_cycle_tasks(
            owner_emp_id=ctx.emp_id, status=TaskStatus.OPEN.value
        )
    except PerformanceRepositoryError:
        st.caption("Deadline tracking starts in phase 4.")
        return

    if not tasks:
        st.caption(
            "Nothing outstanding. Deadlines appear here once the cycle is "
            "generated for a month."
        )
        return

    today = date.today()
    rows = []
    for task in sorted(tasks, key=lambda t: t.due_date or date.max):
        late = days_late(task, today)
        subject = ctx.chart.get(task.subject_emp_id)
        rows.append({
            "What": STAGE_LABELS.get(task.stage, task.stage),
            "For": subject.name if subject else "—",
            "Period": task.period,
            "Due": task.due_date.strftime("%d %b") if task.due_date else "—",
            "Status": f"{late} day(s) late" if late else "on time",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------
# Amendment approvals
# --------------------------------------------------------------------------


def _render_pending_approvals(ctx: PerformanceContext) -> None:
    """Amendments waiting on this person, one level below them."""
    try:
        pending = [
            a for a in ctx.repo.get_amendments(status="pending")
            if a.approver_emp_id == ctx.emp_id
        ]
    except PerformanceRepositoryError:
        return
    if not pending:
        return

    st.markdown("#### Amendment requests awaiting you")
    st.caption(
        "Approval sits exactly one level above the requester. You cannot "
        "approve a request you raised yourself."
    )

    for amendment in pending:
        requester = ctx.chart.get(amendment.requested_by)
        subject = ctx.chart.get(amendment.emp_id)
        with st.container(border=True):
            st.markdown(
                f"**{requester.name if requester else amendment.requested_by}** "
                f"wants to change **{subject.name if subject else amendment.emp_id}**'s "
                f"{amendment.period} card"
            )
            st.markdown(f"> {amendment.rationale}")
            if amendment.changes_json:
                with st.expander("What would change"):
                    st.code(amendment.changes_json, language="json")

            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                note = st.text_input(
                    "Decision note", key=f"perf_amd_note_{amendment.amendment_id}",
                    label_visibility="collapsed", placeholder="Optional note",
                )
            with col2:
                if st.button("Approve", key=f"perf_amd_ok_{amendment.amendment_id}",
                             type="primary", use_container_width=True):
                    _decide(ctx, amendment, True, note)
            with col3:
                if st.button("Reject", key=f"perf_amd_no_{amendment.amendment_id}",
                             use_container_width=True):
                    _decide(ctx, amendment, False, note)


def _decide(ctx: PerformanceContext, amendment, approve: bool, note: str) -> None:
    try:
        decided = cards.decide_amendment(
            amendment, ctx.chart, actor=ctx.emp_id, approve=approve, note=note
        )
        ctx.repo.save_amendment(decided)

        if approve:
            card = ctx.repo.get_card(amendment.emp_id, amendment.period)
            if card is not None:
                ctx.repo.save_card(cards.apply_amendment(card, decided))
    except (cards.CardError, PerformanceRepositoryError) as exc:
        st.error(str(exc))
        return

    ctx.repo.log([AuditEntry(
        audit_id=new_id("AUD"),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        actor=ctx.emp_id, entity="Amendment", entity_id=amendment.amendment_id,
        action="approve" if approve else "reject", note=note,
    )])
    clear_caches()
    st.success("Approved." if approve else "Rejected.")
    st.rerun()


# --------------------------------------------------------------------------
# The card
# --------------------------------------------------------------------------


def _render_card(ctx: PerformanceContext, card, period: str) -> None:
    manager = ctx.chart.manager_of(ctx.emp_id)
    st.markdown(f"### Your card — {period}")
    st.caption(
        f"Status: **{card.status}** · version {card.version} · set by "
        f"{manager.name if manager else card.set_by}"
    )

    if card.status == CardStatus.DRAFT.value:
        st.info(
            f"{manager.name if manager else 'Your manager'} is still working "
            "on this. You will be asked to acknowledge it once it is sent."
        )
        return

    result_items = ctx.repo.get_card_items(card.card_id)
    _render_result(result_items)
    _render_kbd(ctx, card)

    if card.status in (CardStatus.SUBMITTED.value, CardStatus.AMENDED.value):
        _render_acknowledge(ctx, card, manager)
    elif card.status == CardStatus.ACKNOWLEDGED.value:
        st.success(
            f"You acknowledged this card on "
            f"{card.acknowledged_at[:10] or 'record'}. It goes live on the 1st."
        )
    elif card.status in (CardStatus.LIVE.value, CardStatus.LOCKED.value):
        _render_live_note(ctx, card)


def _render_result(items: list) -> None:
    st.markdown("#### Result — 60%")
    if not items:
        st.caption("No KPIs on this card.")
        return

    changed = [i for i in items if i.change_type in
               (ChangeType.ADDED.value, ChangeType.EDITED.value)]
    st.dataframe(
        pd.DataFrame([
            {
                "KPI": i.name,
                "Target": f"{i.target:g} {i.unit}".strip() if i.target is not None
                          else (i.unit or "—"),
                "Better when": "lower" if i.direction == Direction.LOWER.value
                               else i.direction,
                "Weight %": i.weight,
                "Measured by": i.measurement_method,
                "From": i.data_source,
                "New this month": "yes" if i.change_type == ChangeType.ADDED.value
                                  else ("changed" if i.change_type == ChangeType.EDITED.value
                                        else ""),
            }
            for i in items
        ]),
        use_container_width=True, hide_index=True,
    )
    total = sum(i.weight for i in items)
    st.caption(f"Weights total {total:g}%. {len(changed)} item(s) new or changed "
               "since last month.")


def _render_kbd(ctx: PerformanceContext, card) -> None:
    for pillar, weight in ((Pillar.KNOWLEDGE, 20), (Pillar.BEHAVIOUR, 10),
                           (Pillar.DISCIPLINE, 10)):
        items = ctx.repo.get_kbd_items(card.card_id, pillar.value)
        st.markdown(f"#### {pillar.value} — {weight}%")
        if not items:
            st.caption("Nothing set for this pillar.")
            continue
        for item in items:
            evidence = (f"  \n  _Evidence: {item.evidence_expected}_"
                        if item.evidence_expected else "")
            flag = " **(new)**" if item.change_type == ChangeType.ADDED.value else ""
            st.markdown(f"- {item.text}{flag}{evidence}")


def _render_acknowledge(ctx: PerformanceContext, card, manager) -> None:
    st.markdown("---")
    if card.status == CardStatus.AMENDED.value:
        st.warning(
            "This card was amended after you first accepted it, so it needs "
            "your acknowledgement again."
        )

    st.markdown("#### Acknowledge")
    st.caption(
        "Confirming means you have read the card and understand what you are "
        "being measured on. If something looks wrong, raise it with "
        f"{manager.name if manager else 'your manager'} before accepting — "
        "once it goes live on the 1st it is locked for the month."
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("I acknowledge this card", type="primary",
                     use_container_width=True):
            _acknowledge(ctx, card)
    with col2:
        query = st.text_input(
            "Raise a query instead", placeholder="What does not look right?",
            key=f"perf_ack_query_{card.card_id}", label_visibility="collapsed",
        )
        if st.button("Send query", disabled=not query.strip()):
            ctx.repo.log([AuditEntry(
                audit_id=new_id("AUD"),
                timestamp=datetime.now().isoformat(timespec="seconds"),
                actor=ctx.emp_id, entity="KPICard", entity_id=card.card_id,
                action="query", new_value=query.strip(),
                note=f"{card.period} v{card.version}",
            )])
            st.success(
                "Query recorded against the card. Follow it up with your "
                "manager directly — the card stays unacknowledged until it is "
                "resolved."
            )


def _acknowledge(ctx: PerformanceContext, card) -> None:
    try:
        acknowledged = cards.acknowledge(card, ctx.emp_id)
        ctx.repo.save_card(acknowledged)
    except (cards.CardError, PerformanceRepositoryError) as exc:
        st.error(str(exc))
        return

    ctx.repo.log([AuditEntry(
        audit_id=new_id("AUD"),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        actor=ctx.emp_id, entity="KPICard", entity_id=card.card_id,
        action="acknowledge", new_value=f"{card.period} v{card.version}",
    )])
    clear_caches()
    st.success("Acknowledged.")
    st.rerun()


def _render_live_note(ctx: PerformanceContext, card) -> None:
    st.markdown("---")
    params = ctx.repo.get_parameters()
    close_day = int(params.get("cycle.amendment_close_day", 10))

    if card.status == CardStatus.LOCKED.value:
        st.info("This month is closed.")
        return

    if cards.amendment_window_open(card.period, close_day=close_day):
        closes = period_date(card.period, close_day)
        st.info(
            f"This card is live and locked for the month. Your manager can "
            f"still request a change until {closes.strftime('%d %b')}, with "
            "approval from their own manager."
        )
    else:
        st.info(
            "This card is live and closed to changes. Anything that needs to "
            "change belongs on next month's card."
        )
