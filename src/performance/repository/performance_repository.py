"""Persistence for the performance system.

The only module that knows tab and column names — every service above it works
in models. Backed by the performance spreadsheet, which is deliberately
separate from the operations sheet: score data is salary-adjacent and does not
belong alongside tabs the whole team edits daily.

Reads are cached per instance because a single page render touches the same
tabs repeatedly and Google's per-minute read quota is the binding constraint
on this app. Call `invalidate()` after a write, or build a new repository.

Reads raise rather than returning empty on failure. An empty employee list and
a failed employee read look identical to a caller, and treating the second as
the first would silently strip everyone's permissions.
"""

from __future__ import annotations

from typing import Any, Optional, TypeVar

import pandas as pd

from config import settings
from src.performance.models.performance_models import (
    SHEET_MODELS,
    AmendmentRequest,
    AuditEntry,
    BusinessNeed,
    CheckIn,
    CycleTask,
    Employee,
    KBDItem,
    KPICard,
    KPICardItem,
    KPILibraryEntry,
    LevelConfig,
    MonthlyScore,
    Parameter,
    QuarterlyReview,
    Role,
    ScoreItem,
    SheetModel,
)
from src.shared.integrations.google_drive_service import google_drive_service
from src.shared.utils.logger_config import setup_logger

logger = setup_logger(__name__)

T = TypeVar("T", bound=SheetModel)


class PerformanceRepositoryError(Exception):
    """Raised when the performance sheet is unreachable or misconfigured."""


class PerformanceRepository:
    def __init__(self, spreadsheet_id: Optional[str] = None):
        self.spreadsheet_id = spreadsheet_id or settings.performance.performance_sheets_id
        self.google = google_drive_service
        self._cache: dict[str, pd.DataFrame] = {}

    # -- plumbing ----------------------------------------------------------

    def _require_id(self) -> str:
        if not self.spreadsheet_id:
            raise PerformanceRepositoryError(
                "No performance spreadsheet configured. Set "
                "[performance].performance_sheets_id in secrets.toml."
            )
        return self.spreadsheet_id

    def invalidate(self, sheet: Optional[str] = None) -> None:
        """Drop cached reads. Called after every write."""
        if sheet is None:
            self._cache.clear()
        else:
            self._cache.pop(sheet, None)

    def _frame(self, sheet: str) -> pd.DataFrame:
        if sheet in self._cache:
            return self._cache[sheet]
        # raise_on_error: a failed read must not masquerade as an empty tab.
        frame = self.google.get_worksheet_data(
            self._require_id(), sheet, header_row=1, raise_on_error=True
        )
        self._cache[sheet] = frame
        return frame

    def _read(self, model: type[T]) -> list[T]:
        try:
            frame = self._frame(model.SHEET)
        except Exception as exc:
            raise PerformanceRepositoryError(
                f"Could not read '{model.SHEET}': {exc}"
            ) from exc
        if frame.empty:
            return []

        rows: list[T] = []
        for index, record in enumerate(frame.to_dict("records"), start=2):
            # Skip fully blank rows — Sheets pads them below real data.
            if not any(str(value).strip() for value in record.values()):
                continue
            try:
                rows.append(model.from_row(record))
            except Exception as exc:
                # One malformed row must not blank out the whole tab.
                logger.error(
                    "Skipping malformed row %d of '%s': %s", index, model.SHEET, exc
                )
        return rows

    def _append(self, records: list[T]) -> bool:
        if not records:
            return True
        sheet = records[0].SHEET
        ok = self.google.append_data(
            self._require_id(), sheet, [r.to_row() for r in records]
        )
        if not ok:
            raise PerformanceRepositoryError(f"Failed to append to '{sheet}'.")
        self.invalidate(sheet)
        return True

    def _upsert(self, record: T, key_column_index: int = 0) -> bool:
        ok = self.google.upsert_row(
            self._require_id(), record.SHEET, record.to_row(), key_column_index
        )
        if not ok:
            raise PerformanceRepositoryError(f"Failed to save to '{record.SHEET}'.")
        self.invalidate(record.SHEET)
        return True

    def _delete_by_key(self, model: type[T], key: str, key_column_index: int = 0) -> bool:
        ok = self.google.delete_rows_by_key(
            self._require_id(), model.SHEET, key, key_column_index
        )
        if not ok:
            raise PerformanceRepositoryError(f"Failed to delete from '{model.SHEET}'.")
        self.invalidate(model.SHEET)
        return True

    # -- setup -------------------------------------------------------------

    def ensure_tabs(self) -> dict[str, bool]:
        """Create any missing tab with its headers. Safe to re-run."""
        results: dict[str, bool] = {}
        for model in SHEET_MODELS:
            results[model.SHEET] = self.google.ensure_worksheet_with_headers(
                self._require_id(), model.SHEET, list(model.HEADERS)
            )
        self.invalidate()
        return results

    def health_check(self) -> tuple[bool, str]:
        try:
            if not self.google.client:
                return False, "Google Drive client not initialised — check credentials."
            if not self.spreadsheet_id:
                return False, "performance_sheets_id is not set in secrets."
            if not self.google.test_connection(self.spreadsheet_id):
                return False, f"Cannot open spreadsheet '{self.spreadsheet_id}'."
            return True, "Connected."
        except Exception as exc:
            return False, str(exc)

    # -- parameters & levels -----------------------------------------------

    def get_parameters(self) -> dict[str, str]:
        return {p.key: p.value for p in self._read(Parameter) if p.key}

    def save_parameter(self, key: str, value: str, description: str = "") -> bool:
        return self._upsert(Parameter(key=key, value=value, description=description))

    def get_levels(self) -> list[LevelConfig]:
        return sorted(self._read(LevelConfig), key=lambda lvl: lvl.rank)

    def get_roles(self) -> list[Role]:
        return self._read(Role)

    def get_role_for(self, designation: str) -> Optional[Role]:
        target = (designation or "").strip().lower()
        for role in self.get_roles():
            if role.designation.strip().lower() == target:
                return role
        return None

    # -- employees ---------------------------------------------------------

    def get_employees(self) -> list[Employee]:
        """Every employee row, including superseded effective-dated ones.

        Resolution to a point in time is OrgChart's job, not the repository's.
        """
        return self._read(Employee)

    def save_employee(self, employee: Employee) -> bool:
        return self._upsert(employee)

    def next_employee_id(self) -> str:
        """Next free E-number, gap-tolerant."""
        used = set()
        for emp in self.get_employees():
            text = (emp.emp_id or "").strip().upper()
            if text.startswith("E") and text[1:].isdigit():
                used.add(int(text[1:]))
        candidate = 1
        while candidate in used:
            candidate += 1
        return f"E{candidate:02d}"

    # -- business needs & library ------------------------------------------

    def get_business_needs(self, period: Optional[str] = None) -> list[BusinessNeed]:
        needs = self._read(BusinessNeed)
        return [n for n in needs if n.period == period] if period else needs

    def save_business_needs(self, needs: list[BusinessNeed]) -> bool:
        return self._append(needs)

    def replace_business_needs(self, period: str, needs: list[BusinessNeed]) -> bool:
        """Republishing a month replaces that month rather than duplicating it."""
        self._delete_by_key(BusinessNeed, period, key_column_index=1)
        return self._append(needs)

    def get_kpi_library(self, active_only: bool = True) -> list[KPILibraryEntry]:
        entries = self._read(KPILibraryEntry)
        return [e for e in entries if e.active] if active_only else entries

    def save_kpi_library_entry(self, entry: KPILibraryEntry) -> bool:
        return self._upsert(entry)

    # -- cards -------------------------------------------------------------

    def get_cards(
        self, period: Optional[str] = None, emp_id: Optional[str] = None
    ) -> list[KPICard]:
        cards = self._read(KPICard)
        if period:
            cards = [c for c in cards if c.period == period]
        if emp_id:
            cards = [c for c in cards if c.emp_id == emp_id]
        return cards

    def get_card(self, emp_id: str, period: str) -> Optional[KPICard]:
        matches = self.get_cards(period=period, emp_id=emp_id)
        return matches[0] if matches else None

    def save_card(self, card: KPICard) -> bool:
        return self._upsert(card)

    def get_card_items(self, card_id: str) -> list[KPICardItem]:
        items = [i for i in self._read(KPICardItem) if i.card_id == card_id]
        return sorted(items, key=lambda i: i.seq)

    def get_kbd_items(self, card_id: str, pillar: Optional[str] = None) -> list[KBDItem]:
        items = [i for i in self._read(KBDItem) if i.card_id == card_id]
        if pillar:
            items = [i for i in items if i.pillar == pillar]
        return sorted(items, key=lambda i: (i.pillar, i.seq))

    def replace_card_items(
        self, card_id: str, result_items: list[KPICardItem], kbd_items: list[KBDItem]
    ) -> bool:
        """Write a card's items, replacing whatever was there.

        Deletes precede appends so re-saving a card never leaves duplicates
        behind. Both tabs key on card_id in column A.
        """
        self._delete_by_key(KPICardItem, card_id, key_column_index=0)
        self._delete_by_key(KBDItem, card_id, key_column_index=0)
        self._append(result_items)
        self._append(kbd_items)
        return True

    # -- amendments --------------------------------------------------------

    def get_amendments(
        self, card_id: Optional[str] = None, status: Optional[str] = None
    ) -> list[AmendmentRequest]:
        rows = self._read(AmendmentRequest)
        if card_id:
            rows = [a for a in rows if a.card_id == card_id]
        if status:
            rows = [a for a in rows if a.status == status]
        return rows

    def save_amendment(self, amendment: AmendmentRequest) -> bool:
        return self._upsert(amendment)

    # -- scores ------------------------------------------------------------

    def get_score_items(
        self,
        emp_id: Optional[str] = None,
        period: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> list[ScoreItem]:
        rows = self._read(ScoreItem)
        if emp_id:
            rows = [s for s in rows if s.emp_id == emp_id]
        if period:
            rows = [s for s in rows if s.period == period]
        if stage:
            rows = [s for s in rows if s.stage == stage]
        return rows

    def save_score_items(self, items: list[ScoreItem]) -> bool:
        return self._append(items)

    def get_monthly_scores(
        self,
        emp_id: Optional[str] = None,
        period: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> list[MonthlyScore]:
        rows = self._read(MonthlyScore)
        if emp_id:
            rows = [s for s in rows if s.emp_id == emp_id]
        if period:
            rows = [s for s in rows if s.period == period]
        if stage:
            rows = [s for s in rows if s.stage == stage]
        return rows

    def save_monthly_score(self, score: MonthlyScore) -> bool:
        return self._upsert(score)

    # -- reviews -----------------------------------------------------------

    def get_check_ins(self, card_id: Optional[str] = None) -> list[CheckIn]:
        rows = self._read(CheckIn)
        return [c for c in rows if c.card_id == card_id] if card_id else rows

    def save_check_in(self, check_in: CheckIn) -> bool:
        return self._upsert(check_in)

    def get_quarterly_reviews(
        self, quarter: Optional[str] = None, emp_id: Optional[str] = None
    ) -> list[QuarterlyReview]:
        rows = self._read(QuarterlyReview)
        if quarter:
            rows = [r for r in rows if r.quarter == quarter]
        if emp_id:
            rows = [r for r in rows if r.emp_id == emp_id]
        return rows

    def save_quarterly_review(self, review: QuarterlyReview) -> bool:
        return self._upsert(review)

    # -- cycle tasks -------------------------------------------------------

    def get_cycle_tasks(
        self,
        period: Optional[str] = None,
        owner_emp_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[CycleTask]:
        rows = self._read(CycleTask)
        if period:
            rows = [t for t in rows if t.period == period]
        if owner_emp_id:
            rows = [t for t in rows if t.owner_emp_id == owner_emp_id]
        if status:
            rows = [t for t in rows if t.status == status]
        return rows

    def save_cycle_tasks(self, tasks: list[CycleTask]) -> bool:
        return self._append(tasks)

    def save_cycle_task(self, task: CycleTask) -> bool:
        return self._upsert(task)

    def has_tasks_for_period(self, period: str) -> bool:
        """Guards against generating a period's tasks twice."""
        return any(t.period == period for t in self._read(CycleTask))

    # -- audit -------------------------------------------------------------

    def log(self, entries: list[AuditEntry]) -> bool:
        """Append-only. Never raises — losing an audit line must not abort the
        user's actual work, but it must be visible in the logs."""
        try:
            return self._append(entries)
        except Exception as exc:
            logger.error("Failed to write %d audit entries: %s", len(entries), exc)
            return False

    def get_audit(self, entity_id: Optional[str] = None) -> list[AuditEntry]:
        rows = self._read(AuditEntry)
        return [a for a in rows if a.entity_id == entity_id] if entity_id else rows
