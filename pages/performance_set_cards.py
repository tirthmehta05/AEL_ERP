"""Set Cards tab — the four-pillar card editor.

The manager's monthly job. Every pillar is an editable list seeded from last
month, because Amba deliberately did not adopt the workbook's yearly KPI
freeze: reuse is the default, but any item can be edited, deleted or added.

Three things the UI has to get right:

* **Show last month's outcome next to this month's target.** Setting a number
  without seeing what actually happened is how targets drift from reality.
* **Never silently break lineage.** Editing keeps an item's history; only an
  explicit delete ends the series. The editor makes that distinction visible.
* **Explain refusals.** The quality gate blocks submission, so it has to say
  what is wrong and why, not just refuse.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from src.performance.models.performance_models import (
    AuditEntry,
    CardStatus,
    Direction,
    Employee,
    KBDItem,
    KPICardItem,
    OutcomeType,
    Pillar,
    new_id,
)
from src.performance.repository.performance_repository import (
    PerformanceRepositoryError,
)
from src.performance.service import card_service as cards
from src.performance.service.kpi_quality import (
    Severity,
    blocking,
    validate_card,
)
from src.performance.service.prompt_builder import build_prompt, parse_draft
from pages.performance_shared import PerformanceContext, clear_caches, period_selector

DIRECTIONS = [d.value for d in Direction]
OUTCOMES = [o.value for o in OutcomeType]

RESULT_COLUMNS = [
    "Keep", "KPI", "Direction", "Unit", "Target", "Weight %",
    "How measured", "Data source", "Type", "Links to", "_lineage",
]
KBD_COLUMNS = ["Keep", "Item", "Evidence expected", "Weight", "_lineage"]


def render(ctx: PerformanceContext) -> None:
    reports = ctx.direct_reports
    if not reports:
        st.info(
            "You have no direct reports, so there are no cards for you to set. "
            "Your own card appears under My Work."
        )
        return

    period = period_selector("Month being planned", key="perf_setcards_period")
    st.caption(
        f"Setting cards for {period}. Cards go live on the 1st and are locked "
        "for the month after that."
    )

    _render_team_status(ctx, reports, period)
    st.markdown("---")

    names = {f"{e.name} — {e.designation or e.level}": e.emp_id for e in reports}
    chosen = st.selectbox("Whose card?", list(names), key="perf_setcards_who")
    employee = ctx.chart.get(names[chosen])
    if employee is None:
        return

    _render_editor(ctx, employee, period)


# --------------------------------------------------------------------------
# Team overview
# --------------------------------------------------------------------------


def _render_team_status(
    ctx: PerformanceContext, reports: list[Employee], period: str
) -> None:
    cards_by_emp = {c.emp_id: c for c in ctx.repo.get_cards(period=period)}
    rows = []
    for employee in reports:
        card = cards_by_emp.get(employee.emp_id)
        rows.append({
            "Name": employee.name,
            "Depth": ctx.chart.depth(employee.emp_id),
            "Status": card.status if card else "not started",
            "Version": card.version if card else "—",
            "Acknowledged": "yes" if card and card.acknowledged_at else "no",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------
# Editor
# --------------------------------------------------------------------------


def _render_editor(
    ctx: PerformanceContext, employee: Employee, period: str
) -> None:
    card = ctx.repo.get_card(employee.emp_id, period)
    previous_period = cards.previous_period(period)

    if card is None:
        _render_start(ctx, employee, period, previous_period)
        return

    if not cards.is_editable(card):
        _render_locked(ctx, employee, card)
        return

    result_items = ctx.repo.get_card_items(card.card_id)
    kbd_items = ctx.repo.get_kbd_items(card.card_id)
    needs = ctx.repo.get_business_needs(period)
    params = ctx.repo.get_parameters()

    st.markdown(f"### {employee.name} — {period}")
    st.caption(f"Status: **{card.status}** · version {card.version}")

    previous_actuals = _previous_actuals(ctx, employee.emp_id, previous_period)

    result_edited = _render_result_pillar(
        card.card_id, result_items, needs, previous_actuals
    )
    kbd_edited = _render_kbd_pillars(card.card_id, kbd_items)

    findings = validate_card(
        result_edited, kbd_edited, params,
        business_need_refs=[n.need_id for n in needs],
    )
    _render_gate(findings)

    _render_ai_helper(ctx, employee, period, card, result_items, kbd_items,
                      previous_actuals)

    st.markdown("---")
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Save draft", use_container_width=True):
            _save(ctx, card, result_edited, kbd_edited, result_items, kbd_items)
    with col2:
        disabled = bool(blocking(findings))
        if st.button(
            f"Submit to {employee.name}", type="primary", disabled=disabled,
            help="Blocked until the issues above are resolved." if disabled else None,
        ):
            _save(ctx, card, result_edited, kbd_edited, result_items, kbd_items)
            _submit(ctx, card, employee)


def _render_start(
    ctx: PerformanceContext, employee: Employee, period: str, previous: str
) -> None:
    previous_card = ctx.repo.get_card(employee.emp_id, previous)
    needs = ctx.repo.get_business_needs(period)

    st.markdown(f"### {employee.name} — {period}")
    if previous_card:
        st.info(
            f"Their {previous} card will be carried forward — every item "
            "editable, with last month's target and actual shown alongside."
        )
    else:
        st.info(
            f"No card exists for {previous}, so this one starts from the KPI "
            "library and the published business needs."
        )
    if not needs:
        st.warning(
            f"No business needs are published for {period}. Cards can still "
            "be set, but nothing will cascade from the company's targets and "
            "the Behaviour/Discipline baseline will be empty."
        )

    if not st.button(f"Start {employee.name}'s card", type="primary"):
        return

    previous_result = ctx.repo.get_card_items(previous_card.card_id) if previous_card else []
    previous_kbd = ctx.repo.get_kbd_items(previous_card.card_id) if previous_card else []

    card, result_items, kbd_items = cards.seed_new_card(
        employee.emp_id, period, ctx.emp_id,
        previous_result=previous_result, previous_kbd=previous_kbd,
        business_needs=needs,
    )
    try:
        ctx.repo.save_card(card)
        ctx.repo.replace_card_items(card.card_id, result_items, kbd_items)
    except PerformanceRepositoryError as exc:
        st.error(f"Could not create the card: {exc}")
        return
    st.rerun()


def _render_locked(ctx: PerformanceContext, employee: Employee, card) -> None:
    st.info(
        f"**{employee.name}'s {card.period} card is {card.status}** and no "
        "longer freely editable."
    )
    if card.status in (CardStatus.LIVE.value, CardStatus.AMENDED.value):
        st.caption(
            "A live card changes only through an amendment request, approved "
            "one level above you, and only up to day 10."
        )
    _render_readonly_items(ctx, card)


def _render_readonly_items(ctx: PerformanceContext, card) -> None:
    result_items = ctx.repo.get_card_items(card.card_id)
    if result_items:
        st.dataframe(
            pd.DataFrame([
                {"KPI": i.name, "Direction": i.direction,
                 "Target": i.target, "Unit": i.unit, "Weight %": i.weight}
                for i in result_items
            ]),
            use_container_width=True, hide_index=True,
        )
    for pillar in (Pillar.KNOWLEDGE, Pillar.BEHAVIOUR, Pillar.DISCIPLINE):
        items = ctx.repo.get_kbd_items(card.card_id, pillar.value)
        if items:
            st.markdown(f"**{pillar.value}**")
            for item in items:
                st.markdown(f"- {item.text}")


# --------------------------------------------------------------------------
# Result pillar
# --------------------------------------------------------------------------


def _render_result_pillar(
    card_id: str,
    items: list[KPICardItem],
    needs: list,
    previous_actuals: dict[str, tuple[Optional[float], Optional[float]]],
) -> list[KPICardItem]:
    st.markdown("#### Result — 60% of the score")

    if previous_actuals:
        with st.expander("How last month actually went", expanded=True):
            rows = []
            for item in items:
                target, actual = previous_actuals.get(item.lineage_id, (None, None))
                if target is None and actual is None:
                    continue
                rows.append({
                    "KPI": item.name,
                    "Last target": target,
                    "Last actual": actual,
                    "Achieved": _achievement(item.direction, target, actual),
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True,
                             hide_index=True)
            else:
                st.caption("No scored history for these items yet.")

    need_options = [""] + [n.need_id for n in needs
                           if n.pillar == Pillar.RESULT.value]

    frame = pd.DataFrame([
        {
            "Keep": True,
            "KPI": item.name,
            "Direction": item.direction,
            "Unit": item.unit,
            "Target": item.target,
            "Weight %": item.weight,
            "How measured": item.measurement_method,
            "Data source": item.data_source,
            "Type": item.outcome_type,
            "Links to": item.business_need_ref,
            "_lineage": item.lineage_id,
        }
        for item in items
    ], columns=RESULT_COLUMNS)

    edited = st.data_editor(
        frame,
        num_rows="dynamic",
        use_container_width=True,
        key=f"perf_result_editor_{card_id}",
        column_config={
            "Keep": st.column_config.CheckboxColumn(
                help="Uncheck to drop this KPI from the month. Editing a row "
                     "keeps its history; dropping and re-adding starts a new "
                     "series.",
                default=True, width="small",
            ),
            "KPI": st.column_config.TextColumn(required=True, width="medium"),
            "Direction": st.column_config.SelectboxColumn(
                options=DIRECTIONS, required=True, width="small",
                help="'lower' for scrap, DSO, downtime, lead time, error "
                     "counts — anything where a smaller number is better.",
            ),
            "Target": st.column_config.NumberColumn(width="small"),
            "Weight %": st.column_config.NumberColumn(
                min_value=0, max_value=100, step=1, width="small",
            ),
            "Type": st.column_config.SelectboxColumn(
                options=OUTCOMES, width="small",
                help="Outcome = business result, Output = deliverable, "
                     "Activity = effort.",
            ),
            "Links to": st.column_config.SelectboxColumn(
                options=need_options, width="small",
                help="The business need this KPI cascades from.",
            ),
            "_lineage": None,   # hidden: carries item identity
        },
    )

    existing = {item.lineage_id: item for item in items}
    out: list[KPICardItem] = []
    for seq, (_, row) in enumerate(edited.iterrows()):
        if not row.get("Keep", True):
            continue
        if not str(row.get("KPI", "")).strip():
            continue
        lineage = str(row.get("_lineage") or "").strip() or new_id("LIN")
        previous = existing.get(lineage)
        out.append(KPICardItem(
            card_id=card_id,
            lineage_id=lineage,
            seq=seq,
            kpi_id=previous.kpi_id if previous else "",
            source=previous.source if previous else "custom",
            change_type="kept" if previous else "added",
            name=str(row.get("KPI", "")).strip(),
            direction=str(row.get("Direction") or Direction.HIGHER.value),
            unit=str(row.get("Unit") or "").strip(),
            target=_float(row.get("Target")),
            weight=_float(row.get("Weight %")) or 0.0,
            measurement_method=str(row.get("How measured") or "").strip(),
            data_source=str(row.get("Data source") or "").strip(),
            business_need_ref=str(row.get("Links to") or "").strip(),
            accountability_layer=previous.accountability_layer if previous else "L1 Execution",
            outcome_type=str(row.get("Type") or OutcomeType.OUTCOME.value),
        ))

    total = sum(item.weight for item in out)
    st.caption(f"Weights total **{total:g}%** across {len(out)} KPIs (must be 100).")
    return out


# --------------------------------------------------------------------------
# Knowledge / Behaviour / Discipline
# --------------------------------------------------------------------------


def _render_kbd_pillars(card_id: str, items: list[KBDItem]) -> list[KBDItem]:
    out: list[KBDItem] = []
    weights = {Pillar.KNOWLEDGE: 20, Pillar.BEHAVIOUR: 10, Pillar.DISCIPLINE: 10}
    hints = {
        Pillar.KNOWLEDGE: "What they will learn, and what would prove it. "
                          "Personal to this person — no company default.",
        Pillar.BEHAVIOUR: "Company values apply to everyone; add a personal "
                          "focus only if there is one.",
        Pillar.DISCIPLINE: "Company standards apply to everyone; add a "
                           "personal focus only if there is one.",
    }

    for pillar in (Pillar.KNOWLEDGE, Pillar.BEHAVIOUR, Pillar.DISCIPLINE):
        st.markdown(f"#### {pillar.value} — {weights[pillar]}% of the score")
        st.caption(hints[pillar])
        pillar_items = [i for i in items if i.pillar == pillar.value]

        frame = pd.DataFrame([
            {
                "Keep": True,
                "Item": item.text,
                "Evidence expected": item.evidence_expected,
                "Weight": item.weight,
                "_lineage": item.lineage_id,
            }
            for item in pillar_items
        ], columns=KBD_COLUMNS)

        config = {
            "Keep": st.column_config.CheckboxColumn(default=True, width="small"),
            "Item": st.column_config.TextColumn(required=True, width="large"),
            "Weight": st.column_config.NumberColumn(
                min_value=0.0, step=0.5, width="small",
                help="Relative weight inside this pillar. Leave at 1 to weigh "
                     "all items equally.",
            ),
            "_lineage": None,
        }
        if pillar is Pillar.KNOWLEDGE:
            config["Evidence expected"] = st.column_config.TextColumn(
                required=True, width="large",
                help="What will you ask them to show at month end? Required — "
                     "a goal with no evidence cannot be rated honestly.",
            )
        else:
            config["Evidence expected"] = st.column_config.TextColumn(
                width="large", help="Optional context."
            )

        edited = st.data_editor(
            frame, num_rows="dynamic", use_container_width=True,
            key=f"perf_kbd_editor_{card_id}_{pillar.value}",
            column_config=config,
        )

        existing = {item.lineage_id: item for item in pillar_items}
        for seq, (_, row) in enumerate(edited.iterrows()):
            if not row.get("Keep", True):
                continue
            if not str(row.get("Item", "")).strip():
                continue
            lineage = str(row.get("_lineage") or "").strip() or new_id("LIN")
            previous = existing.get(lineage)
            out.append(KBDItem(
                card_id=card_id,
                lineage_id=lineage,
                seq=seq,
                pillar=pillar.value,
                source=previous.source if previous else "custom",
                change_type="kept" if previous else "added",
                text=str(row.get("Item", "")).strip(),
                evidence_expected=str(row.get("Evidence expected") or "").strip(),
                weight=_float(row.get("Weight")) or 1.0,
            ))
    return out


# --------------------------------------------------------------------------
# Quality gate
# --------------------------------------------------------------------------


def _render_gate(findings) -> None:
    st.markdown("#### Quality check")
    blocks = [f for f in findings if f.severity is Severity.BLOCK]
    warns = [f for f in findings if f.severity is Severity.WARN]
    infos = [f for f in findings if f.severity is Severity.INFO]

    if not findings:
        st.success("No issues. Ready to submit.")
        return

    if blocks:
        st.error(f"{len(blocks)} issue(s) must be fixed before submitting:")
        for finding in blocks:
            st.markdown(f"- {finding.message}")
    if warns:
        st.warning(
            f"{len(warns)} thing(s) management will see in the exception "
            "review — allowed, but worth a second look:"
        )
        for finding in warns:
            st.markdown(f"- {finding.message}")
    if infos:
        with st.expander(f"{len(infos)} note(s)"):
            for finding in infos:
                st.markdown(f"- {finding.message}")
    if not blocks:
        st.success("Nothing blocking. Ready to submit.")


# --------------------------------------------------------------------------
# AI helper
# --------------------------------------------------------------------------


def _render_ai_helper(
    ctx: PerformanceContext,
    employee: Employee,
    period: str,
    card,
    result_items: list[KPICardItem],
    kbd_items: list[KBDItem],
    previous_actuals: dict,
) -> None:
    with st.expander("Draft with AI"):
        st.caption(
            "Copy this into Copilot or ChatGPT, then paste the reply back. "
            "Nothing is sent anywhere from here — you stay the author. Use it "
            "to sharpen wording and make goals measurable, not to pick target "
            "numbers; those come from the Scaling Plan."
        )

        role = ctx.repo.get_role_for(employee.designation)
        manager = ctx.chart.manager_of(employee.emp_id)
        prompt = build_prompt(
            employee, period, role=role,
            business_needs=ctx.repo.get_business_needs(period),
            previous_result=result_items, previous_kbd=kbd_items,
            previous_actuals={k: v[1] for k, v in previous_actuals.items()
                              if v[1] is not None},
            manager_name=manager.name if manager else "",
        )
        st.code(prompt, language="markdown")

        pasted = st.text_area(
            "Paste the reply here", height=200,
            key=f"perf_ai_paste_{card.card_id}",
        )
        if st.button("Load draft into the card", disabled=not pasted.strip()):
            draft = parse_draft(
                pasted, card.card_id,
                existing_result=result_items, existing_kbd=kbd_items,
            )
            if draft.errors:
                for error in draft.errors:
                    st.error(error)
            if draft.result_items or draft.kbd_items:
                try:
                    ctx.repo.replace_card_items(
                        card.card_id, draft.result_items, draft.kbd_items
                    )
                except PerformanceRepositoryError as exc:
                    st.error(f"Could not save the draft: {exc}")
                    return
                st.success(
                    f"Loaded {len(draft.result_items)} KPIs and "
                    f"{len(draft.kbd_items)} K/B/D items. "
                    f"{draft.matched_lineage} kept their history. Review "
                    "everything before submitting."
                )
                st.rerun()


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def _save(
    ctx: PerformanceContext, card, result_edited, kbd_edited,
    result_original, kbd_original,
) -> None:
    result_marked = cards.mark_changes(result_edited, result_original)
    kbd_marked = cards.mark_changes(kbd_edited, kbd_original)
    try:
        ctx.repo.replace_card_items(card.card_id, result_marked, kbd_marked)
    except PerformanceRepositoryError as exc:
        st.error(f"Could not save: {exc}")
        return

    entries = cards.audit_card_changes(
        ctx.emp_id, card, result_marked, result_original, "KPICardItem"
    ) + cards.audit_card_changes(
        ctx.emp_id, card, kbd_marked, kbd_original, "KBDItem"
    )
    if entries:
        ctx.repo.log(entries)
    st.success(f"Saved. {len(entries)} change(s) recorded.")


def _submit(ctx: PerformanceContext, card, employee: Employee) -> None:
    try:
        submitted = cards.submit(card, ctx.emp_id)
        ctx.repo.save_card(submitted)
    except (cards.CardError, PerformanceRepositoryError) as exc:
        st.error(str(exc))
        return

    ctx.repo.log([AuditEntry(
        audit_id=new_id("AUD"),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        actor=ctx.emp_id, entity="KPICard", entity_id=card.card_id,
        action="submit", new_value=f"{card.period} v{card.version}",
    )])
    clear_caches()
    st.success(
        f"Sent to {employee.name} for acknowledgement. They will see it under "
        "My Work."
    )
    st.rerun()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _previous_actuals(
    ctx: PerformanceContext, emp_id: str, period: str
) -> dict[str, tuple[Optional[float], Optional[float]]]:
    """Last month's target and actual, keyed by lineage.

    Setting a target without seeing what happened is how targets drift from
    reality, so this is shown next to the editor rather than buried.
    """
    card = ctx.repo.get_card(emp_id, period)
    if card is None:
        return {}
    targets = {i.lineage_id: i.target for i in ctx.repo.get_card_items(card.card_id)}
    scores = ctx.repo.get_score_items(emp_id=emp_id, period=period, stage="locked")
    if not scores:
        scores = ctx.repo.get_score_items(emp_id=emp_id, period=period, stage="manager")
    actuals = {s.lineage_id: s.actual for s in scores}
    return {
        lineage: (targets.get(lineage), actuals.get(lineage))
        for lineage in set(targets) | set(actuals)
    }


def _achievement(direction: str, target, actual) -> str:
    if target is None or actual is None:
        return "—"
    try:
        if direction == Direction.LOWER.value:
            ratio = 120.0 if actual == 0 else target / actual
        else:
            if target == 0:
                return "—"
            ratio = actual / target
    except (TypeError, ZeroDivisionError):
        return "—"
    return f"{min(120.0, ratio * 100):.0f}%"


def _float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
