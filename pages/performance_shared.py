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
    clear_all_caches,
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


def load_chart(repo: PerformanceRepository, period: str) -> OrgChart:
    """Resolve the org as of a period.

    Reads go through the repository's own TTL cache, which is shared across
    reruns — Streamlit rebuilds this page (and the repository) on every widget
    interaction, so caching has to live below the Streamlit layer to help at
    all.
    """
    return OrgChart(repo.get_employees(), as_of=as_of_for_period(period))


def clear_caches() -> None:
    """Drop cached reads after a write."""
    clear_all_caches()


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

    Rendered at the top of the page rather than in the sidebar: the sidebar
    already ends with a copyright footer, so anything appended below it reads
    as chrome and gets scrolled past.
    """
    people = chart.all_employees()
    if not people:
        return matched, False

    options = [e.emp_id for e in people]
    labels = {
        e.emp_id: f"{e.name} — {e.designation or e.level} (depth "
                  f"{chart.depth(e.emp_id)})"
        + ("  ·  admin" if chart.is_admin(e.emp_id) else "")
        + ("  ·  management" if chart.is_management(e.emp_id) else "")
        for e in people
    }

    # Default to an admin so the Admin tab is reachable on first open. Landing
    # as someone who cannot use half the page makes the tool look broken.
    default = matched.emp_id if matched else _preferred_dev_identity(chart, options)
    stored = st.session_state.get(IMPERSONATE_KEY, default)
    index = options.index(stored) if stored in options else options.index(default)

    with st.container(border=True):
        left, right = st.columns([3, 2])
        with left:
            chosen = st.selectbox(
                "Acting as (dev mode)",
                options,
                index=index,
                format_func=lambda emp_id: labels.get(emp_id, emp_id),
                key=IMPERSONATE_KEY,
                help="Dev mode only. Switch identity to exercise the cascade "
                     "without twelve Microsoft accounts.",
            )
        with right:
            st.caption(
                "Permissions follow the reporting tree, so what you can see "
                "and do changes with this. Admin needs an admin; Business "
                "Needs needs management."
            )
    return chart.get(chosen), True


def _preferred_dev_identity(chart: OrgChart, options: list[str]) -> str:
    """Pick the most useful starting identity: an admin, else the root."""
    for emp_id in options:
        if chart.is_admin(emp_id):
            return emp_id
    root = chart.root()
    return root.emp_id if root else options[0]


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
