import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import gspread

# We have to patch the settings before importing the service
with patch('config.settings', MagicMock()):
    from src.shared.integrations.google_drive_service import GoogleDriveService

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
    """Service with a real APIError class patched in and sleep neutered."""
    service, _ = mocked_service
    service.max_retries = 3
    service.initial_backoff = 0.0
    with patch('src.shared.integrations.google_drive_service.APIError', _FakeAPIError), \
         patch('src.shared.integrations.google_drive_service.time.sleep') as mock_sleep:
        yield service, mock_sleep


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

    with pytest.raises(_FakeAPIError):
        service._execute_with_retry(func)

    assert func.call_count == service.max_retries


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
