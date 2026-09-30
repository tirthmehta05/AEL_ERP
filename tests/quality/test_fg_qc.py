import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.quality.fg_qc import (
    NA,
    NO,
    QC_SHEET_HEADERS,
    STATUS_EXCEPTION,
    STATUS_OK,
    YES,
    FGQCSignOff,
    checks_for_order_type,
    is_core_building_job_card,
    order_type_from_job_card,
    qc_signed_by_line,
    qc_status_label,
    unanswered_checks,
)


def _all_yes(order_type):
    return {c.key: YES for c in checks_for_order_type(order_type)}


def _sign_off(order_type="LOOSE_STRIPS", answers=None, **overrides):
    fields = dict(
        order_type=order_type,
        answers=answers if answers is not None else _all_yes(order_type),
        floor_checked_by="Ramesh",
        signed_by="qc@amba.example",
        signed_by_name="QC Lead",
        signed_at=datetime(2026, 9, 14, 17, 5, 9),
        responsibility_accepted=True,
    )
    fields.update(overrides)
    return FGQCSignOff(**fields)


def test_core_gap_check_only_applies_to_core_building():
    core_keys = [c.key for c in checks_for_order_type("CORE_BUILDING")]
    strip_keys = [c.key for c in checks_for_order_type("LOOSE_STRIPS")]
    assert "no_core_gaps" in core_keys
    assert "no_core_gaps" not in strip_keys
    assert "no_core_gaps" not in [c.key for c in checks_for_order_type("EI_READY")]
    assert "material_as_per_jc" in strip_keys
    assert len(core_keys) == len(strip_keys) + 1


def test_na_is_only_a_valid_answer_for_the_hole_check():
    answers = _all_yes("LOOSE_STRIPS")
    answers["hole_size_ok"] = NA
    assert unanswered_checks("LOOSE_STRIPS", answers) == []

    answers["no_burr"] = NA
    assert [c.key for c in unanswered_checks("LOOSE_STRIPS", answers)] == ["no_burr"]


def test_all_yes_sign_off_is_ok_and_serialises_in_header_order():
    sign_off = _sign_off("CORE_BUILDING")
    values = sign_off.to_sheet_values()

    assert sign_off.status == STATUS_OK
    assert list(values) == QC_SHEET_HEADERS
    assert values["QCExceptions"] == ""
    assert values["QCSignedAt"] == "14/09/2026 17:05:09"
    payload = json.loads(values["QCChecksJSON"])
    assert payload["answers"]["no_core_gaps"] == YES
    assert payload["responsibility_accepted"] is True


def test_answers_for_checks_that_do_not_apply_are_dropped():
    answers = _all_yes("LOOSE_STRIPS")
    answers["no_core_gaps"] = NO
    sign_off = _sign_off("LOOSE_STRIPS", answers=answers)

    assert sign_off.status == STATUS_OK
    assert "no_core_gaps" not in json.loads(sign_off.to_sheet_values()["QCChecksJSON"])["answers"]


def test_unanswered_check_is_rejected():
    answers = _all_yes("LOOSE_STRIPS")
    del answers["free_of_rust"]
    with pytest.raises(ValidationError, match="Free of rust"):
        _sign_off(answers=answers)


@pytest.mark.parametrize("overrides, message", [
    ({"responsibility_accepted": False}, "declaration"),
    ({"floor_checked_by": "  "}, "floor person"),
    ({"signed_by": ""}, "logged-in user"),
])
def test_incomplete_sign_off_is_rejected(overrides, message):
    with pytest.raises(ValidationError, match=message):
        _sign_off(**overrides)


def test_exception_needs_reason_and_personal_responsibility():
    answers = _all_yes("LOOSE_STRIPS")
    answers["no_bend"] = NO
    answers["no_dent"] = NO

    with pytest.raises(ValidationError, match="reason"):
        _sign_off(answers=answers, exception_responsibility_accepted=True)
    with pytest.raises(ValidationError, match="personal responsibility"):
        _sign_off(answers=answers, exception_reason="Customer approved on call")

    sign_off = _sign_off(
        answers=answers,
        exception_reason="Customer approved on call",
        exception_responsibility_accepted=True,
    )
    values = sign_off.to_sheet_values()
    assert sign_off.status == STATUS_EXCEPTION
    assert values["QCExceptions"] == "No bend; No dent"
    assert values["QCExceptionReason"] == "Customer approved on call"


def test_status_label_and_signer_line_read_back_from_sheet_row():
    row = _sign_off().to_sheet_values()
    assert qc_status_label(row) == "OK"
    assert qc_signed_by_line(row) == "QC checked by: QC Lead"

    row.update(QCStatus=STATUS_EXCEPTION, QCExceptions="No dent", QCExceptionReason="Customer approved")
    assert qc_status_label(row) == "Exceptions: No dent"
    assert qc_signed_by_line(row) == "QC checked by: QC Lead"


@pytest.mark.parametrize("legacy_row", [{}, {"QCStatus": ""}, {"QCStatus": float("nan"), "QCSignedBy": float("nan")}])
def test_receipts_saved_before_qc_read_as_not_recorded(legacy_row):
    assert qc_status_label(legacy_row) == "Not recorded"
    assert qc_signed_by_line(legacy_row) is None


@pytest.mark.parametrize("job_card, expected", [
    ({"order_type": "CORE_BUILDING", "number_of_cores": 0}, "CORE_BUILDING"),
    ({"order_type": "LOOSE_STRIPS", "number_of_cores": 4}, "LOOSE_STRIPS"),
    ({"order_type": "EI_READY"}, "EI_READY"),
    ({"order_type": "bogus", "designs_json": json.dumps([{"hole": "Ready Entry"}]), "number_of_cores": 0}, "EI_READY"),
    ({"designs_json": "[]", "number_of_cores": "0"}, "LOOSE_STRIPS"),
    ({"designs_json": "[]", "number_of_cores": "0.0"}, "LOOSE_STRIPS"),
    ({"designs_json": "[]", "number_of_cores": "12"}, "CORE_BUILDING"),
    ({"designs_json": "not json", "number_of_cores": ""}, "CORE_BUILDING"),
    ({"designs_json": "5", "number_of_cores": 3}, "CORE_BUILDING"),
    ({"designs_json": float("nan"), "number_of_cores": float("nan")}, "CORE_BUILDING"),
])
def test_order_type_from_job_card_matches_service_precedence(job_card, expected):
    assert order_type_from_job_card(job_card) == expected
    assert is_core_building_job_card(job_card) is (expected == "CORE_BUILDING")


def test_free_text_that_looks_like_a_formula_is_stored_as_text():
    answers = _all_yes("LOOSE_STRIPS")
    answers["no_dent"] = NO
    values = _sign_off(
        answers=answers,
        exception_reason=" -2 dents, customer ok",
        floor_checked_by="=Ramesh",
        exception_responsibility_accepted=True,
    ).to_sheet_values()

    assert values["QCExceptionReason"] == "'-2 dents, customer ok"
    assert values["QCFloorCheckedBy"] == "'=Ramesh"
    assert values["QCSignedByName"] == "QC Lead"
