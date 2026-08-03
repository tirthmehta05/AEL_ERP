"""Performance page — tab router.

Follows the pattern in pages/data_entry.py, including the `cache_to_clear`
handshake the sidebar Refresh button uses.

Tabs beyond Admin arrive in later phases; they are listed here from the start
so the shape of the cycle is visible to anyone opening the page, and each
states plainly what it will do rather than rendering an empty panel.
"""

from __future__ import annotations

import streamlit as st

from theme.components import render_main_header
from pages import performance_admin
from pages.performance_shared import (
    clear_caches,
    get_context,
    period_selector,
    render_identity_bar,
)

TAB_MY_WORK = "My Work"
TAB_SET_CARDS = "Set Cards"
TAB_SCORE = "Score"
TAB_REVIEWS = "Reviews"
TAB_BUSINESS_NEEDS = "Business Needs"
TAB_COMPLIANCE = "Compliance"
TAB_ADMIN = "Admin"

TABS = [
    TAB_MY_WORK, TAB_SET_CARDS, TAB_SCORE, TAB_REVIEWS,
    TAB_BUSINESS_NEEDS, TAB_COMPLIANCE, TAB_ADMIN,
]

# Phase each not-yet-built tab lands in, and what it will do. Shown in place
# of the tab body so the page explains itself during the rollout.
COMING = {
    TAB_MY_WORK: (
        "Phase 2-3",
        "Your live card, open deadlines, monthly scorecard and score trend.",
    ),
    TAB_SET_CARDS: (
        "Phase 2",
        "Set next month's card for each direct report — carried forward from "
        "last month with per-item keep, edit, delete and add across all four "
        "pillars, a live quality gate, and the AI prompt helper.",
    ),
    TAB_SCORE: (
        "Phase 3",
        "Self-score, manager score and calibration, each item with a "
        "mandatory written justification.",
    ),
    TAB_REVIEWS: (
        "Phase 5",
        "Mid-month check-ins and the quarterly 1:1 with a generated agenda "
        "and dual sign-off.",
    ),
    TAB_BUSINESS_NEEDS: (
        "Phase 2",
        "Publish the month's company targets and the company-wide Behaviour "
        "and Discipline baseline that cascades onto every card.",
    ),
    TAB_COMPLIANCE: (
        "Phase 4",
        "Who is on time and who is late, by person and by stage, plus when "
        "reminder emails last went out.",
    ),
}


def render() -> None:
    render_main_header("Performance")

    active_tab = _select_tab()

    ctx = get_context(period=st.session_state.get("perf_period"))
    if ctx is None:
        return

    render_identity_bar(ctx)
    st.markdown("---")

    if active_tab == TAB_ADMIN:
        performance_admin.render(ctx)
    else:
        _render_placeholder(active_tab)


def _select_tab() -> str:
    """Tab picker plus the sidebar Refresh handshake.

    navigation.py stashes {"page": ..., "tab": ...} in `cache_to_clear`; the
    page consumes it, drops its caches and restores the tab the user was on.
    """
    radio_index = 0
    try:
        radio_index = TABS.index(st.session_state.performance_active_tab)
    except (AttributeError, ValueError):
        pass

    cache_request = st.session_state.get("cache_to_clear")
    if cache_request:
        st.session_state.pop("cache_to_clear")
        requested = (
            cache_request.get("tab")
            if isinstance(cache_request, dict) else cache_request
        )
        clear_caches()
        st.toast("Performance data refreshed.")
        if requested in TABS:
            radio_index = TABS.index(requested)

    return st.radio(
        "Select view:",
        TABS,
        index=radio_index,
        horizontal=True,
        key="performance_active_tab",
        label_visibility="collapsed",
    )


def _render_placeholder(tab: str) -> None:
    phase, description = COMING.get(tab, ("", ""))
    st.subheader(tab)
    st.info(f"**Coming in {phase}.** {description}")

    if tab in (TAB_MY_WORK, TAB_SET_CARDS, TAB_SCORE):
        period_selector()

    with st.expander("How the monthly cycle works"):
        st.markdown(
            """
Planning and scoring overlap, so a card is always live from the 1st.

**Planning next month** — during this month, cascading *down* the tree:

| Day | Who | What |
|---|---|---|
| 18 | Management | Publish business needs |
| 20 | MD | Set cards for direct reports |
| 23 | Depth&nbsp;1 | Set cards for their reports |
| 25 | Depth&nbsp;2 | Set cards for their reports |
| 28 | Everyone | Acknowledge your card |
| 29 | Management | Exception review |

**Scoring last month** — during this month, cascading *up*, because a
manager's own "Direct Reports' Avg Score" needs their team locked first:

| Day | Who | What |
|---|---|---|
| 1-2 | Everyone | Self-score |
| 3 | Depth&nbsp;2 managers | Score their reports |
| 4 | Depth&nbsp;1 managers | Score their reports |
| 5 | MD | Score direct reports |
| 6 | Management | Calibration |
| 7 | System | Lock and publish |
| 10 | — | Amendment window closes |
| 16 | Manager + report | Mid-month check-in |

Deadlines key off depth in the reporting tree rather than job level, and
every day number is configurable under Admin > Cadence.
            """
        )
