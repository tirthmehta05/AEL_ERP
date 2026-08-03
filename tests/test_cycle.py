"""Org hierarchy and cycle-task generation.

Fixtures use the real Amba tree from Foundation Doc 02, because the two rules
that matter most are only interesting on the real shape: Vijay is a
Sr. Associate reporting to another Sr. Associate (so deadlines must key off
depth, not level), and management is the MD plus depth 1 (so it must not be a
hand-maintained flag).
"""

from __future__ import annotations

from datetime import date

import pytest

# conftest.py has already prepended PROJECT_ROOT and mocked streamlit.
from src.performance.models.performance_models import Employee, CycleStage, TaskStatus
from src.performance.service.cycle_service import (
    compliance_summary,
    days_late,
    fiscal_quarter,
    generate_in_month_tasks,
    generate_planning_tasks,
    generate_quarterly_tasks,
    generate_scoring_tasks,
    generate_tasks_for_period,
    mark_completed,
    period_date,
    periods_in_quarter,
    shift_period,
)
from src.performance.service.org_service import OrgChart, as_of_for_period

# Name, level, manager — Foundation Doc 02, April 2026.
REAL_TREE = [
    ("E01", "Ketan Mehta", "MD", ""),
    ("E02", "Sarika Bhise", "Director", "E01"),
    ("E03", "Tirth Mehta", "VP", "E01"),
    ("E04", "Dhara Bhavsar", "VP", "E02"),
    ("E05", "Sneha Kadam", "Sr. Associate", "E02"),
    ("E06", "Pranay Shinde", "Sr. Associate", "E02"),
    ("E07", "Vijay", "Sr. Associate", "E05"),
    ("E08", "Pravin Mhade", "Associate", "E05"),
    ("E09", "Jagruti Sutar", "Associate", "E05"),
    ("E10", "Riya Telawade", "Associate", "E06"),
    ("E11", "Aditi Patel", "Associate", "E04"),
    ("E12", "Akshay Sawant", "Associate", "E04"),
]


def _employees(rows=None) -> list[Employee]:
    return [
        Employee(
            emp_id=emp_id,
            name=name,
            email=f"{name.split()[0].lower()}@amba.com",
            level=level,
            reports_to_emp_id=manager,
            status="active",
        )
        for emp_id, name, level, manager in (rows or REAL_TREE)
    ]


@pytest.fixture
def chart() -> OrgChart:
    return OrgChart(_employees(), as_of=date(2026, 4, 30))


# --------------------------------------------------------------------------
# Depth
# --------------------------------------------------------------------------


def test_depths_match_the_real_tree(chart):
    assert chart.depth("E01") == 0
    assert chart.depth("E02") == 1 and chart.depth("E03") == 1
    assert all(chart.depth(e) == 2 for e in ("E04", "E05", "E06"))
    assert all(chart.depth(e) == 3 for e in ("E07", "E08", "E09", "E10", "E11", "E12"))


def test_vijay_is_depth_three_despite_being_a_senior_associate(chart):
    """The case that forces depth-keyed rather than level-keyed deadlines.

    Vijay and Sneha share the Sr. Associate level, but Vijay reports to
    Sneha. Keyed on level they would share a deadline, so Vijay's card would
    be due the same day his manager's own card is set.
    """
    assert chart.get("E07").level == chart.get("E05").level == "Sr. Associate"
    assert chart.depth("E07") == 3
    assert chart.depth("E05") == 2


def test_max_depth_and_root(chart):
    assert chart.max_depth() == 3
    assert chart.root().emp_id == "E01"


# --------------------------------------------------------------------------
# Management
# --------------------------------------------------------------------------


def test_management_is_md_plus_depth_one(chart):
    assert {e.emp_id for e in chart.management()} == {"E01", "E02", "E03"}
    assert all(chart.is_management(e) for e in ("E01", "E02", "E03"))
    assert not any(chart.is_management(e) for e in ("E04", "E05", "E06", "E11"))


def test_new_md_direct_report_joins_management_with_no_flag_set():
    """The reason management is derived rather than stored."""
    rows = REAL_TREE + [("E13", "New Head", "VP", "E01")]
    chart = OrgChart(_employees(rows), as_of=date(2026, 4, 30))
    assert chart.is_management("E13")
    assert chart.get("E13").management_override == ""


def test_management_override_grants_and_revokes():
    people = _employees()
    by_id = {e.emp_id: e for e in people}
    by_id["E02"].management_override = "revoke"
    by_id["E11"].management_override = "grant"
    chart = OrgChart(people, as_of=date(2026, 4, 30))
    assert not chart.is_management("E02")
    assert chart.is_management("E11")


# --------------------------------------------------------------------------
# Permissions
# --------------------------------------------------------------------------


def test_only_the_direct_manager_can_score(chart):
    assert chart.can_score("E05", "E07")        # Sneha scores Vijay
    assert not chart.can_score("E02", "E07")    # Sarika is two levels up
    assert not chart.can_score("E07", "E07")    # nobody scores themselves


def test_ancestors_can_view_but_not_score(chart):
    assert chart.can_view("E02", "E07")
    assert not chart.can_score("E02", "E07")
    assert chart.can_view("E07", "E07")
    assert not chart.can_view("E11", "E07")     # unrelated branch


def test_amendment_approver_is_exactly_one_level_up(chart):
    assert chart.amendment_approver("E05").emp_id == "E02"
    assert chart.amendment_approver("E02").emp_id == "E01"
    # Nobody sits above the MD, so an MD-set card has no approver — the UI
    # surfaces this rather than allowing a silent self-approval.
    assert chart.amendment_approver("E01") is None


def test_email_lookup_is_case_insensitive(chart):
    assert chart.by_email("SNEHA@Amba.com  ").emp_id == "E05"
    assert chart.by_email("nobody@amba.com") is None


# --------------------------------------------------------------------------
# Tree validation
# --------------------------------------------------------------------------


def test_reassignment_rejects_cycles(chart):
    # Making Sneha report to her own subordinate would orphan the branch.
    assert chart.validate_reassignment("E05", "E07") is not None
    assert chart.validate_reassignment("E05", "E05") is not None
    assert chart.validate_reassignment("E05", "E99") is not None
    assert chart.validate_reassignment("E05", "E06") is None


def test_cycle_in_stored_data_yields_negative_depth_not_a_crash():
    rows = [("E01", "A", "MD", "E02"), ("E02", "B", "Director", "E01")]
    chart = OrgChart(_employees(rows), as_of=date(2026, 4, 30))
    assert chart.depth("E01") == -1
    assert any("cycle" in problem.lower() for problem in chart.validate_tree())


def test_validate_tree_flags_missing_email_and_duplicates():
    people = _employees()
    people[3].email = ""
    people[4].email = people[5].email
    problems = OrgChart(people, as_of=date(2026, 4, 30)).validate_tree()
    assert any("no email" in p for p in problems)
    assert any("shared by" in p for p in problems)


# --------------------------------------------------------------------------
# Effective dating
# --------------------------------------------------------------------------


def test_reports_to_resolves_as_of_the_period_being_acted_on():
    """A reorg must not rewrite who scored whom last quarter."""
    people = _employees()
    moved_before = Employee(
        emp_id="E10", name="Riya Telawade", email="riya@amba.com",
        level="Associate", reports_to_emp_id="E06", status="active",
        effective_from=date(2026, 1, 1), effective_to=date(2026, 6, 30),
    )
    moved_after = Employee(
        emp_id="E10", name="Riya Telawade", email="riya@amba.com",
        level="Associate", reports_to_emp_id="E04", status="active",
        effective_from=date(2026, 7, 1),
    )
    people = [e for e in people if e.emp_id != "E10"] + [moved_before, moved_after]

    june = OrgChart(people, as_of=as_of_for_period("2026-06"))
    july = OrgChart(people, as_of=as_of_for_period("2026-07"))
    assert june.get("E10").reports_to_emp_id == "E06"
    assert july.get("E10").reports_to_emp_id == "E04"
    assert june.can_score("E06", "E10")
    assert july.can_score("E04", "E10")


# --------------------------------------------------------------------------
# Period arithmetic
# --------------------------------------------------------------------------


def test_shift_period_crosses_year_boundaries():
    assert shift_period("2026-12", 1) == "2027-01"
    assert shift_period("2027-01", -1) == "2026-12"
    assert shift_period("2026-04", 12) == "2027-04"


@pytest.mark.parametrize(
    "period,day,expected",
    [
        ("2027-02", 30, date(2027, 2, 28)),   # clamps to a short month
        ("2028-02", 30, date(2028, 2, 29)),   # leap year
        ("2026-04", 31, date(2026, 4, 30)),   # 30-day month
        ("2026-05", 20, date(2026, 5, 20)),   # ordinary case
    ],
)
def test_period_date_clamps_to_month_length(period, day, expected):
    assert period_date(period, day) == expected


def test_fiscal_quarter_uses_april_start():
    assert fiscal_quarter("2026-04") == "FY26-27 Q1"
    assert fiscal_quarter("2026-09") == "FY26-27 Q2"
    assert fiscal_quarter("2026-12") == "FY26-27 Q3"
    assert fiscal_quarter("2027-03") == "FY26-27 Q4"
    assert periods_in_quarter("FY26-27 Q1") == ["2026-04", "2026-05", "2026-06"]
    assert periods_in_quarter("FY26-27 Q4") == ["2027-01", "2027-02", "2027-03"]


# --------------------------------------------------------------------------
# Task generation
# --------------------------------------------------------------------------


def _by_stage(tasks, stage: CycleStage):
    return [t for t in tasks if t.stage == stage.value]


def test_planning_tasks_fall_in_the_previous_month(chart):
    tasks = generate_planning_tasks("2026-05", chart)
    assert tasks, "expected planning tasks"
    assert all(t.due_date.month == 4 for t in tasks)


def test_set_card_deadlines_cascade_down_by_depth(chart):
    setters = {
        t.subject_emp_id: t.due_date.day
        for t in _by_stage(generate_planning_tasks("2026-05", chart), CycleStage.SET_CARDS)
    }
    # depth 1 by the 20th, depth 2 by the 23rd, depth 3 by the 25th
    assert setters["E02"] == 20 and setters["E03"] == 20
    assert setters["E05"] == 23 and setters["E04"] == 23
    assert setters["E07"] == 25 and setters["E11"] == 25
    # A manager's own card is always set before they must set their team's.
    assert setters["E05"] < setters["E07"]


def test_set_card_task_is_owned_by_the_manager_not_the_subject(chart):
    tasks = _by_stage(generate_planning_tasks("2026-05", chart), CycleStage.SET_CARDS)
    vijay = next(t for t in tasks if t.subject_emp_id == "E07")
    assert vijay.owner_emp_id == "E05"


def test_scoring_tasks_fall_in_the_following_month(chart):
    tasks = generate_scoring_tasks("2026-05", chart)
    assert tasks
    assert all(t.due_date.month == 6 for t in tasks)


def test_manager_scoring_cascades_up_by_depth(chart):
    scoring = {
        t.subject_emp_id: t.due_date.day
        for t in _by_stage(generate_scoring_tasks("2026-05", chart), CycleStage.MANAGER_SCORE)
    }
    # Deepest scored first, so a manager's "Direct Reports' Avg Score" KPI
    # can be computed before they are scored themselves.
    assert scoring["E07"] == 3    # depth 3
    assert scoring["E05"] == 4    # depth 2
    assert scoring["E02"] == 5    # depth 1
    assert scoring["E07"] < scoring["E05"] < scoring["E02"]


def test_root_is_neither_self_scored_nor_asked_to_acknowledge(chart):
    planning = generate_planning_tasks("2026-05", chart)
    scoring = generate_scoring_tasks("2026-05", chart)
    assert all(t.subject_emp_id != "E01" for t in _by_stage(scoring, CycleStage.SELF_SCORE))
    assert all(t.subject_emp_id != "E01" for t in _by_stage(planning, CycleStage.ACKNOWLEDGE))
    # ...but the MD still owns the top-of-cycle duties.
    assert _by_stage(planning, CycleStage.PUBLISH_NEEDS)[0].owner_emp_id == "E01"
    assert _by_stage(scoring, CycleStage.LOCK)[0].owner_emp_id == "E01"


def test_every_scored_employee_gets_a_card_and_a_self_score(chart):
    scored = {e.emp_id for e in chart.all_employees()} - {"E01"}
    planning = generate_planning_tasks("2026-05", chart)
    scoring = generate_scoring_tasks("2026-05", chart)
    assert {t.subject_emp_id for t in _by_stage(planning, CycleStage.SET_CARDS)} == scored
    assert {t.subject_emp_id for t in _by_stage(scoring, CycleStage.SELF_SCORE)} == scored


def test_check_ins_fall_inside_the_live_month(chart):
    tasks = generate_in_month_tasks("2026-05", chart)
    assert len(tasks) == 11
    assert all(t.due_date == date(2026, 5, 16) for t in tasks)


def test_february_scoring_deadlines_clamp(chart):
    """Scoring 2027-01 happens in February, exercising the short month."""
    tasks = generate_scoring_tasks("2027-01", chart)
    assert all(t.due_date.month == 2 and t.due_date.day <= 28 for t in tasks)


def test_quarterly_tasks_land_in_the_month_after_quarter_end(chart):
    tasks = generate_quarterly_tasks("FY26-27 Q1", chart)
    reviews = _by_stage(tasks, CycleStage.QUARTERLY_REVIEW)
    assert all(t.due_date == date(2026, 7, 15) for t in reviews)
    assert len(reviews) == 11
    validate = _by_stage(tasks, CycleStage.QUARTER_VALIDATE)[0]
    assert validate.due_date == date(2026, 7, 18)
    assert validate.owner_emp_id == "E01"


def test_full_period_covers_three_calendar_months(chart):
    months = {t.due_date.month for t in generate_tasks_for_period("2026-05", chart)}
    assert months == {4, 5, 6}


def test_task_ids_are_unique(chart):
    tasks = generate_tasks_for_period("2026-05", chart)
    assert len({t.task_id for t in tasks}) == len(tasks)


def test_custom_deadline_parameters_override_defaults(chart):
    params = {"cycle.set_cards_days": "1:10,2:12,3:14", "cycle.acknowledge_day": "15"}
    tasks = generate_planning_tasks("2026-05", chart, params)
    setters = {t.subject_emp_id: t.due_date.day for t in _by_stage(tasks, CycleStage.SET_CARDS)}
    assert setters["E02"] == 10 and setters["E05"] == 12 and setters["E07"] == 14
    assert _by_stage(tasks, CycleStage.ACKNOWLEDGE)[0].due_date.day == 15


def test_unconfigured_depth_inherits_the_deepest_deadline():
    """A newly added org layer must not silently lose its deadline."""
    rows = REAL_TREE + [("E13", "Deep Report", "Associate", "E07")]
    chart = OrgChart(_employees(rows), as_of=date(2026, 4, 30))
    params = {"cycle.set_cards_days": "1:20,2:23,3:25"}
    tasks = _by_stage(generate_planning_tasks("2026-05", chart, params), CycleStage.SET_CARDS)
    assert chart.depth("E13") == 4
    assert next(t for t in tasks if t.subject_emp_id == "E13").due_date.day == 25


# --------------------------------------------------------------------------
# Status and compliance
# --------------------------------------------------------------------------


def test_days_late_counts_only_past_due(chart):
    task = _by_stage(generate_planning_tasks("2026-05", chart), CycleStage.SET_CARDS)[0]
    assert days_late(task, date(2026, 4, 1)) == 0
    assert days_late(task, task.due_date) == 0
    assert days_late(task, date(2026, 4, 30)) == 30 - task.due_date.day


def test_mark_completed_freezes_lateness(chart):
    task = _by_stage(generate_planning_tasks("2026-05", chart), CycleStage.SET_CARDS)[0]
    done = mark_completed(task, actor="E05", completed_on=date(2026, 4, 24))
    assert done.status == TaskStatus.COMPLETED.value
    assert done.days_late == max(0, 24 - task.due_date.day)
    # Later reads must not inflate a settled record.
    assert days_late(done, date(2026, 12, 31)) == done.days_late


def test_compliance_summary_reports_on_time_rate(chart):
    tasks = _by_stage(generate_planning_tasks("2026-05", chart), CycleStage.SET_CARDS)[:4]
    done = [
        mark_completed(tasks[0], "x", date(2026, 4, 19)),
        mark_completed(tasks[1], "x", date(2026, 4, 19)),
        mark_completed(tasks[2], "x", date(2026, 4, 27)),
        tasks[3],
    ]
    summary = compliance_summary(done, today=date(2026, 4, 30))
    assert summary["total"] == 4
    assert summary["completed"] == 3
    assert summary["on_time"] == 2
    assert summary["on_time_pct"] == pytest.approx(66.7, abs=0.1)
    assert summary["overdue"] == 1
    assert summary["avg_delay_days"] > 0
