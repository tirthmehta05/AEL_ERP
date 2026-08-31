import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import gspread

# We have to patch the settings before importing the service
with patch('config.settings', MagicMock()):
    from src.shared.integrations.google_drive_service import (
        GoogleDriveService,
        RateLimitError,
        TransientAPIError,
    )

@pytest.fixture
def mocked_service():
    """Pytest fixture to provide a GoogleDriveService instance with a mocked client."""
    with patch('src.shared.integrations.google_drive_service.gspread.authorize') as mock_gspread_authorize:
        mock_gspread_client = MagicMock()
        mock_gspread_authorize.return_value = mock_gspread_client
        
        service = GoogleDriveService()
        service.client = mock_gspread_client
        yield service, mock_gspread_client

def test_get_worksheet_data_success(mocked_service):
    """Test successfully getting worksheet data."""
    service, mock_gspread_client = mocked_service
    spreadsheet_id = "test_spreadsheet_id"
    worksheet_name = "test_worksheet"

    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_gspread_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_worksheet.get_all_values.return_value = [
        ["ID", "Name", "Value"],
        ["1", "A", "100"],
        ["2", "B", "200"]
    ]

    df = service.get_worksheet_data(spreadsheet_id, worksheet_name)

    mock_gspread_client.open_by_key.assert_called_with(spreadsheet_id)
    mock_spreadsheet.worksheet.assert_called_with(worksheet_name)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ["ID", "Name", "Value"]

def test_append_data_success(mocked_service):
    """Test successfully appending data."""
    service, mock_gspread_client = mocked_service
    spreadsheet_id = "test_spreadsheet_id"
    worksheet_name = "test_worksheet"

    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_gspread_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet

    new_data = [["3", "C", "300"]]
    result = service.append_data(spreadsheet_id, worksheet_name, new_data)

    mock_worksheet.append_rows.assert_called_with(new_data, value_input_option='USER_ENTERED')
    assert result is True

def test_ensure_worksheet_with_headers_sheet_not_found(mocked_service):
    """Test ensuring worksheet when it does not exist."""
    service, mock_gspread_client = mocked_service
    spreadsheet_id = "test_spreadsheet_id"
    worksheet_name = "test_worksheet"

    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_gspread_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound
    mock_spreadsheet.add_worksheet.return_value = mock_worksheet

    headers = ["ID", "Name"]
    result = service.ensure_worksheet_with_headers(spreadsheet_id, worksheet_name, headers)

    mock_spreadsheet.add_worksheet.assert_called_with(title=worksheet_name, rows=1, cols=2)
    mock_worksheet.append_row.assert_called_with(headers, value_input_option='USER_ENTERED')
    assert result is True

def test_upsert_row_inserts_new_row(mocked_service):
    """Test that upsert adds a new row when the key is not found."""
    service, mock_gspread_client = mocked_service
    spreadsheet_id = "test_spreadsheet_id"
    worksheet_name = "test_worksheet"

    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_gspread_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_worksheet.findall.return_value = []  # Simulate key not found

    new_data = ["key-1", "New Data"]
    result = service.upsert_row(spreadsheet_id, worksheet_name, new_data, key_column_index=0)

    mock_worksheet.findall.assert_called_with("key-1", in_column=1)
    mock_worksheet.append_row.assert_called_with(new_data, value_input_option='USER_ENTERED')
    mock_worksheet.update.assert_not_called()
    assert result is True

def test_upsert_row_updates_existing_row(mocked_service):
    """Test that upsert updates an existing row when the key is found."""
    service, mock_gspread_client = mocked_service
    spreadsheet_id = "test_spreadsheet_id"
    worksheet_name = "test_worksheet"

    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_cell = MagicMock()
    mock_cell.row = 5
    mock_gspread_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_worksheet.findall.return_value = [mock_cell]  # Simulate key found at row 5

    update_data = ["key-1", "Updated Data"]
    result = service.upsert_row(spreadsheet_id, worksheet_name, update_data, key_column_index=0)

    mock_worksheet.findall.assert_called_with("key-1", in_column=1)
    mock_worksheet.update.assert_called_with('A5', [update_data], value_input_option='USER_ENTERED')
    mock_worksheet.append_row.assert_not_called()
    assert result is True


# ---------------------------------------------------------------------------
# Retry behaviour for transient API failures.
#
# Regression guard for the 2026-08-31 production incident: Google Sheets
# returned "[503]: The service is currently unavailable" for ~12 minutes and
# every read failed on its first and only attempt, because _execute_with_retry
# retried 429 alone. Transient 5xx must be retried like a rate limit.
# ---------------------------------------------------------------------------

class _FakeAPIError(Exception):
    """Stand-in for gspread.exceptions.APIError, which conftest mocks out."""

    def __init__(self, status_code):
        super().__init__(f"APIError: [{status_code}]")
        self.response = MagicMock()
        self.response.status_code = status_code


@pytest.fixture
def retry_service(mocked_service):
    """Service with a real APIError class patched in and sleep neutered.

    The whole `time` module is swapped for a mock rather than patching
    `time.sleep` directly: `google_drive_service.time` *is* the shared stdlib
    module object, so patching an attribute on it would make sleep a no-op
    process-wide for the duration of the test.
    """
    service, _ = mocked_service
    service.max_retries = 3
    service.initial_backoff = 0.0
    mock_time = MagicMock()
    with patch('src.shared.integrations.google_drive_service.APIError', _FakeAPIError), \
         patch('src.shared.integrations.google_drive_service.time', mock_time):
        yield service, mock_time.sleep


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
def test_execute_with_retry_recovers_from_transient_errors(retry_service, status_code):
    """A transient failure is retried and the eventual success is returned."""
    service, mock_sleep = retry_service
    func = MagicMock(side_effect=[_FakeAPIError(status_code), "ok"])

    assert service._execute_with_retry(func, "arg", kw=1) == "ok"
    assert func.call_count == 2
    func.assert_called_with("arg", kw=1)
    assert mock_sleep.call_count == 1


@pytest.mark.parametrize("status_code", [400, 403, 404])
def test_execute_with_retry_raises_permanent_errors_immediately(retry_service, status_code):
    """Non-transient API errors are not retried."""
    service, mock_sleep = retry_service
    func = MagicMock(side_effect=_FakeAPIError(status_code))

    with pytest.raises(_FakeAPIError):
        service._execute_with_retry(func)

    assert func.call_count == 1
    mock_sleep.assert_not_called()


def test_execute_with_retry_gives_up_after_max_retries(retry_service):
    """Persistent transient failures exhaust the retry budget and raise."""
    service, _ = retry_service
    func = MagicMock(side_effect=_FakeAPIError(503))

    with pytest.raises(TransientAPIError):
        service._execute_with_retry(func)

    assert func.call_count == service.max_retries


def test_exhausted_retries_raise_transient_not_api_error(retry_service):
    """Exhaustion raises TransientAPIError, not the underlying APIError.

    Callers wrap these calls in `except APIError: return False`. An exhausted
    retry means the outcome is UNKNOWN, so it must not be catchable as a clean
    failure by those handlers — it has to propagate.
    """
    service, _ = retry_service
    func = MagicMock(side_effect=_FakeAPIError(503))

    with pytest.raises(TransientAPIError) as exc_info:
        service._execute_with_retry(func)

    assert not isinstance(exc_info.value, _FakeAPIError)
    # the original error is preserved for diagnosis
    assert isinstance(exc_info.value.__cause__, _FakeAPIError)


def test_exhausted_rate_limit_raises_rate_limit_error(retry_service):
    """429 exhaustion keeps the more specific RateLimitError type."""
    service, _ = retry_service
    func = MagicMock(side_effect=_FakeAPIError(429))

    with pytest.raises(RateLimitError):
        service._execute_with_retry(func)


# --- Non-idempotent calls must not be replayed on 5xx ----------------------
#
# A 429 is a pre-execution quota rejection, so replaying is free. A 502/504 can
# arrive *after* Google applied the mutation, so replaying an append duplicates
# a row and replaying an index-based delete removes the wrong record.


@pytest.mark.parametrize("status_code", [408, 500, 502, 503, 504])
def test_non_idempotent_calls_are_not_retried_on_server_errors(retry_service, status_code):
    """Writes fail fast on 5xx rather than risking a double-apply."""
    service, mock_sleep = retry_service
    func = MagicMock(side_effect=_FakeAPIError(status_code))

    with pytest.raises(_FakeAPIError):
        service._execute_with_retry(func, _idempotent=False)

    assert func.call_count == 1
    mock_sleep.assert_not_called()


def test_non_idempotent_calls_are_still_retried_on_rate_limit(retry_service):
    """429 is safe to replay for writes too — the request never ran."""
    service, _ = retry_service
    func = MagicMock(side_effect=[_FakeAPIError(429), "ok"])

    assert service._execute_with_retry(func, _idempotent=False) == "ok"
    assert func.call_count == 2


def test_idempotent_flag_is_not_forwarded_to_the_wrapped_call(retry_service):
    """_idempotent is consumed by the wrapper, never passed to gspread."""
    service, _ = retry_service
    func = MagicMock(return_value="ok")

    service._execute_with_retry(func, "arg", value_input_option='USER_ENTERED', _idempotent=False)

    func.assert_called_once_with("arg", value_input_option='USER_ENTERED')


def test_delete_rows_by_key_does_not_retry_deletes_on_server_error(mocked_service):
    """The row-deletion loop is the least replayable call in the class.

    Indices are absolute and resolved by the preceding findall, so a delete
    that commits and loses its response would, on replay, remove whatever row
    slid into that index — a different record entirely.
    """
    service, mock_gspread_client = mocked_service
    service.max_retries = 3
    service.initial_backoff = 0.0

    mock_spreadsheet = MagicMock()
    mock_worksheet = MagicMock()
    mock_gspread_client.open_by_key.return_value = mock_spreadsheet
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_cell = MagicMock()
    mock_cell.row = 10
    mock_worksheet.findall.return_value = [mock_cell]
    mock_worksheet.delete_rows.side_effect = _FakeAPIError(504)

    mock_time = MagicMock()
    with patch('src.shared.integrations.google_drive_service.APIError', _FakeAPIError), \
         patch('src.shared.integrations.google_drive_service.time', mock_time):
        result = service.delete_rows_by_key("sheet_id", "Sales Order", "N-6881", key_column_index=0)

    assert result is False
    assert mock_worksheet.delete_rows.call_count == 1
    mock_time.sleep.assert_not_called()


def test_execute_with_retry_backs_off_exponentially(retry_service):
    """Each retry waits longer than the last, capped at max_backoff."""
    service, mock_sleep = retry_service
    service.max_retries = 5
    service.initial_backoff = 1.0
    service.max_backoff = 4.0
    func = MagicMock(side_effect=[_FakeAPIError(503)] * 4 + ["ok"])

    assert service._execute_with_retry(func) == "ok"

    # jitter adds [0, 1) to each backoff of 1, 2, 4, 4
    waits = [call.args[0] for call in mock_sleep.call_args_list]
    assert len(waits) == 4
    for wait, expected in zip(waits, [1.0, 2.0, 4.0, 4.0]):
        assert expected <= wait < expected + 1
