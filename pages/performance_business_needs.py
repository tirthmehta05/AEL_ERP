"""Business Needs tab — what the company needs this month.

Publishing is the top of the cascade: nothing else in the planning window can
start until management says what the month is for. The tab carries two kinds
of content in one place, because both cascade the same way:

* **Result needs** — numeric company targets, copied from the Scaling Plan's
  Monthly Targets. Managers link KPIs to these, which is what makes a card
  visibly derived from the business rather than invented.
* **Behaviour / Discipline baseline** — the company-wide items applied to
  every card automatically, so a manager who does nothing still has valid
  qualitative pillars instead of an empty one scoring zero.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.performance import seed_data
from src.performance.models.performance_models import (
    AuditEntry,
    BusinessNeed,
    Pillar,
    new_id,
)
from src.performance.repository.performance_repository import (
    PerformanceRepositoryError,
)
from src.performance.service.cycle_service import period_date, shift_period
from pages.performance_shared import PerformanceContext, period_selector

AREAS = ["Trading", "Manufacturing", "Corporate Services", "Strategy & BD",
         "Company-wide"]


def render(ctx: PerformanceContext) -> None:
    st.caption(
        "Published by management before the cascade starts. Managers link "
        "their team's KPIs to these, and the Behaviour/Discipline baseline "
        "is applied to every card automatically."
    )

    period = period_selector("Month being planned", key="perf_bn_period")
    needs = ctx.repo.get_business_needs(period)

    _render_status(ctx, period, needs)

    if not ctx.is_management:
        _render_read_only(needs)
        return

    tabs = st.tabs(["Company targets", "Behaviour & Discipline baseline"])
    with tabs[0]:
        _render_result_needs(ctx, period, needs)
    with tabs[1]:
        _render_kbd_baseline(ctx, period, needs)


def _render_status(ctx: PerformanceContext, period: str, needs: list) -> None:
    publish_by = period_date(
        shift_period(period, -1),
        int(ctx.repo.get_parameters().get("cycle.publish_needs_day", 18)),
    )
    result_count = sum(1 for n in needs if n.pillar == Pillar.RESULT.value)
    kbd_count = len(needs) - result_count

    col1, col2, col3 = st.columns(3)
    col1.metric("Company targets", result_count)
    col2.metric("B/D baseline items", kbd_count)
    col3.metric("Publish by", publish_by.strftime("%d %b"))

    if not needs:
        st.warning(
            f"Nothing published for {period} yet. Cards set for this month "
            "will have no business needs to link to."
        )


def _render_read_only(needs: list) -> None:
    if not needs:
        return
    st.info("Only management can publish business needs.")
    _show_table(needs)


def _show_table(needs: list) -> None:
    st.dataframe(
        pd.DataFrame([
            {
                "Ref": n.need_id,
                "Pillar": n.pillar,
                "Area": n.area,
                "Metric": n.metric,
                "Target": n.target,
                "Unit": n.unit,
                "Note": n.note,
            }
            for n in needs
        ]),
        use_container_width=True, hide_index=True,
    )


# --------------------------------------------------------------------------
# Company targets
# --------------------------------------------------------------------------


def _render_result_needs(ctx: PerformanceContext, period: str, needs: list) -> None:
    existing = [n for n in needs if n.pillar == Pillar.RESULT.value]

    st.markdown("#### This month's company targets")
    st.caption(
        "Copy the month's column from the Scaling Plan's Monthly Targets "
        "sheet. Keep the metric names recognisable — managers pick from these "
        "when linking a KPI."
    )

    seed_rows = [
        {"Area": n.area, "Metric": n.metric, "Target": n.target,
         "Unit": n.unit, "Note": n.note}
        for n in existing
    ] or [{"Area": "Trading", "Metric": "", "Target": "", "Unit": "", "Note": ""}]

    edited = st.data_editor(
        pd.DataFrame(seed_rows),
        num_rows="dynamic",
        use_container_width=True,
        key=f"perf_bn_editor_{period}",
        column_config={
            "Area": st.column_config.SelectboxColumn(options=AREAS, required=True),
            "Metric": st.column_config.TextColumn(required=True, width="large"),
            "Target": st.column_config.TextColumn(
                help="Free text — a number, a band like '< 10', or a milestone."
            ),
            "Unit": st.column_config.TextColumn(width="small"),
            "Note": st.column_config.TextColumn(width="large"),
        },
    )

    carry_from = shift_period(period, -1)
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Copy last month", use_container_width=True,
                     help=f"Load the targets published for {carry_from}."):
            _copy_previous(ctx, period, carry_from)
    with col2:
        if st.button(f"Publish {period} targets", type="primary"):
            _publish_result(ctx, period, edited, existing)


def _copy_previous(ctx: PerformanceContext, period: str, source: str) -> None:
    previous = [
        n for n in ctx.repo.get_business_needs(source)
        if n.pillar == Pillar.RESULT.value
    ]
    if not previous:
        st.warning(f"Nothing was published for {source}.")
        return
    st.session_state[f"perf_bn_carried_{period}"] = [
        {"Area": n.area, "Metric": n.metric, "Target": n.target,
         "Unit": n.unit, "Note": n.note}
        for n in previous
    ]
    st.info(
        f"Loaded {len(previous)} targets from {source}. Review the numbers — "
        "they are last month's — then publish."
    )


def _publish_result(
    ctx: PerformanceContext, period: str, edited: pd.DataFrame, existing: list
) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    rows = [
        row for _, row in edited.iterrows()
        if str(row.get("Metric", "")).strip()
    ]
    if not rows:
        st.error("Nothing to publish — add at least one target.")
        return

    needs = [
        BusinessNeed(
            need_id=f"BN-{period}-{index + 1:02d}",
            period=period,
            pillar=Pillar.RESULT.value,
            area=str(row.get("Area", "")).strip(),
            metric=str(row.get("Metric", "")).strip(),
            unit=str(row.get("Unit", "")).strip(),
            target=str(row.get("Target", "")).strip(),
            note=str(row.get("Note", "")).strip(),
            is_company_default=False,
            published_by=ctx.emp_id,
            published_at=stamp,
        )
        for index, row in enumerate(rows)
    ]

    # Republishing replaces the month's Result rows; the B/D baseline is
    # written separately and must survive.
    keep = [n for n in ctx.repo.get_business_needs(period)
            if n.pillar != Pillar.RESULT.value]
    try:
        ctx.repo.replace_business_needs(period, keep + needs)
    except PerformanceRepositoryError as exc:
        st.error(f"Could not publish: {exc}")
        return

    ctx.repo.log([AuditEntry(
        audit_id=new_id("AUD"), timestamp=stamp, actor=ctx.emp_id,
        entity="BusinessNeeds", entity_id=period,
        action="publish" if not existing else "republish",
        old_value=f"{len(existing)} targets", new_value=f"{len(needs)} targets",
    )])
    st.success(f"Published {len(needs)} company targets for {period}.")
    st.rerun()


# --------------------------------------------------------------------------
# Behaviour & Discipline baseline
# --------------------------------------------------------------------------


def _render_kbd_baseline(ctx: PerformanceContext, period: str, needs: list) -> None:
    existing = [n for n in needs if n.pillar in
                (Pillar.BEHAVIOUR.value, Pillar.DISCIPLINE.value)]

    st.markdown("#### Company-wide Behaviour & Discipline")
    st.caption(
        "Applied to every card automatically. Managers may add per-person "
        "items on top, and may remove a default — that is allowed, but it is "
        "surfaced to you in the exception review."
    )

    if existing:
        for pillar in (Pillar.BEHAVIOUR, Pillar.DISCIPLINE):
            items = [n for n in existing if n.pillar == pillar.value]
            if not items:
                continue
            st.markdown(f"**{pillar.value}** — {len(items)} items")
            for item in items:
                st.markdown(f"- **{item.metric}** — {item.note or '_no description_'}")
        st.caption(
            "Knowledge has no company default on purpose — a learning goal is "
            "personal, and a shared default would invite exactly the "
            "copy-paste the remark rules exist to prevent."
        )

    st.markdown("---")
    default_source = (
        "the six company Values and the Rating Guide's discipline rubric"
    )
    if st.button(
        f"Apply standard baseline to {period}",
        type="primary" if not existing else "secondary",
        help=f"Publishes {default_source}.",
    ):
        _publish_baseline(ctx, period, existing)

    if existing:
        st.caption(
            f"{len(existing)} baseline items already published for {period}. "
            "Re-applying replaces them."
        )


def _publish_baseline(ctx: PerformanceContext, period: str, existing: list) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    baseline: list[BusinessNeed] = []
    for pillar, defaults in (
        (Pillar.BEHAVIOUR, seed_data.BEHAVIOUR_DEFAULTS),
        (Pillar.DISCIPLINE, seed_data.DISCIPLINE_DEFAULTS),
    ):
        for metric, note in defaults:
            baseline.append(BusinessNeed(
                need_id=new_id("BN"),
                period=period,
                pillar=pillar.value,
                area="Company-wide",
                metric=metric,
                note=note,
                is_company_default=True,
                published_by=ctx.emp_id,
                published_at=stamp,
            ))

    keep = [n for n in ctx.repo.get_business_needs(period)
            if n.pillar == Pillar.RESULT.value]
    try:
        ctx.repo.replace_business_needs(period, keep + baseline)
    except PerformanceRepositoryError as exc:
        st.error(f"Could not publish: {exc}")
        return

    ctx.repo.log([AuditEntry(
        audit_id=new_id("AUD"), timestamp=stamp, actor=ctx.emp_id,
        entity="BusinessNeeds", entity_id=f"{period}/baseline",
        action="publish", old_value=f"{len(existing)} items",
        new_value=f"{len(baseline)} items",
    )])
    st.success(f"Applied {len(baseline)} baseline items to {period}.")
    st.rerun()
