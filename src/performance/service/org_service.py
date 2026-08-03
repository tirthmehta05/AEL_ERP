"""Reporting hierarchy: resolution, depth, and permissions.

Everything the performance system authorises is derived from the tree rather
than from a role list. That is deliberate — a hand-maintained "who is a
manager" list goes stale the first time someone changes teams, and a stale
permission list on salary-adjacent data is worse than an inconvenient one.

Two rules carry most of the weight:

* **Deadlines key off depth, not level.** Vijay is a Sr. Associate reporting
  to another Sr. Associate, so a level-keyed deadline would make his card due
  the same day his manager's is set.
* **Management is the MD plus everyone at depth 1.** A new VP reporting
  straight to the MD becomes management the day their reports_to is set, with
  nothing else to remember.

The chart is a snapshot resolved as of a date, because `Employees` rows are
effective-dated. Re-organising must never rewrite who actually scored whom
last quarter.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Iterable, Optional

from src.performance.models.performance_models import Employee
from src.shared.utils.logger_config import setup_logger

logger = setup_logger(__name__)

MANAGEMENT_MAX_DEPTH = 1
# Guards against a reports_to cycle produced by a bad edit. The real tree is
# 4 deep; anything past this is a data problem, not a deep org.
MAX_TREE_DEPTH = 20


class OrgError(Exception):
    """Raised when the hierarchy itself is invalid (cycle, missing manager)."""


def as_of_for_period(period: str) -> date:
    """The date at which to resolve the org for a given YYYY-MM period.

    Month end, not month start: the person who managed you on the last day of
    the month is the one who scores that month.
    """
    year, month = (int(part) for part in period.split("-")[:2])
    return date(year, month, calendar.monthrange(year, month)[1])


class OrgChart:
    """An immutable snapshot of the hierarchy as of one date."""

    def __init__(self, employees: Iterable[Employee], as_of: Optional[date] = None):
        self.as_of = as_of or date.today()
        self._by_id: dict[str, Employee] = self._resolve(employees, self.as_of)
        self._depth_cache: dict[str, int] = {}
        self._children: dict[str, list[str]] = {}
        for emp_id, emp in self._by_id.items():
            if emp.reports_to_emp_id:
                self._children.setdefault(emp.reports_to_emp_id, []).append(emp_id)

    # -- construction ------------------------------------------------------

    @staticmethod
    def _resolve(employees: Iterable[Employee], as_of: date) -> dict[str, Employee]:
        """Pick the row in effect on `as_of` for each employee.

        An employee may have several effective-dated rows. Blank bounds are
        open-ended. Where several rows match, the latest effective_from wins.
        """
        candidates: dict[str, list[Employee]] = {}
        for emp in employees:
            if not emp.emp_id:
                continue
            starts = emp.effective_from is None or emp.effective_from <= as_of
            ends = emp.effective_to is None or emp.effective_to >= as_of
            if starts and ends:
                candidates.setdefault(emp.emp_id, []).append(emp)

        resolved: dict[str, Employee] = {}
        for emp_id, rows in candidates.items():
            rows.sort(key=lambda e: e.effective_from or date.min)
            resolved[emp_id] = rows[-1]
        return resolved

    # -- lookup ------------------------------------------------------------

    def get(self, emp_id: str) -> Optional[Employee]:
        return self._by_id.get(emp_id)

    def by_email(self, email: str) -> Optional[Employee]:
        """Map a signed-in Microsoft account to an employee.

        `st.session_state['user_info']['username']` is the UPN; matching is
        case-insensitive because casing is not stable across MSAL responses.
        """
        if not email:
            return None
        target = email.strip().lower()
        for emp in self._by_id.values():
            if emp.email and emp.email == target:
                return emp
        return None

    def all_employees(self, include_inactive: bool = False) -> list[Employee]:
        people = self._by_id.values()
        if not include_inactive:
            people = [e for e in people if e.is_active]
        return sorted(people, key=lambda e: (self.depth(e.emp_id), e.name))

    # -- structure ---------------------------------------------------------

    def depth(self, emp_id: str) -> int:
        """Distance from the top. The MD is 0.

        Returns -1 for an unknown employee or one caught in a reports_to
        cycle, so callers can filter rather than crash on bad data.
        """
        if emp_id in self._depth_cache:
            return self._depth_cache[emp_id]

        seen: set[str] = set()
        current = emp_id
        chain: list[str] = []
        while True:
            emp = self._by_id.get(current)
            if emp is None:
                for node in chain:
                    self._depth_cache[node] = -1
                return -1
            if current in seen:
                logger.error(
                    "reports_to cycle detected at '%s' — depth unresolvable", current
                )
                for node in chain:
                    self._depth_cache[node] = -1
                return -1
            seen.add(current)
            chain.append(current)

            if not emp.reports_to_emp_id:
                break
            if len(chain) > MAX_TREE_DEPTH:
                logger.error("reports_to chain from '%s' exceeded max depth", emp_id)
                for node in chain:
                    self._depth_cache[node] = -1
                return -1
            current = emp.reports_to_emp_id

        # chain runs subject -> ... -> root, so depth counts back down
        for offset, node in enumerate(chain):
            self._depth_cache[node] = len(chain) - 1 - offset
        return self._depth_cache[emp_id]

    def direct_reports(self, emp_id: str, include_inactive: bool = False) -> list[Employee]:
        reports = [
            self._by_id[child]
            for child in self._children.get(emp_id, [])
            if child in self._by_id
        ]
        if not include_inactive:
            reports = [e for e in reports if e.is_active]
        return sorted(reports, key=lambda e: e.name)

    def subtree(self, emp_id: str, include_self: bool = False) -> list[Employee]:
        """Everyone below this person, breadth-first."""
        out: list[Employee] = []
        if include_self and emp_id in self._by_id:
            out.append(self._by_id[emp_id])
        queue = list(self._children.get(emp_id, []))
        seen: set[str] = {emp_id}
        while queue:
            node = queue.pop(0)
            if node in seen or node not in self._by_id:
                continue
            seen.add(node)
            out.append(self._by_id[node])
            queue.extend(self._children.get(node, []))
        return out

    def manager_of(self, emp_id: str) -> Optional[Employee]:
        emp = self._by_id.get(emp_id)
        if emp is None or not emp.reports_to_emp_id:
            return None
        return self._by_id.get(emp.reports_to_emp_id)

    def ancestors(self, emp_id: str) -> list[Employee]:
        """Managers from immediate upward, stopping safely on a cycle."""
        out: list[Employee] = []
        seen: set[str] = {emp_id}
        current = self.manager_of(emp_id)
        while current is not None and current.emp_id not in seen:
            out.append(current)
            seen.add(current.emp_id)
            current = self.manager_of(current.emp_id)
        return out

    def root(self) -> Optional[Employee]:
        for emp in self._by_id.values():
            if not emp.reports_to_emp_id and emp.is_active:
                return emp
        return None

    def employees_at_depth(self, depth: int, include_inactive: bool = False) -> list[Employee]:
        return [
            emp for emp in self.all_employees(include_inactive)
            if self.depth(emp.emp_id) == depth
        ]

    def max_depth(self) -> int:
        depths = [self.depth(e.emp_id) for e in self.all_employees()]
        return max([d for d in depths if d >= 0], default=0)

    # -- permissions -------------------------------------------------------

    def is_direct_manager(self, actor_id: str, subject_id: str) -> bool:
        """Sets the card and scores. The only role that can do either."""
        subject = self._by_id.get(subject_id)
        return bool(subject and subject.reports_to_emp_id == actor_id and actor_id)

    def is_ancestor(self, actor_id: str, subject_id: str) -> bool:
        """Anywhere above in the chain — grants view, not edit."""
        return any(a.emp_id == actor_id for a in self.ancestors(subject_id))

    def is_management(self, emp_id: str) -> bool:
        """The MD (depth 0) plus everyone at depth 1.

        Calibrates scores, locks months, publishes business needs, runs the
        exception review and validates quarters. `management_override` exists
        only for deliberate exceptions and is expected to stay empty.
        """
        emp = self._by_id.get(emp_id)
        if emp is None or not emp.is_active:
            return False
        override = (emp.management_override or "").strip().lower()
        if override == "grant":
            return True
        if override == "revoke":
            return False
        depth = self.depth(emp_id)
        return 0 <= depth <= MANAGEMENT_MAX_DEPTH

    def management(self) -> list[Employee]:
        return [e for e in self.all_employees() if self.is_management(e.emp_id)]

    def is_admin(self, emp_id: str) -> bool:
        """Edits the org tree, KPI library and parameters."""
        emp = self._by_id.get(emp_id)
        return bool(emp and emp.is_admin and emp.is_active)

    def can_view(self, actor_id: str, subject_id: str) -> bool:
        if actor_id == subject_id:
            return True
        return (
            self.is_management(actor_id)
            or self.is_admin(actor_id)
            or self.is_ancestor(actor_id, subject_id)
        )

    def can_score(self, actor_id: str, subject_id: str) -> bool:
        """Only the direct manager scores. Management adjusts at calibration
        instead, which keeps an audit trail of who changed what and why."""
        return self.is_direct_manager(actor_id, subject_id)

    def amendment_approver(self, requester_id: str) -> Optional[Employee]:
        """Exactly one level above the requester.

        Foundation Doc 03: accountability moves up exactly one level and never
        leapfrogs. Returns None for the root, whose cards no one can approve
        an amendment to — that case is surfaced in the UI rather than being
        silently self-approved.
        """
        return self.manager_of(requester_id)

    # -- validation --------------------------------------------------------

    def validate_reassignment(self, emp_id: str, new_manager_id: str) -> Optional[str]:
        """Check a proposed reports_to change. Returns an error, or None.

        Called before the Admin tab writes, because a cycle written to the
        sheet breaks depth resolution for everyone underneath it.
        """
        if not new_manager_id:
            root = self.root()
            if root is not None and root.emp_id != emp_id:
                return (
                    f"'{emp_id}' would become a second root — only "
                    f"'{root.emp_id}' may have no manager."
                )
            return None
        if new_manager_id == emp_id:
            return "An employee cannot report to themselves."
        if new_manager_id not in self._by_id:
            return f"Manager '{new_manager_id}' does not exist."

        # Walking up from the proposed manager must not lead back to emp_id.
        seen: set[str] = set()
        current: Optional[str] = new_manager_id
        while current:
            if current == emp_id:
                return (
                    f"'{new_manager_id}' reports to '{emp_id}' — this would "
                    "create a reporting cycle."
                )
            if current in seen:
                return "The existing hierarchy already contains a cycle."
            seen.add(current)
            manager = self._by_id.get(current)
            current = manager.reports_to_emp_id if manager else None
        return None

    def validate_tree(self) -> list[str]:
        """Whole-tree health check for the Admin tab."""
        problems: list[str] = []
        roots = [e for e in self._by_id.values() if not e.reports_to_emp_id and e.is_active]
        if not roots:
            problems.append("No root employee — someone must have no manager.")
        elif len(roots) > 1:
            names = ", ".join(sorted(e.emp_id for e in roots))
            problems.append(f"Multiple roots found: {names}.")

        for emp in self._by_id.values():
            if emp.reports_to_emp_id and emp.reports_to_emp_id not in self._by_id:
                problems.append(
                    f"'{emp.emp_id}' reports to '{emp.reports_to_emp_id}', "
                    "who is not in the employee list."
                )
            elif emp.is_active and self.depth(emp.emp_id) < 0:
                problems.append(f"'{emp.emp_id}' is in a reporting cycle.")
            if emp.is_active and not emp.email:
                problems.append(f"'{emp.emp_id}' has no email — they cannot sign in.")

        emails: dict[str, str] = {}
        for emp in self._by_id.values():
            if not emp.email:
                continue
            if emp.email in emails:
                problems.append(
                    f"Email '{emp.email}' is shared by '{emails[emp.email]}' "
                    f"and '{emp.emp_id}'."
                )
            emails[emp.email] = emp.emp_id
        return problems
