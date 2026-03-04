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
