"""Admin tab — org tree, employees, KPI library and cadence parameters.

The org tree is the substrate for every permission in the system, so this tab
does two things beyond plain CRUD: it validates before writing (a reports_to
cycle written to the sheet breaks depth resolution for everyone underneath
it), and it surfaces a standing health check so problems like a missing email
are visible rather than discovered at sign-in.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from src.performance.models.performance_models import AuditEntry, Employee, new_id
from src.performance.repository.performance_repository import (
    PerformanceRepositoryError,
)
from src.performance.service.cycle_service import DEFAULT_CYCLE_PARAMS
from src.performance.service.org_service import OrgChart
from pages.performance_shared import PerformanceContext, clear_caches

LEVEL_OPTIONS = ["MD", "Director", "VP", "Sr. Associate", "Associate"]
DEPARTMENTS = ["Executive", "Operations", "Corporate Services", "Strategy & BD"]


def render(ctx: PerformanceContext) -> None:
    if not ctx.is_admin:
        st.info(
            f"**{ctx.employee.name}** is not a system administrator, so this "
            f"tab is read-locked. Administrators: {_admin_names(ctx)}."
        )
        if ctx.impersonating:
            st.caption(
                "You are in dev mode — switch the *Acting as* picker above to "
                "an admin to use this tab."
            )
        return

    tabs = st.tabs(["Org tree", "Employees", "KPI library", "Cadence"])
    with tabs[0]:
        _render_tree(ctx)
    with tabs[1]:
        _render_employees(ctx)
    with tabs[2]:
        _render_library(ctx)
    with tabs[3]:
        _render_cadence(ctx)


def _admin_names(ctx: PerformanceContext) -> str:
    admins = [e.name for e in ctx.chart.all_employees() if ctx.chart.is_admin(e.emp_id)]
    return ", ".join(admins) if admins else "an administrator"


# --------------------------------------------------------------------------
# Org tree
# --------------------------------------------------------------------------


def _render_tree(ctx: PerformanceContext) -> None:
    problems = ctx.chart.validate_tree()
    if problems:
        st.error(f"{len(problems)} issue(s) need attention:")
        for problem in problems:
            st.markdown(f"- {problem}")
    else:
        st.success("Hierarchy is healthy.")

    management = ctx.chart.management()
    st.markdown("#### Management")
    st.caption(
        "Derived from the tree — the MD plus everyone reporting directly to "
        "them. Calibrates scores, locks months, publishes business needs and "
        "validates quarters. Change it by changing who reports to whom, not "
        "by setting a flag."
    )
    st.markdown(" · ".join(f"**{e.name}** ({e.level})" for e in management) or "_none_")

    st.markdown("#### Reporting structure")
    root = ctx.chart.root()
    if root is None:
        st.warning("No root employee — someone must have no manager.")
        return

    lines: list[str] = []

    def walk(emp: Employee, prefix: str, is_last: bool, is_root: bool) -> None:
        connector = "" if is_root else ("└── " if is_last else "├── ")
        flags = []
        if ctx.chart.is_management(emp.emp_id):
            flags.append("mgmt")
        if emp.is_admin:
            flags.append("admin")
        if not emp.email:
            flags.append("NO EMAIL")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        lines.append(
            f"{prefix}{connector}{emp.name} — {emp.designation or emp.level}"
            f"  (d{ctx.chart.depth(emp.emp_id)}){suffix}"
        )
        children = ctx.chart.direct_reports(emp.emp_id)
        child_prefix = prefix if is_root else prefix + ("    " if is_last else "│   ")
        for index, child in enumerate(children):
            walk(child, child_prefix, index == len(children) - 1, False)

    walk(root, "", True, True)
    st.code("\n".join(lines), language=None)

    counts = {}
    for emp in ctx.chart.all_employees():
        counts[ctx.chart.depth(emp.emp_id)] = counts.get(ctx.chart.depth(emp.emp_id), 0) + 1
    st.caption(
        "Depth drives every deadline — cards cascade down by depth and "
        "scoring cascades up by depth. Headcount by depth: "
        + ", ".join(f"d{d}: {n}" for d, n in sorted(counts.items()))
    )


# --------------------------------------------------------------------------
# Employees
# --------------------------------------------------------------------------


def _render_employees(ctx: PerformanceContext) -> None:
    employees = ctx.chart.all_employees(include_inactive=True)

    frame = pd.DataFrame([
        {
            "ID": e.emp_id,
            "Name": e.name,
            "Email": e.email or "— missing —",
            "Designation": e.designation,
            "Level": e.level,
            "Depth": ctx.chart.depth(e.emp_id),
            "Reports to": _name_of(ctx.chart, e.reports_to_emp_id),
            "Status": e.status,
            "Admin": "yes" if e.is_admin else "",
        }
        for e in employees
    ])
    st.dataframe(frame, use_container_width=True, hide_index=True)

    st.markdown("#### Add or edit")
    options = ["+ New employee"] + [f"{e.emp_id} — {e.name}" for e in employees]
    choice = st.selectbox("Employee", options, key="perf_admin_emp_choice")
    is_new = choice == options[0]
    existing = None if is_new else ctx.chart.get(choice.split(" — ")[0])

    _employee_form(ctx, existing, employees)


def _employee_form(
    ctx: PerformanceContext, existing: Employee | None, employees: list[Employee]
) -> None:
    is_new = existing is None
    manager_options = [""] + [e.emp_id for e in employees if not existing
                              or e.emp_id != existing.emp_id]

    with st.form("perf_admin_employee_form"):
        col1, col2 = st.columns(2)
        with col1:
            emp_id = st.text_input(
                "Employee ID",
                value=existing.emp_id if existing else ctx.repo.next_employee_id(),
                disabled=not is_new,
                help="Immutable — scores and cards reference it.",
            )
            name = st.text_input("Name", value=existing.name if existing else "")
            email = st.text_input(
                "Microsoft email",
                value=existing.email if existing else "",
                help="Must match the account they sign in with, or they "
                     "cannot use the system.",
            )
            designation = st.text_input(
                "Designation", value=existing.designation if existing else ""
            )
        with col2:
            level = st.selectbox(
                "Level", LEVEL_OPTIONS,
                index=LEVEL_OPTIONS.index(existing.level)
                if existing and existing.level in LEVEL_OPTIONS else 4,
            )
            department = st.selectbox(
                "Department", DEPARTMENTS,
                index=DEPARTMENTS.index(existing.department)
                if existing and existing.department in DEPARTMENTS else 1,
            )
            reports_to = st.selectbox(
                "Reports to", manager_options,
                index=manager_options.index(existing.reports_to_emp_id)
                if existing and existing.reports_to_emp_id in manager_options else 0,
                format_func=lambda e: "— none (root) —" if not e
                else f"{e} — {_name_of(ctx.chart, e)}",
            )
            status = st.selectbox(
                "Status", ["active", "inactive"],
                index=0 if not existing or existing.is_active else 1,
            )

        col3, col4 = st.columns(2)
        with col3:
            doj = st.date_input(
                "Date of joining",
                value=existing.doj if existing and existing.doj else None,
                format="DD/MM/YYYY",
            )
            is_admin = st.checkbox(
                "System administrator",
                value=existing.is_admin if existing else False,
                help="Can edit the org tree, KPI library and cadence.",
            )
        with col4:
            effective_from = st.date_input(
                "Effective from",
                value=existing.effective_from if existing and existing.effective_from
                else None,
                format="DD/MM/YYYY",
                help="Leave blank unless recording a change from a specific "
                     "date. Set it when someone moves teams, so past months "
                     "keep the manager who actually scored them.",
            )
            override = st.selectbox(
                "Management override", ["", "grant", "revoke"],
                index=["", "grant", "revoke"].index(existing.management_override)
                if existing and existing.management_override in ("", "grant", "revoke")
                else 0,
                help="Normally blank. Management is the MD plus depth 1.",
            )

        submitted = st.form_submit_button(
            "Add employee" if is_new else "Save changes", type="primary"
        )

    if not submitted:
        return

    errors = _validate(ctx, emp_id, name, email, reports_to, is_new, employees)
    if errors:
        for error in errors:
            st.error(error)
        return

    employee = Employee(
        emp_id=emp_id.strip(),
        name=name.strip(),
        email=email.strip().lower(),
        designation=designation.strip(),
        level=level,
        department=department,
        reports_to_emp_id=reports_to,
        doj=doj,
        status=status,
        effective_from=effective_from,
        effective_to=existing.effective_to if existing else None,
        is_admin=is_admin,
        management_override=override,
    )
    _save(ctx, employee, existing)


def _validate(
    ctx: PerformanceContext,
    emp_id: str,
    name: str,
    email: str,
    reports_to: str,
    is_new: bool,
    employees: list[Employee],
) -> list[str]:
    errors: list[str] = []
    if not emp_id.strip():
        errors.append("Employee ID is required.")
    if not name.strip():
        errors.append("Name is required.")
    if is_new and any(e.emp_id == emp_id.strip() for e in employees):
        errors.append(f"Employee ID '{emp_id}' is already in use.")

    address = email.strip().lower()
    if address:
        clash = next(
            (e for e in employees if e.email == address and e.emp_id != emp_id.strip()),
            None,
        )
        if clash:
            errors.append(f"Email '{address}' already belongs to {clash.name}.")

    # Cycle check before writing — a cycle in the sheet breaks depth
    # resolution for every employee underneath it.
    problem = ctx.chart.validate_reassignment(emp_id.strip(), reports_to)
    if problem:
        errors.append(problem)
    return errors


def _save(ctx: PerformanceContext, employee: Employee, existing: Employee | None) -> None:
    try:
        ctx.repo.save_employee(employee)
    except PerformanceRepositoryError as exc:
        st.error(f"Could not save: {exc}")
        return

    ctx.repo.log([
        AuditEntry(
            audit_id=new_id("AUD"),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            actor=ctx.emp_id,
            entity="Employee",
            entity_id=employee.emp_id,
            action="update" if existing else "create",
            old_value=_summary(existing) if existing else "",
            new_value=_summary(employee),
        )
    ])

    clear_caches()
    st.success(f"Saved {employee.name}.")

    # Re-resolve so the admin sees the consequence of the change immediately,
    # rather than after a manual refresh.
    updated = [e for e in ctx.repo.get_employees()]
    fresh = OrgChart(updated, as_of=date.today())
    problems = fresh.validate_tree()
    if problems:
        st.warning("The hierarchy now has issues:")
        for problem in problems:
            st.markdown(f"- {problem}")
    st.rerun()


def _summary(employee: Employee) -> str:
    return (
        f"{employee.name} | {employee.level} | reports_to="
        f"{employee.reports_to_emp_id or '-'} | {employee.status}"
        f"{' | admin' if employee.is_admin else ''}"
    )


def _name_of(chart: OrgChart, emp_id: str) -> str:
    if not emp_id:
        return "—"
    employee = chart.get(emp_id)
    return employee.name if employee else f"{emp_id} (missing)"


# --------------------------------------------------------------------------
# KPI library
# --------------------------------------------------------------------------


def _render_library(ctx: PerformanceContext) -> None:
    entries = ctx.repo.get_kpi_library(active_only=False)
    if not entries:
        st.info("The KPI library is empty. Run the seed script to populate it.")
        return

    st.caption(
        f"{len(entries)} entries. Managers pick from these rather than "
        "free-typing, which is what keeps measurement methods and data "
        "sources consistent across months."
    )

    lower = [e for e in entries if e.direction == "lower"]
    if lower:
        with st.expander(f"{len(lower)} lower-is-better KPIs — why direction matters"):
            st.markdown(
                "The Performance Master computes `Actual / Target` for every "
                "KPI. For these, a **miss scores as an overachievement** — "
                "10% scrap against a 5% target hits the 120% cap instead of "
                "50%. The ERP inverts the ratio for these."
            )
            st.dataframe(
                pd.DataFrame([
                    {"KPI": e.name, "Unit": e.unit, "Applies to": e.applies_to}
                    for e in lower
                ]),
                use_container_width=True, hide_index=True,
            )

    roles = sorted({e.applies_to for e in entries if e.applies_to})
    chosen = st.selectbox("Filter by role", ["All"] + roles)
    shown = entries if chosen == "All" else [e for e in entries if e.applies_to == chosen]

    st.dataframe(
        pd.DataFrame([
            {
                "ID": e.kpi_id,
                "KPI": e.name,
                "Direction": e.direction,
                "Unit": e.unit,
                "Wt %": e.default_weight,
                "Type": e.outcome_type,
                "Layer": e.accountability_layer,
                "Data source": e.data_source,
                "Active": "yes" if e.active else "no",
            }
            for e in shown
        ]),
        use_container_width=True, hide_index=True,
    )
    st.caption("Library editing arrives with the card editor in the next phase.")


# --------------------------------------------------------------------------
# Cadence
# --------------------------------------------------------------------------


def _render_cadence(ctx: PerformanceContext) -> None:
    params = ctx.repo.get_parameters()
    st.caption(
        "Deadlines are day-of-month numbers, clamped to the real month "
        "length — a day-30 deadline lands on the 28th in February. Depth maps "
        "read `depth:day`."
    )

    cycle_keys = sorted(k for k in set(params) | set(DEFAULT_CYCLE_PARAMS)
                        if k.startswith("cycle."))
    st.dataframe(
        pd.DataFrame([
            {
                "Parameter": key,
                "Value": params.get(key, ""),
                "Default": DEFAULT_CYCLE_PARAMS.get(key, ""),
                "In use": params.get(key) or DEFAULT_CYCLE_PARAMS.get(key, ""),
            }
            for key in cycle_keys
        ]),
        use_container_width=True, hide_index=True,
    )

    with st.form("perf_admin_param_form"):
        st.markdown("**Change a parameter**")
        col1, col2 = st.columns([2, 1])
        with col1:
            key = st.selectbox("Parameter", sorted(set(params) | set(DEFAULT_CYCLE_PARAMS)))
        with col2:
            value = st.text_input("Value", value=params.get(key, ""))
        if st.form_submit_button("Save", type="primary"):
            try:
                ctx.repo.save_parameter(key, value.strip())
            except PerformanceRepositoryError as exc:
                st.error(f"Could not save: {exc}")
                return
            ctx.repo.log([
                AuditEntry(
                    audit_id=new_id("AUD"),
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                    actor=ctx.emp_id, entity="Parameter", entity_id=key,
                    action="update", field=key,
                    old_value=params.get(key, ""), new_value=value.strip(),
                )
            ])
            st.success(f"Saved {key}.")
            st.rerun()
