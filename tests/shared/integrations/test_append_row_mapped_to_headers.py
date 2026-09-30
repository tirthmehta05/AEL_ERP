import pytest
from unittest.mock import MagicMock, patch

with patch('config.settings', MagicMock()):
    from src.shared.integrations.google_drive_service import GoogleDriveService

FIXED_HEADERS = ["WeightReceiptNumber", "Date", "Deduction"]
FIXED_ROW = ["10400", "14/09/2026", 0.5]


class _FakeAPIError(Exception):
    """Stand-in for gspread.exceptions.APIError, which conftest mocks out."""


@pytest.fixture
def sheets():
    module = 'src.shared.integrations.google_drive_service'
    with patch(f'{module}.gspread.authorize') as mock_authorize:
        client = MagicMock()
        mock_authorize.return_value = client
        service = GoogleDriveService()
        service.client = client
        spreadsheet = client.open_by_key.return_value
        worksheet = MagicMock()
        worksheet.col_count = 26
        spreadsheet.worksheet.return_value = worksheet
        spreadsheet.add_worksheet.return_value = worksheet
        with patch(f'{module}.APIError', _FakeAPIError), \
             patch(f'{module}.gspread.utils.rowcol_to_a1', side_effect=lambda row, col: f"R{row}C{col}"), \
             patch(f'{module}.gspread.utils.absolute_range_name',
                   side_effect=lambda sheet, rng=None: f"'{sheet}'!{rng}" if rng else f"'{sheet}'"):
            yield service, spreadsheet, worksheet


def _set_headers(spreadsheet, headers):
    spreadsheet.values_get.return_value = {"values": [headers]} if headers else {"range": "'WeightReceipts'!A1:Z1"}


def _append(service, extra_columns):
    return service.append_row_mapped_to_headers("sheet", "WeightReceipts", FIXED_HEADERS, FIXED_ROW, extra_columns)


def _appended_row(spreadsheet):
    call = spreadsheet.values_append.call_args
    assert call.args == ("'WeightReceipts'",)
    assert call.kwargs["params"] == {"valueInputOption": "USER_ENTERED"}
    return call.kwargs["body"]["values"][0]


def test_normal_save_is_two_reads_and_one_write(sheets):
    service, spreadsheet, worksheet = sheets
    _set_headers(spreadsheet, FIXED_HEADERS + ["QCStatus", "QCSignedBy"])

    assert _append(service, {"QCSignedBy": "qc@amba.example", "QCStatus": "OK"}) is True

    spreadsheet.values_get.assert_called_once_with("'WeightReceipts'!1:1")
    spreadsheet.worksheet.assert_not_called()
    worksheet.update.assert_not_called()
    spreadsheet.values_append.assert_called_once()
    assert _appended_row(spreadsheet) == FIXED_ROW + ["OK", "qc@amba.example"]


def test_without_extra_columns_appends_the_fixed_row_unchanged(sheets):
    service, spreadsheet, worksheet = sheets
    _set_headers(spreadsheet, FIXED_HEADERS + ["Invoice"])

    assert _append(service, {}) is True
    spreadsheet.worksheet.assert_not_called()
    assert _appended_row(spreadsheet) == FIXED_ROW


def test_adds_missing_headers_after_last_filled_header(sheets):
    service, spreadsheet, worksheet = sheets
    # A column someone added by hand ("Invoice") stays where it is; QC headers go after it.
    _set_headers(spreadsheet, FIXED_HEADERS + ["Invoice", ""])
    worksheet.col_count = 4

    assert _append(service, {"QCStatus": "OK", "QCSignedBy": "qc@amba.example"}) is True

    worksheet.add_cols.assert_called_once_with(2)
    worksheet.update.assert_called_once_with("R1C5", [["QCStatus", "QCSignedBy"]], value_input_option='USER_ENTERED')
    # None leaves the hand-added column's cell untouched.
    assert _appended_row(spreadsheet) == FIXED_ROW + [None, "OK", "qc@amba.example"]


def test_empty_worksheet_gets_fixed_and_extra_headers(sheets):
    service, spreadsheet, worksheet = sheets
    _set_headers(spreadsheet, [])

    assert _append(service, {"QCStatus": "OK"}) is True

    worksheet.update.assert_called_once_with("R1C1", [FIXED_HEADERS + ["QCStatus"]], value_input_option='USER_ENTERED')
    assert _appended_row(spreadsheet) == FIXED_ROW + ["OK"]


def test_missing_worksheet_is_created_with_headers(sheets):
    service, spreadsheet, worksheet = sheets
    spreadsheet.values_get.side_effect = _FakeAPIError("Unable to parse range")

    assert _append(service, {"QCStatus": "OK"}) is True

    spreadsheet.add_worksheet.assert_called_once_with(title="WeightReceipts", rows=1, cols=4)
    spreadsheet.worksheet.assert_not_called()
    worksheet.update.assert_called_once_with("R1C1", [FIXED_HEADERS + ["QCStatus"]], value_input_option='USER_ENTERED')
    assert _appended_row(spreadsheet) == FIXED_ROW + ["OK"]


def test_writes_nothing_when_an_extra_header_sits_inside_the_fixed_columns(sheets):
    service, spreadsheet, worksheet = sheets
    _set_headers(spreadsheet, ["WeightReceiptNumber", "QCStatus", "Deduction"])

    assert _append(service, {"QCStatus": "OK"}) is False
    worksheet.update.assert_not_called()
    spreadsheet.values_append.assert_not_called()


def test_does_not_append_when_header_update_fails(sheets):
    service, spreadsheet, worksheet = sheets
    _set_headers(spreadsheet, list(FIXED_HEADERS))
    worksheet.update.side_effect = _FakeAPIError("403 forbidden")

    assert _append(service, {"QCStatus": "OK"}) is False
    spreadsheet.values_append.assert_not_called()


def test_does_not_append_when_header_read_and_sheet_creation_both_fail(sheets):
    service, spreadsheet, worksheet = sheets
    spreadsheet.values_get.side_effect = _FakeAPIError("403 forbidden")
    spreadsheet.add_worksheet.side_effect = _FakeAPIError("403 forbidden")

    assert _append(service, {"QCStatus": "OK"}) is False
    spreadsheet.values_append.assert_not_called()
