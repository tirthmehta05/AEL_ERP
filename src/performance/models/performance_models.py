"""Pydantic models for the employee performance & review system.

Every model maps to one tab in the performance spreadsheet. Sheet headers are
the snake_case field names verbatim, so `to_row` / `from_row` are generic and
there is no header->field mapping table to drift out of sync. This sheet is
machine-owned — humans read it through the Performance page, not raw.

Everything read back from Google Sheets is a string, so the models coerce
blanks to None and parse dates/bools/numbers defensively. A malformed cell
must never take the whole page down.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Level(str, Enum):
    MD = "MD"
    DIRECTOR = "Director"
    VP = "VP"
    SR_ASSOCIATE = "Sr. Associate"
    ASSOCIATE = "Associate"


class Pillar(str, Enum):
    RESULT = "Result"
    KNOWLEDGE = "Knowledge"
    BEHAVIOUR = "Behaviour"
    DISCIPLINE = "Discipline"


class Direction(str, Enum):
    """Which way a KPI is good.

    The Performance Master computes Actual/Target for every KPI, which is
    backwards for LOWER metrics (scrap rate, DSO, lead time) — it scores a
    miss as an overachievement. Storing direction is what lets scoring.py
    fix that.
    """

    HIGHER = "higher"   # higher is better - volume, revenue, on-time %
    LOWER = "lower"     # lower is better  - scrap, DSO, lead time, overdue
    BINARY = "binary"   # milestone hit or missed
    RANGE = "range"     # good inside a band


class OutcomeType(str, Enum):
    OUTCOME = "outcome"    # business result
    OUTPUT = "output"      # deliverable produced
    ACTIVITY = "activity"  # effort expended


class ItemSource(str, Enum):
    CARRIED = "carried"
    LIBRARY = "library"
    BUSINESS_NEED = "business_need"
    CUSTOM = "custom"


class ChangeType(str, Enum):
    KEPT = "kept"
    EDITED = "edited"
    ADDED = "added"
    DELETED = "deleted"


class CardStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    LIVE = "live"
    AMENDED = "amended"
    LOCKED = "locked"


class ScoreStage(str, Enum):
    SELF = "self"
    MANAGER = "manager"
    CALIBRATED = "calibrated"
    LOCKED = "locked"


class AccountabilityLayer(str, Enum):
    """Foundation Doc 03. Forces the manager to confirm the person actually
    has the authority to move the KPI before it lands on their card."""

    EXECUTION = "L1 Execution"
    SUPERVISION = "L2 Supervision"
    DESIGN = "L3 Design"


class CycleStage(str, Enum):
    PUBLISH_NEEDS = "publish_needs"
    SET_CARDS = "set_cards"
    ACKNOWLEDGE = "acknowledge"
    EXCEPTION_REVIEW = "exception_review"
    SELF_SCORE = "self_score"
    MANAGER_SCORE = "manager_score"
    CALIBRATE = "calibrate"
    LOCK = "lock"
    CHECK_IN = "check_in"
    QUARTERLY_REVIEW = "quarterly_review"
    QUARTER_VALIDATE = "quarter_validate"


class TaskStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"


# --------------------------------------------------------------------------
# Serialization helpers
# --------------------------------------------------------------------------


def _to_cell(value: Any) -> Any:
    """Render a Python value for a Google Sheets cell."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return " | ".join(str(v) for v in value)
    return value


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in {"TRUE", "YES", "Y", "1"}


def parse_optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_optional_date(value: Any) -> Optional[date]:
    """Parse a date cell, tolerating the formats this codebase already emits.

    Sheets round-trips dates as text, and the ops sheets use dd/mm/yyyy while
    this module writes ISO. Accept both rather than losing a row.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------
# Base
# --------------------------------------------------------------------------


class SheetModel(BaseModel):
    """A model persisted as one row of one tab.

    HEADERS is the authoritative column order and must contain field names
    exactly. `to_row` and `from_row` derive from it, so adding a column means
    editing one list.
    """

    SHEET: ClassVar[str] = ""
    HEADERS: ClassVar[list[str]] = []

    def to_row(self) -> list[Any]:
        return [_to_cell(getattr(self, header)) for header in self.HEADERS]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "SheetModel":
        return cls(**{header: row.get(header, "") for header in cls.HEADERS})

    @classmethod
    def blank_row(cls) -> dict[str, str]:
        return {header: "" for header in cls.HEADERS}


# --------------------------------------------------------------------------
# Org
# --------------------------------------------------------------------------


class Employee(SheetModel):
    """One person, effective-dated.

    A person can have several rows over time. `reports_to_emp_id` is resolved
    as of the period being acted on, so re-organising never rewrites who
    actually scored whom last quarter.
    """

    SHEET: ClassVar[str] = "Employees"
    HEADERS: ClassVar[list[str]] = [
        "emp_id", "name", "email", "designation", "level", "department",
        "reports_to_emp_id", "doj", "status", "effective_from",
        "effective_to", "is_admin", "management_override",
    ]

    emp_id: str
    name: str
    email: str = ""
    designation: str = ""
    level: str = ""
    department: str = ""
    reports_to_emp_id: str = ""
    doj: Optional[date] = None
    status: str = "active"
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    is_admin: bool = False
    # "grant" or "revoke" to override depth-derived management rights.
    # Expected to stay empty — management is normally the MD plus depth 1.
    management_override: str = ""

    @field_validator("doj", "effective_from", "effective_to", mode="before")
    @classmethod
    def _dates(cls, v: Any) -> Any:
        return parse_optional_date(v)

    @field_validator("is_admin", mode="before")
    @classmethod
    def _bools(cls, v: Any) -> Any:
        return parse_bool(v)

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v: Any) -> str:
        return str(v or "").strip().lower()

    @property
    def is_active(self) -> bool:
        return str(self.status).strip().lower() == "active"


class LevelConfig(SheetModel):
    """Compensation shape per level, mirroring Performance Master Parameters
    section 2. Held here so the ERP can preview payout without the workbook."""

    SHEET: ClassVar[str] = "Levels"
    HEADERS: ClassVar[list[str]] = [
        "level", "rank", "variable_pct", "company_share", "individual_share",
    ]

    level: str
    rank: int = 0
    variable_pct: float = 0.0
    company_share: float = 0.0
    individual_share: float = 0.0

    @field_validator("rank", mode="before")
    @classmethod
    def _rank(cls, v: Any) -> int:
        return int(parse_optional_float(v) or 0)

    @field_validator("variable_pct", "company_share", "individual_share", mode="before")
    @classmethod
    def _floats(cls, v: Any) -> float:
        return parse_optional_float(v) or 0.0


class Role(SheetModel):
    """Primary Ownership text from Foundation Doc 02, per role.

    Feeds the AI prompt builder so a drafted KPI is anchored to what the role
    actually owns rather than to a generic job title.
    """

    SHEET: ClassVar[str] = "Roles"
    HEADERS: ClassVar[list[str]] = [
        "role_id", "designation", "level", "department",
        "primary_ownership", "not_responsible_for", "active",
    ]

    role_id: str
    designation: str = ""
    level: str = ""
    department: str = ""
    primary_ownership: str = ""
    not_responsible_for: str = ""
    active: bool = True

    @field_validator("active", mode="before")
    @classmethod
    def _active(cls, v: Any) -> Any:
        return True if v == "" else parse_bool(v)


# --------------------------------------------------------------------------
# Planning inputs
# --------------------------------------------------------------------------


class BusinessNeed(SheetModel):
    """What the company needs this month.

    Carries both the numeric targets cascaded from the Scaling Plan and the
    company-wide Behaviour/Discipline baseline, which is why it has a pillar
    column rather than being Result-only.
    """

    SHEET: ClassVar[str] = "BusinessNeeds"
    HEADERS: ClassVar[list[str]] = [
        "need_id", "period", "pillar", "area", "metric", "unit", "target",
        "note", "is_company_default", "published_by", "published_at",
    ]

    need_id: str
    period: str = ""              # YYYY-MM
    pillar: str = Pillar.RESULT.value
    area: str = ""
    metric: str = ""
    unit: str = ""
    target: str = ""              # free text: numbers, "< 10", "Milestone"
    note: str = ""
    is_company_default: bool = False
    published_by: str = ""
    published_at: str = ""

    @field_validator("is_company_default", mode="before")
    @classmethod
    def _default(cls, v: Any) -> Any:
        return parse_bool(v)


class KPILibraryEntry(SheetModel):
    """A reusable, well-formed item a manager can pick instead of free-typing."""

    SHEET: ClassVar[str] = "KPILibrary"
    HEADERS: ClassVar[list[str]] = [
        "kpi_id", "pillar", "applies_to", "name", "direction", "unit",
        "measurement_method", "data_source", "default_weight",
        "outcome_type", "accountability_layer", "active",
    ]

    kpi_id: str
    pillar: str = Pillar.RESULT.value
    applies_to: str = ""          # level, department or designation
    name: str = ""
    direction: str = Direction.HIGHER.value
    unit: str = ""
    measurement_method: str = ""
    data_source: str = ""
    default_weight: float = 0.0
    outcome_type: str = OutcomeType.OUTCOME.value
    accountability_layer: str = AccountabilityLayer.EXECUTION.value
    active: bool = True

    @field_validator("default_weight", mode="before")
    @classmethod
    def _weight(cls, v: Any) -> float:
        return parse_optional_float(v) or 0.0

    @field_validator("active", mode="before")
    @classmethod
    def _active(cls, v: Any) -> Any:
        return True if v == "" else parse_bool(v)


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------


class KPICard(SheetModel):
    """One employee's card for one month, across all four pillars."""

    SHEET: ClassVar[str] = "KPICards"
    HEADERS: ClassVar[list[str]] = [
        "card_id", "emp_id", "period", "status", "version", "set_by",
        "set_at", "submitted_at", "acknowledged_at", "went_live_at",
        "locked_at", "quality_flags",
    ]

    card_id: str
    emp_id: str = ""
    period: str = ""              # YYYY-MM
    status: str = CardStatus.DRAFT.value
    version: int = 1
    set_by: str = ""
    set_at: str = ""
    submitted_at: str = ""
    acknowledged_at: str = ""
    went_live_at: str = ""
    locked_at: str = ""
    quality_flags: str = ""

    @field_validator("version", mode="before")
    @classmethod
    def _version(cls, v: Any) -> int:
        return int(parse_optional_float(v) or 1)

    @property
    def is_editable(self) -> bool:
        """Free editing only before the card goes live on the 1st.

        A live card changes only through the amendment request/approve flow.
        """
        return self.status in {CardStatus.DRAFT.value, CardStatus.SUBMITTED.value}


class KPICardItem(SheetModel):
    """One Result KPI on a card.

    `lineage_id` is what makes month-over-month trending survive free editing:
    carrying an item forward preserves it, so an edited KPI still charts
    against its own history, while a delete-and-re-add starts a new series.
    """

    SHEET: ClassVar[str] = "KPICardItems"
    HEADERS: ClassVar[list[str]] = [
        "card_id", "lineage_id", "seq", "kpi_id", "source", "change_type",
        "name", "direction", "unit", "target", "target_max", "weight",
        "measurement_method", "data_source", "business_need_ref",
        "accountability_layer", "outcome_type",
    ]

    card_id: str
    lineage_id: str
    seq: int = 0
    kpi_id: str = ""              # blank when custom
    source: str = ItemSource.CUSTOM.value
    change_type: str = ChangeType.ADDED.value
    name: str = ""
    direction: str = Direction.HIGHER.value
    unit: str = ""
    target: Optional[float] = None
    target_max: Optional[float] = None   # upper bound for RANGE direction
    weight: float = 0.0
    measurement_method: str = ""
    data_source: str = ""
    business_need_ref: str = ""
    accountability_layer: str = AccountabilityLayer.EXECUTION.value
    outcome_type: str = OutcomeType.OUTCOME.value

    @field_validator("seq", mode="before")
    @classmethod
    def _seq(cls, v: Any) -> int:
        return int(parse_optional_float(v) or 0)

    @field_validator("target", "target_max", mode="before")
    @classmethod
    def _targets(cls, v: Any) -> Any:
        return parse_optional_float(v)

    @field_validator("weight", mode="before")
    @classmethod
    def _weight(cls, v: Any) -> float:
        return parse_optional_float(v) or 0.0


class KBDItem(SheetModel):
    """One Knowledge, Behaviour or Discipline item.

    All three qualitative pillars share a tab — they have identical shape and
    identical lifecycle, and splitting them would triple the CRUD for nothing.
    """

    SHEET: ClassVar[str] = "KBDItems"
    HEADERS: ClassVar[list[str]] = [
        "card_id", "lineage_id", "seq", "pillar", "source", "change_type",
        "text", "evidence_expected", "weight",
    ]

    card_id: str
    lineage_id: str
    seq: int = 0
    pillar: str = Pillar.KNOWLEDGE.value
    source: str = ItemSource.CUSTOM.value
    change_type: str = ChangeType.ADDED.value
    text: str = ""
    evidence_expected: str = ""
    weight: float = 1.0

    @field_validator("seq", mode="before")
    @classmethod
    def _seq(cls, v: Any) -> int:
        return int(parse_optional_float(v) or 0)

    @field_validator("weight", mode="before")
    @classmethod
    def _weight(cls, v: Any) -> float:
        parsed = parse_optional_float(v)
        return 1.0 if parsed is None else parsed


class AmendmentRequest(SheetModel):
    """A request to change a live card between day 1 and day 10.

    Approval sits exactly one level above the requester, matching the
    Accountability Framework's escalate-one-level rule. The requester can
    never approve their own request.
    """

    SHEET: ClassVar[str] = "Amendments"
    HEADERS: ClassVar[list[str]] = [
        "amendment_id", "card_id", "emp_id", "period", "requested_by",
        "requested_at", "rationale", "changes_json", "status",
        "approver_emp_id", "decided_at", "decision_note",
    ]

    amendment_id: str
    card_id: str = ""
    emp_id: str = ""
    period: str = ""
    requested_by: str = ""
    requested_at: str = ""
    rationale: str = ""
    changes_json: str = ""
    status: str = "pending"       # pending | approved | rejected
    approver_emp_id: str = ""
    decided_at: str = ""
    decision_note: str = ""


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


class ScoreItem(SheetModel):
    """One item's score at one stage.

    Self and manager stages are separate rows for the same item, so an
    employee's own assessment is preserved next to their manager's rather
    than being overwritten by it.
    """

    SHEET: ClassVar[str] = "ScoreItems"
    HEADERS: ClassVar[list[str]] = [
        "score_item_id", "emp_id", "period", "stage", "card_id",
        "lineage_id", "pillar", "actual", "rating", "remark",
        "scored_by", "scored_at",
    ]

    score_item_id: str
    emp_id: str = ""
    period: str = ""
    stage: str = ScoreStage.SELF.value
    card_id: str = ""
    lineage_id: str = ""
    pillar: str = Pillar.RESULT.value
    actual: Optional[float] = None    # Result pillar
    rating: Optional[float] = None    # K/B/D pillars, 1-5
    remark: str = ""
    scored_by: str = ""
    scored_at: str = ""

    @field_validator("actual", "rating", mode="before")
    @classmethod
    def _numbers(cls, v: Any) -> Any:
        return parse_optional_float(v)


class MonthlyScore(SheetModel):
    """The rolled-up result for one employee-month at one stage."""

    SHEET: ClassVar[str] = "Scores"
    HEADERS: ClassVar[list[str]] = [
        "score_id", "emp_id", "period", "stage", "card_id", "result_pct",
        "knowledge_rating", "behaviour_rating", "discipline_rating",
        "monthly_score", "floor_applied", "scored_by", "scored_at",
    ]

    score_id: str
    emp_id: str = ""
    period: str = ""
    stage: str = ScoreStage.SELF.value
    card_id: str = ""
    result_pct: float = 0.0
    knowledge_rating: float = 0.0
    behaviour_rating: float = 0.0
    discipline_rating: float = 0.0
    monthly_score: float = 0.0
    floor_applied: bool = False
    scored_by: str = ""
    scored_at: str = ""

    @field_validator(
        "result_pct", "knowledge_rating", "behaviour_rating",
        "discipline_rating", "monthly_score", mode="before",
    )
    @classmethod
    def _floats(cls, v: Any) -> float:
        return parse_optional_float(v) or 0.0

    @field_validator("floor_applied", mode="before")
    @classmethod
    def _floor(cls, v: Any) -> Any:
        return parse_bool(v)


# --------------------------------------------------------------------------
# Reviews
# --------------------------------------------------------------------------


class CheckIn(SheetModel):
    """Mid-month check-in. Keeps month-end scoring free of surprises."""

    SHEET: ClassVar[str] = "CheckIns"
    HEADERS: ClassVar[list[str]] = [
        "checkin_id", "card_id", "emp_id", "period", "checkin_date",
        "rag_json", "blockers", "notes", "logged_by", "logged_at",
    ]

    checkin_id: str
    card_id: str = ""
    emp_id: str = ""
    period: str = ""
    checkin_date: Optional[date] = None
    rag_json: str = ""            # {lineage_id: "green"|"amber"|"red"}
    blockers: str = ""
    notes: str = ""
    logged_by: str = ""
    logged_at: str = ""

    @field_validator("checkin_date", mode="before")
    @classmethod
    def _date(cls, v: Any) -> Any:
        return parse_optional_date(v)


class QuarterlyReview(SheetModel):
    """The quarterly 1:1, with dual sign-off."""

    SHEET: ClassVar[str] = "QuarterlyReviews"
    HEADERS: ClassVar[list[str]] = [
        "review_id", "emp_id", "quarter", "meeting_date", "went_well",
        "didnt_go_well", "development_actions", "employee_comments",
        "manager_emp_id", "manager_signoff_at", "employee_signoff_at",
        "status",
    ]

    review_id: str
    emp_id: str = ""
    quarter: str = ""             # FY26-27 Q1
    meeting_date: Optional[date] = None
    went_well: str = ""
    didnt_go_well: str = ""
    development_actions: str = ""
    employee_comments: str = ""
    manager_emp_id: str = ""
    manager_signoff_at: str = ""
    employee_signoff_at: str = ""
    status: str = "pending"

    @field_validator("meeting_date", mode="before")
    @classmethod
    def _date(cls, v: Any) -> Any:
        return parse_optional_date(v)


# --------------------------------------------------------------------------
# Cadence & audit
# --------------------------------------------------------------------------


class CycleTask(SheetModel):
    """One thing one person owes by one date.

    This tab is the source of truth for the compliance board and for the
    daily alert job — nothing else decides who is late.
    """

    SHEET: ClassVar[str] = "CycleTasks"
    HEADERS: ClassVar[list[str]] = [
        "task_id", "period", "stage", "owner_emp_id", "subject_emp_id",
        "due_date", "status", "completed_at", "days_late",
        "last_alert_sent", "last_alert_kind",
    ]

    task_id: str
    period: str = ""
    stage: str = ""
    owner_emp_id: str = ""
    subject_emp_id: str = ""      # blank when the task is not about someone
    due_date: Optional[date] = None
    status: str = TaskStatus.OPEN.value
    completed_at: str = ""
    days_late: int = 0
    last_alert_sent: str = ""
    last_alert_kind: str = ""

    @field_validator("due_date", mode="before")
    @classmethod
    def _due(cls, v: Any) -> Any:
        return parse_optional_date(v)

    @field_validator("days_late", mode="before")
    @classmethod
    def _late(cls, v: Any) -> int:
        return int(parse_optional_float(v) or 0)

    @property
    def is_open(self) -> bool:
        return self.status == TaskStatus.OPEN.value


class AuditEntry(SheetModel):
    """Append-only. Every card and score mutation lands here."""

    SHEET: ClassVar[str] = "AuditLog"
    HEADERS: ClassVar[list[str]] = [
        "audit_id", "timestamp", "actor", "entity", "entity_id",
        "action", "field", "old_value", "new_value", "note",
    ]

    audit_id: str = Field(default_factory=lambda: new_id("AUD"))
    timestamp: str = ""
    actor: str = ""
    entity: str = ""
    entity_id: str = ""
    action: str = ""
    field: str = ""
    old_value: str = ""
    new_value: str = ""
    note: str = ""


class Parameter(SheetModel):
    """Free-form key/value configuration.

    Pillar weights, payout curves, gates and the deadline day-numbers all live
    here rather than in code, so the cadence can be retuned without a deploy.
    """

    SHEET: ClassVar[str] = "Parameters"
    HEADERS: ClassVar[list[str]] = ["key", "value", "description"]

    key: str
    value: str = ""
    description: str = ""


# Every model that owns a tab, in creation order. The seed script and the
# repository both read this, so a new tab is registered in exactly one place.
SHEET_MODELS: list[type[SheetModel]] = [
    Parameter, LevelConfig, Employee, Role, BusinessNeed, KPILibraryEntry,
    KPICard, KPICardItem, KBDItem, AmendmentRequest, ScoreItem, MonthlyScore,
    CheckIn, QuarterlyReview, CycleTask, AuditEntry,
]
