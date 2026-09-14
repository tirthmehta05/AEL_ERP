from datetime import date, datetime
from unittest.mock import MagicMock, patch

from src.data_entry.models.weight_receipt_models import WeighedDesignDetail, WeightReceiptRequest
from src.data_entry.repository.weight_receipt_repository import WeightReceiptRepository
from src.data_entry.service.weight_receipt_service import WeightReceiptService
from src.quality.fg_qc import YES, FGQCSignOff, checks_for_order_type

BASE_ROW = [f"v{i}" for i in range(len(WeightReceiptRepository.BASE_HEADERS))]


def _repository():
    repo = WeightReceiptRepository()
    repo.google_service = MagicMock()
    repo.google_service.append_row_mapped_to_headers.return_value = True
    return repo


def test_repository_saves_receipt_and_qc_in_one_append():
    repo = _repository()

    assert repo.save_weight_receipt(BASE_ROW, extra_columns={"QCStatus": "OK"}) is True

    repo.google_service.append_row_mapped_to_headers.assert_called_once_with(
        repo.spreadsheet_id, "WeightReceipts", WeightReceiptRepository.BASE_HEADERS, BASE_ROW, {"QCStatus": "OK"},
    )
    repo.google_service.ensure_worksheet_with_headers.assert_not_called()
    repo.google_service.append_data.assert_not_called()


def test_repository_without_qc_passes_no_extra_columns():
    repo = _repository()

    assert repo.save_weight_receipt(BASE_ROW) is True
    assert repo.google_service.append_row_mapped_to_headers.call_args.args[4] == {}


def test_service_saves_qc_sign_off_with_the_receipt():
    with patch('src.data_entry.repository.weight_receipt_repository.WeightReceiptRepository'):
        service = WeightReceiptService()
    service.repository = MagicMock()
    service.repository.save_weight_receipt.return_value = True
    service._get_or_refresh_all_weight_receipts = MagicMock()

    sign_off = FGQCSignOff(
        order_type="LOOSE_STRIPS",
        answers={c.key: YES for c in checks_for_order_type("LOOSE_STRIPS")},
        floor_checked_by="Ramesh",
        signed_by="qc@amba.example",
        signed_at=datetime(2026, 9, 14, 10, 0),
        responsibility_accepted=True,
    )
    request = WeightReceiptRequest(
        weight_receipt_number="10400",
        receipt_date=date(2026, 9, 14),
        job_card_number="JC-1",
        party_name="Party",
        material="CRNO",
        sets=1,
        designs=[WeighedDesignDetail(width=100, length=500, actual_weight=12.5)],
        order_type="LOOSE_STRIPS",
        qc=sign_off,
    )

    assert service.save_weight_receipt(request) is True
    assert service.repository.save_weight_receipt.call_args.kwargs["extra_columns"] == sign_off.to_sheet_values()
