"""Finished-goods quality sign-off for TL strips, E&I laminations and built cores.

Every weight receipt — i.e. every dispatched lot — carries one Yes/No checklist
signed by the logged-in user. The same checklist is printed on the job card, so
the floor team ticks the paper copy and the person saving the receipt copies it
in. Every check is worded so that "Yes" means OK.

A "No" does not block the save: it needs a written reason and an explicit
acceptance of personal responsibility for any customer complaint on the lot.
"""

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Mapping, NamedTuple, Optional

from pydantic import BaseModel, model_validator

YES = "Yes"
NO = "No"
NA = "N/A"

STATUS_OK = "OK"
STATUS_EXCEPTION = "EXCEPTION"

# India has no DST, so a fixed offset is exact and needs no tz database on the server.
IST = timezone(timedelta(hours=5, minutes=30))
SIGNED_AT_FORMAT = "%d/%m/%Y %H:%M:%S"

# Columns added to the WeightReceipts sheet, in this order.
QC_SHEET_HEADERS = [
    "QCStatus",
    "QCExceptions",
    "QCExceptionReason",
    "QCFloorCheckedBy",
    "QCSignedByName",
    "QCSignedBy",
    "QCSignedAt",
    "QCChecksJSON",
]


class QCCheck(NamedTuple):
    key: str
    label: str
    core_only: bool = False
    allow_na: bool = False


FG_QC_CHECKS = (
    QCCheck("material_as_per_jc", "Material grade & thickness as per job card"),
    QCCheck("anti_rust_applied", "Anti-rust applied"),
    QCCheck("free_of_rust", "Free of rust"),
    QCCheck("cut_size_ok", "Cut size as per drawing (sample check)"),
    # Plain strips have no holes, so this is the one check that can be N/A.
    QCCheck("hole_size_ok", "Hole size & position as per drawing (sample check)", allow_na=True),
    QCCheck("stack_size_ok", "Stack size as per drawing"),
    QCCheck("no_burr", "No burr at edges & holes"),
    QCCheck("no_bend", "No bend"),
    QCCheck("no_dent", "No dent"),
    QCCheck("no_waviness", "No waviness"),
    QCCheck("bundles_ok", "No. of bundles as per drawing"),
    QCCheck("packaging_ok", "Packaging as per customer requirement"),
    QCCheck("no_core_gaps", "No gaps in core", core_only=True),
)


def checks_for_order_type(order_type: Optional[str]) -> List[QCCheck]:
    """Checks that apply to a receipt of this order type (core-only checks need CORE_BUILDING)."""
    is_core = order_type == "CORE_BUILDING"
    return [check for check in FG_QC_CHECKS if is_core or not check.core_only]


def answer_options(check: QCCheck) -> List[str]:
    return [YES, NO, NA] if check.allow_na else [YES, NO]


def unanswered_checks(order_type: Optional[str], answers: Mapping[str, Optional[str]]) -> List[QCCheck]:
    return [c for c in checks_for_order_type(order_type) if answers.get(c.key) not in answer_options(c)]


def exception_checks(order_type: Optional[str], answers: Mapping[str, Optional[str]]) -> List[QCCheck]:
    return [c for c in checks_for_order_type(order_type) if answers.get(c.key) == NO]


class FGQCSignOff(BaseModel):
    """A complete, signed QC checklist for one weight receipt. Cannot be built incomplete."""

    order_type: Optional[str] = None
    answers: Dict[str, str]
    floor_checked_by: str
    exception_reason: str = ""
    signed_by: str  # login email
    signed_by_name: str = ""
    signed_at: datetime
    responsibility_accepted: bool
    exception_responsibility_accepted: bool = False

    @model_validator(mode="after")
    def _require_complete_sign_off(self):
        missing = unanswered_checks(self.order_type, self.answers)
        if missing:
            raise ValueError("Unanswered QC checks: " + ", ".join(c.label for c in missing))
        if not self.floor_checked_by.strip():
            raise ValueError("Enter the name of the floor person who checked the lot.")
        if not self.signed_by.strip():
            raise ValueError("QC sign-off needs a logged-in user.")
        if not self.responsibility_accepted:
            raise ValueError("Accept the QC declaration to sign off.")
        if self.exceptions:
            if not self.exception_reason.strip():
                raise ValueError("Give a reason for dispatching with checks marked No.")
            if not self.exception_responsibility_accepted:
                raise ValueError("Accept personal responsibility for dispatching with exceptions.")
        return self

    @property
    def exceptions(self) -> List[str]:
        return [c.label for c in exception_checks(self.order_type, self.answers)]

    @property
    def status(self) -> str:
        return STATUS_EXCEPTION if self.exceptions else STATUS_OK

    def to_sheet_values(self) -> Dict[str, str]:
        """Values for the QC columns of the WeightReceipts sheet, keyed by header."""
        applicable = checks_for_order_type(self.order_type)
        return {
            "QCStatus": self.status,
            "QCExceptions": "; ".join(self.exceptions),
            "QCExceptionReason": _sheet_text(self.exception_reason),
            "QCFloorCheckedBy": _sheet_text(self.floor_checked_by),
            "QCSignedByName": _sheet_text(self.signed_by_name),
            "QCSignedBy": self.signed_by.strip(),
            "QCSignedAt": self.signed_at.strftime(SIGNED_AT_FORMAT),
            "QCChecksJSON": json.dumps({
                "version": 1,
                "order_type": self.order_type,
                "answers": {c.key: self.answers[c.key] for c in applicable},
                "responsibility_accepted": self.responsibility_accepted,
                "exception_responsibility_accepted": self.exception_responsibility_accepted,
            }),
        }


def _sheet_text(value: str) -> str:
    """Free text kept as plain text: Sheets would parse a leading = + - @ as a formula."""
    value = value.strip()
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def _cell(row: Mapping, column: str) -> str:
    """A sheet cell as stripped text; missing and NaN read as blank."""
    value = row.get(column)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def qc_status_label(receipt: Mapping) -> str:
    """Short QC status for a WeightReceipts row. Receipts saved before QC read 'Not recorded'."""
    status = _cell(receipt, "QCStatus")
    if status == STATUS_OK:
        return "OK"
    if status == STATUS_EXCEPTION:
        exceptions = _cell(receipt, "QCExceptions")
        return f"Exceptions: {exceptions}" if exceptions else "Exceptions"
    return "Not recorded"


def qc_signed_by_line(receipt: Mapping) -> Optional[str]:
    """'QC checked by: <signer name>' for printed documents, or None for receipts without QC.

    Only the signer is printed: no time, floor name, exceptions or reasons.
    """
    name = _cell(receipt, "QCSignedByName") or _cell(receipt, "QCSignedBy")
    return f"QC checked by: {name}" if name else None


def order_type_from_job_card(job_card: Mapping) -> str:
    """Order type of a Sales Order-JC row already in memory, so it costs no Sheets read.

    Same precedence as WeightReceiptService.get_order_type_for_job_card: the
    stored order_type, else "Ready Entry" designs mean EI_READY, else zero cores
    means LOOSE_STRIPS, else CORE_BUILDING.
    """
    order_type = _cell(job_card, "order_type")
    if order_type in ("CORE_BUILDING", "LOOSE_STRIPS", "EI_READY"):
        return order_type
    try:
        designs = json.loads(job_card.get("designs_json") or "[]")
    except (TypeError, ValueError):
        designs = []
    if isinstance(designs, list) and any(isinstance(d, dict) and d.get("hole") == "Ready Entry" for d in designs):
        return "EI_READY"
    try:
        if float(job_card.get("number_of_cores")) == 0:
            return "LOOSE_STRIPS"
    except (TypeError, ValueError):
        pass
    return "CORE_BUILDING"


def is_core_building_job_card(job_card: Mapping) -> bool:
    return order_type_from_job_card(job_card) == "CORE_BUILDING"
