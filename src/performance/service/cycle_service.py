"""The monthly clock: who owes what, by when.

A period's tasks span three calendar months, which is the whole point of the
overlapping cadence:

* **planning** for period P happens during month P-1, cascading DOWN the tree
  so targets flow from published business needs;
* **check-ins** happen inside month P itself, while the card is live;
* **scoring** of period P happens during month P+1, cascading UP the tree,
  because a manager's own "Direct Reports' Avg Score" KPI cannot be computed
  until their team is locked.

Deadlines key off depth rather than level, and every day-number lives in the
`Parameters` tab so the cadence can be retuned without a deploy. Day numbers
are clamped to month length, so a "day 30" deadline lands on the 28th in
February instead of throwing.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from src.performance.models.performance_models import (
    CycleStage,
    CycleTask,
    Employee,
    TaskStatus,
    new_id,
)
from src.performance.service.org_service import OrgChart
from src.shared.utils.logger_config import setup_logger

logger = setup_logger(__name__)


# Defaults matching the agreed cadence. Seeded into `Parameters`, where they
# can be edited; these values are the fallback if a key is missing.
DEFAULT_CYCLE_PARAMS: dict[str, str] = {
    # -- planning period P, executed during month P-1 (cascades down)
    "cycle.publish_needs_day": "18",
    "cycle.set_cards_days": "1:20,2:23,3:25,4:27",
    "cycle.acknowledge_day": "28",
    "cycle.exception_review_day": "29",
    # -- live month P
    "cycle.check_in_day": "16",
    "cycle.amendment_close_day": "10",
    # -- scoring period P, executed during month P+1 (cascades up)
    "cycle.self_score_day": "2",
    "cycle.manager_score_days": "1:5,2:4,3:3,4:3",
    "cycle.calibrate_day": "6",
    "cycle.lock_day": "7",
    # -- quarterly, in the month after quarter end
    "cycle.quarterly_review_day": "15",
    "cycle.quarter_validate_day": "18",
}


# --------------------------------------------------------------------------
# Period arithmetic
# --------------------------------------------------------------------------


def shift_period(period: str, months: int) -> str:
    """Move a YYYY-MM period by a number of months."""
    year, month = (int(part) for part in period.split("-")[:2])
    index = (year * 12 + (month - 1)) + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def period_date(period: str, day: int) -> date:
    """A day within a period, clamped to the month's real length.

    Without clamping, a day-30 deadline raises in February and a day-31
    deadline raises in four months of the year.
    """
    year, month = (int(part) for part in period.split("-")[:2])
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, max(1, min(day, last_day)))


def period_of(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def fiscal_quarter(period: str) -> str:
    """Indian FY label for a period. April starts the year.

    2026-04 -> "FY26-27 Q1";  2027-01 -> "FY26-27 Q4".
    """
    year, month = (int(part) for part in period.split("-")[:2])
    fy_start = year if month >= 4 else year - 1
    quarter = ((month - 4) % 12) // 3 + 1
    return f"FY{fy_start % 100:02d}-{(fy_start + 1) % 100:02d} Q{quarter}"


def periods_in_quarter(quarter: str) -> list[str]:
    """The three YYYY-MM periods making up a fiscal quarter label."""
    fy_part, q_part = quarter.rsplit(" ", 1)
    fy_start = 2000 + int(fy_part.replace("FY", "").split("-")[0])
    index = int(q_part.replace("Q", "")) - 1
    start_month = 4 + index * 3
    out: list[str] = []
    for offset in range(3):
        month = start_month + offset
        year = fy_start + (month - 1) // 12
        out.append(f"{year:04d}-{(month - 1) % 12 + 1:02d}")
    return out


# --------------------------------------------------------------------------
# Parameter access
# --------------------------------------------------------------------------


def _day(params: dict[str, str], key: str) -> int:
    raw = params.get(key) or DEFAULT_CYCLE_PARAMS.get(key, "1")
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning("Parameter '%s' is not a number (%r); using 1", key, raw)
        return 1


def _depth_days(params: dict[str, str], key: str) -> dict[int, int]:
    """Parse a "1:20,2:23,3:25" depth-to-day map."""
    raw = params.get(key) or DEFAULT_CYCLE_PARAMS.get(key, "")
    out: dict[int, int] = {}
    for chunk in str(raw).split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        depth_text, day_text = chunk.split(":", 1)
        try:
            out[int(depth_text.strip())] = int(day_text.strip())
        except ValueError:
            logger.warning("Skipping malformed entry %r in '%s'", chunk, key)
    return out


def _day_for_depth(depth_map: dict[int, int], depth: int, fallback: int) -> int:
    """Look up a depth, falling back to the deepest configured level.

    A new layer added to the org should not silently lose its deadline; it
    inherits the deepest one until Parameters is updated.
    """
    if depth in depth_map:
        return depth_map[depth]
    if not depth_map:
        return fallback
    deepest = max(depth_map)
    return depth_map[deepest] if depth > deepest else depth_map[min(depth_map)]


# --------------------------------------------------------------------------
# Task generation
# --------------------------------------------------------------------------


def _task(
    period: str,
    stage: CycleStage,
    owner: str,
    due: date,
    subject: str = "",
) -> CycleTask:
    return CycleTask(
        task_id=new_id("TSK"),
        period=period,
        stage=stage.value,
        owner_emp_id=owner,
        subject_emp_id=subject,
        due_date=due,
        status=TaskStatus.OPEN.value,
    )


def _scored_employees(chart: OrgChart) -> list[Employee]:
    """Everyone who receives a card and a score.

    The root is excluded: per the Scaling Plan, the MD is not scored in the
    Performance Master — they review everyone else.
    """
    root = chart.root()
    root_id = root.emp_id if root else ""
    return [
        emp for emp in chart.all_employees()
        if emp.emp_id != root_id and emp.reports_to_emp_id
    ]


def generate_planning_tasks(
    period: str, chart: OrgChart, params: Optional[dict[str, str]] = None
) -> list[CycleTask]:
    """Tasks for planning `period`, all due during the previous month."""
    params = params or {}
    prev = shift_period(period, -1)
    root = chart.root()
    tasks: list[CycleTask] = []

    if root is not None:
        tasks.append(_task(
            period, CycleStage.PUBLISH_NEEDS, root.emp_id,
            period_date(prev, _day(params, "cycle.publish_needs_day")),
        ))

    set_days = _depth_days(params, "cycle.set_cards_days")
    ack_day = _day(params, "cycle.acknowledge_day")

    for emp in _scored_employees(chart):
        depth = chart.depth(emp.emp_id)
        if depth < 0:
            logger.warning("Skipping '%s' — depth unresolvable", emp.emp_id)
            continue
        due_day = _day_for_depth(set_days, depth, ack_day - 1)
        tasks.append(_task(
            period, CycleStage.SET_CARDS, emp.reports_to_emp_id,
            period_date(prev, due_day), subject=emp.emp_id,
        ))
        tasks.append(_task(
            period, CycleStage.ACKNOWLEDGE, emp.emp_id,
            period_date(prev, ack_day), subject=emp.emp_id,
        ))

    if root is not None:
        tasks.append(_task(
            period, CycleStage.EXCEPTION_REVIEW, root.emp_id,
            period_date(prev, _day(params, "cycle.exception_review_day")),
        ))
    return tasks


def generate_in_month_tasks(
    period: str, chart: OrgChart, params: Optional[dict[str, str]] = None
) -> list[CycleTask]:
    """Tasks falling inside the live month — the mid-month check-in."""
    params = params or {}
    due = period_date(period, _day(params, "cycle.check_in_day"))
    return [
        _task(period, CycleStage.CHECK_IN, emp.reports_to_emp_id, due, subject=emp.emp_id)
        for emp in _scored_employees(chart)
        if chart.depth(emp.emp_id) >= 0
    ]


def generate_scoring_tasks(
    period: str, chart: OrgChart, params: Optional[dict[str, str]] = None
) -> list[CycleTask]:
    """Tasks for scoring `period`, all due during the following month."""
    params = params or {}
    nxt = shift_period(period, 1)
    root = chart.root()
    tasks: list[CycleTask] = []

    self_day = _day(params, "cycle.self_score_day")
    score_days = _depth_days(params, "cycle.manager_score_days")

    for emp in _scored_employees(chart):
        depth = chart.depth(emp.emp_id)
        if depth < 0:
            continue
        tasks.append(_task(
            period, CycleStage.SELF_SCORE, emp.emp_id,
            period_date(nxt, self_day), subject=emp.emp_id,
        ))
        tasks.append(_task(
            period, CycleStage.MANAGER_SCORE, emp.reports_to_emp_id,
            period_date(nxt, _day_for_depth(score_days, depth, self_day + 1)),
            subject=emp.emp_id,
        ))

    if root is not None:
        tasks.append(_task(
            period, CycleStage.CALIBRATE, root.emp_id,
            period_date(nxt, _day(params, "cycle.calibrate_day")),
        ))
        tasks.append(_task(
            period, CycleStage.LOCK, root.emp_id,
            period_date(nxt, _day(params, "cycle.lock_day")),
        ))
    return tasks


def generate_quarterly_tasks(
    quarter: str, chart: OrgChart, params: Optional[dict[str, str]] = None
) -> list[CycleTask]:
    """Quarterly 1:1s and validation, due in the month after quarter end."""
    params = params or {}
    after = shift_period(periods_in_quarter(quarter)[-1], 1)
    root = chart.root()

    review_due = period_date(after, _day(params, "cycle.quarterly_review_day"))
    tasks = [
        _task(quarter, CycleStage.QUARTERLY_REVIEW, emp.reports_to_emp_id,
              review_due, subject=emp.emp_id)
        for emp in _scored_employees(chart)
        if chart.depth(emp.emp_id) >= 0
    ]
    if root is not None:
        tasks.append(_task(
            quarter, CycleStage.QUARTER_VALIDATE, root.emp_id,
            period_date(after, _day(params, "cycle.quarter_validate_day")),
        ))
    return tasks


def generate_tasks_for_period(
    period: str, chart: OrgChart, params: Optional[dict[str, str]] = None
) -> list[CycleTask]:
    """Every task in a period's full lifecycle, across all three months."""
    return (
        generate_planning_tasks(period, chart, params)
        + generate_in_month_tasks(period, chart, params)
        + generate_scoring_tasks(period, chart, params)
    )


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------


def days_late(task: CycleTask, today: Optional[date] = None) -> int:
    """How overdue a task is. Zero when on time, complete, or not yet due."""
    if task.due_date is None:
        return 0
    if task.status == TaskStatus.COMPLETED.value:
        return max(0, task.days_late)
    reference = today or date.today()
    return max(0, (reference - task.due_date).days)


def mark_completed(
    task: CycleTask, actor: str, completed_on: Optional[date] = None
) -> CycleTask:
    """Close a task, freezing how late it was at the moment of completion."""
    when = completed_on or date.today()
    late = 0 if task.due_date is None else max(0, (when - task.due_date).days)
    return task.model_copy(update={
        "status": TaskStatus.COMPLETED.value,
        "completed_at": when.isoformat(),
        "days_late": late,
    })


def compliance_summary(tasks: list[CycleTask], today: Optional[date] = None) -> dict:
    """On-time performance, for the Compliance board and the Discipline pillar."""
    reference = today or date.today()
    total = len(tasks)
    completed = [t for t in tasks if t.status == TaskStatus.COMPLETED.value]
    on_time = [t for t in completed if t.days_late == 0]
    overdue = [t for t in tasks if t.is_open and days_late(t, reference) > 0]
    late_days = [t.days_late for t in completed if t.days_late > 0]
    return {
        "total": total,
        "completed": len(completed),
        "open": total - len(completed),
        "overdue": len(overdue),
        "on_time": len(on_time),
        "on_time_pct": round(len(on_time) / len(completed) * 100, 1) if completed else 0.0,
        "avg_delay_days": round(sum(late_days) / len(late_days), 1) if late_days else 0.0,
    }
