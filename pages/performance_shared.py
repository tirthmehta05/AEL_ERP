"""Streamlit glue for the Performance page.

`src/performance/` stays free of Streamlit imports, matching the convention
stated in `src/services.py`. Everything session- or widget-shaped lives here:
resolving the signed-in user to an employee, caching the org chart, and the
small render helpers the tabs share.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import streamlit as st

from config import settings
from src.performance.models.performance_models import Employee
from src.performance.repository.performance_repository import (
    PerformanceRepository,
    PerformanceRepositoryError,
)
from src.performance.service.cycle_service import period_of
from src.performance.service.org_service import OrgChart, as_of_for_period
from src.shared.utils.logger_config import setup_logger

logger = setup_logger(__name__)

IMPERSONATE_KEY = "perf_impersonate_emp_id"


@dataclass
class PerformanceContext:
    """Everything a tab needs to decide what to show and what to allow."""

    repo: PerformanceRepository
    chart: OrgChart
    employee: Optional[Employee]
    period: str
    signed_in_email: str
    impersonating: bool = False

    @property
    def emp_id(self) -> str:
        return self.employee.emp_id if self.employee else ""

    @property
    def is_management(self) -> bool:
        return bool(self.employee) and self.chart.is_management(self.emp_id)

    @property
    def is_admin(self) -> bool:
        return bool(self.employee) and self.chart.is_admin(self.emp_id)

    @property
    def direct_reports(self) -> list[Employee]:
        return self.chart.direct_reports(self.emp_id) if self.employee else []

    def can_view(self, subject_id: str) -> bool:
        return bool(self.employee) and self.chart.can_view(self.emp_id, subject_id)

    def can_score(self, subject_id: str) -> bool:
        return bool(self.employee) and self.chart.can_score(self.emp_id, subject_id)


# --------------------------------------------------------------------------
# Data access
# --------------------------------------------------------------------------


@st.cache_data(ttl=300, show_spinner=False)
def _load_employee_rows(_repo: PerformanceRepository) -> list[dict]:
    """Employee rows, cached as plain dicts.

    Cached as dicts rather than models because Streamlit's cache pickles the
    return value, and re-validating on read is cheap next to a Sheets round
    trip. The leading underscore keeps the repo out of the cache key.
    """
    return [emp.model_dump(mode="json") for emp in _repo.get_employees()]


def load_chart(repo: PerformanceRepository, period: str) -> OrgChart:
    rows = _load_employee_rows(repo)
    employees = [Employee(**row) for row in rows]
    return OrgChart(employees, as_of=as_of_for_period(period))


def clear_caches() -> None:
    """Drop cached reads after a write."""
    _load_employee_rows.clear()


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------


def signed_in_email() -> str:
    """The MSAL UPN of the signed-in user.

    Matches the pattern already used in pages/weight_receipt.py — MSAL puts
    the address in `username`, not `email`.
    """
    return str(
        st.session_state.get("user_info", {}).get("username", "") or ""
    ).strip().lower()


def get_context(period: Optional[str] = None) -> Optional[PerformanceContext]:
    """Build the page context, or render an explanation and return None.

    Returning None rather than raising lets each tab bail out cleanly on a
    misconfigured sheet without a traceback in the UI.
    """
    repo = PerformanceRepository()
    period = period or period_of(date.today())

    ok, message = repo.health_check()
    if not ok:
        st.error(f"Performance system unavailable: {message}")
        st.caption(
            "An admin can run `python scripts/seed_performance_sheet.py "
            "--admin-email <you>` to create the spreadsheet, then set "
            "`[performance].performance_sheets_id` in secrets."
        )
        return None

    try:
        chart = load_chart(repo, period)
    except PerformanceRepositoryError as exc:
        st.error(str(exc))
        return None

    email = signed_in_email()
    employee = chart.by_email(email)
    impersonating = False

    # Dev mode mocks the user entirely (main.py), so there is no real address
    # to match. Allow picking an identity rather than locking the page.
    if settings.app.dev_mode:
        employee, impersonating = _dev_mode_identity(chart, employee)

    if employee is None:
        st.warning(
            f"No employee record is linked to **{email or 'your account'}**."
        )
        st.caption(
            "An admin can add your Microsoft email under Performance > Admin. "
            "Until then the performance system cannot tell who you are."
        )
        return None

    return PerformanceContext(
        repo=repo,
        chart=chart,
        employee=employee,
        period=period,
        signed_in_email=email,
        impersonating=impersonating,
    )


def _dev_mode_identity(
    chart: OrgChart, matched: Optional[Employee]
) -> tuple[Optional[Employee], bool]:
    """Identity picker, dev mode only.

    Lets the whole cascade be exercised locally without twelve Microsoft
    accounts. Never reachable in production — main.py only mocks the user when
    settings.app.dev_mode is set.
    """
    people = chart.all_employees()
    if not people:
        return matched, False

    with st.sidebar:
        st.markdown("---")
        st.caption("Dev mode — acting as")
        options = [e.emp_id for e in people]
        labels = {
            e.emp_id: f"{e.name} · {e.level} · depth {chart.depth(e.emp_id)}"
            for e in people
        }
        default = matched.emp_id if matched else options[0]
        stored = st.session_state.get(IMPERSONATE_KEY, default)
        index = options.index(stored) if stored in options else 0
        chosen = st.selectbox(
            "Acting as",
            options,
            index=index,
            format_func=lambda emp_id: labels.get(emp_id, emp_id),
            key=IMPERSONATE_KEY,
            label_visibility="collapsed",
        )
    return chart.get(chosen), True


# --------------------------------------------------------------------------
# Render helpers
# --------------------------------------------------------------------------


def render_identity_bar(ctx: PerformanceContext) -> None:
    """Who you are and what that lets you do — shown on every tab.

    Permissions here are derived from the tree, so stating them plainly saves
    a support conversation about why a button is missing.
    """
    roles = []
    if ctx.is_management:
        roles.append("Management")
    if ctx.is_admin:
        roles.append("Admin")
    if ctx.direct_reports:
        roles.append(f"{len(ctx.direct_reports)} direct report"
                     f"{'s' if len(ctx.direct_reports) != 1 else ''}")
    role_text = " · ".join(roles) if roles else "Individual contributor"

    left, right = st.columns([3, 1])
    with left:
        st.markdown(
            f"**{ctx.employee.name}** — {ctx.employee.designation or ctx.employee.level}"
        )
        st.caption(f"{role_text} · depth {ctx.chart.depth(ctx.emp_id)}")
    with right:
        if ctx.impersonating:
            st.caption("⚠️ dev impersonation")

    if ctx.employee and not ctx.employee.email:
        st.warning(
            "This employee record has no email, so they cannot sign in. "
            "Add it under Admin."
        )


def period_selector(label: str = "Month", key: str = "perf_period") -> str:
    """A YYYY-MM picker spanning the surrounding year."""
    today = date.today()
    months: list[str] = []
    for offset in range(-12, 4):
        index = (today.year * 12 + today.month - 1) + offset
        months.append(f"{index // 12:04d}-{index % 12 + 1:02d}")
    current = period_of(today)
    return st.selectbox(label, months, index=months.index(current), key=key)


def require(condition: bool, message: str) -> bool:
    """Show an explanation instead of an empty tab when access is denied."""
    if not condition:
        st.info(message)
    return condition
