import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import date
from src.data_entry.service.weight_receipt_service import WeightReceiptService

@pytest.fixture
def weight_receipt_service():
    """Fixture to create an instance of WeightReceiptService."""
    with patch('config.settings', MagicMock()):
         # Mock the repository to avoid actual Google Sheet calls
        with patch('src.data_entry.repository.weight_receipt_repository.WeightReceiptRepository') as mock_repo:
            service = WeightReceiptService()
            service.repository = mock_repo.return_value
            yield service

def test_get_weight_receipts_for_party_and_date_range_case_insensitive(weight_receipt_service):
    """
    Tests that get_weight_receipts_for_party_and_date_range correctly filters by party name
    in a case-insensitive manner and handles whitespace.
    """
    # 1. Arrange: Create mock data
    mock_data = {
        'Date': ['01/01/2024', '02/01/2024', '03/01/2024', '04/01/2024'],
        'PartyName': ['Test Party', 'test party', ' Test Party ', 'Another Party'],
        'WeightReceiptNumber': [1, 2, 3, 4],
        'JobCardNumber': ['JC1', 'JC2', 'JC3', 'JC4']
    }
    mock_df = pd.DataFrame(mock_data)

    # Configure the mock repository to return the mock DataFrame
    weight_receipt_service.repository.get_all_weight_receipts.return_value = mock_df

    # 2. Act: Call the function with a specific party name and date range
    party_name_to_filter = "test party"
    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 5)
    
    results = weight_receipt_service.get_weight_receipts_for_party_and_date_range(
        party_name=party_name_to_filter,
        start_date=start_date,
        end_date=end_date
    )

    # 3. Assert: Check the results
    # It should find the 3 variations of "Test Party"
    assert len(results) == 3
    
    # Check that the party names from the results, when normalized, match the filter
    for record in results:
        assert record['PartyName'].strip().lower() == party_name_to_filter

    # Check that 'Another Party' was not included
    party_names_in_results = [r['PartyName'] for r in results]
    assert 'Another Party' not in party_names_in_results

def test_get_weight_receipts_for_party_date_range_no_match(weight_receipt_service):
    """
    Tests that the function returns an empty list when no party matches.
    """
    # 1. Arrange
    mock_data = {
        'Date': ['01/01/2024'],
        'PartyName': ['Some Other Party'],
        'WeightReceiptNumber': [1],
        'JobCardNumber': ['JC1']
    }
    mock_df = pd.DataFrame(mock_data)
    weight_receipt_service.repository.get_all_weight_receipts.return_value = mock_df

    # 2. Act
    results = weight_receipt_service.get_weight_receipts_for_party_and_date_range(
        party_name="NonExistent Party",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5)
    )

    # 3. Assert
    assert len(results) == 0


# --- Tests for clear_drafts_for_design_indices ---

@pytest.fixture
def wr_service_with_google_mock():
    """Fixture with both repository and google_service mocked."""
    with patch('config.settings', MagicMock()):
        with patch('src.data_entry.repository.weight_receipt_repository.WeightReceiptRepository') as mock_repo:
            with patch('src.data_entry.service.weight_receipt_service.google_drive_service') as mock_google:
                service = WeightReceiptService()
                service.repository = mock_repo.return_value
                service.google_service = mock_google
                yield service


def test_clear_drafts_for_design_indices_selective(wr_service_with_google_mock):
    """
    Clearing specific design indices should only remove those rows,
    preserving drafts for other designs of the same job card.
    """
    service = wr_service_with_google_mock

    mock_draft_data = pd.DataFrame({
        'JobCardNumber': ['JC-001', 'JC-001', 'JC-001'],
        'DesignIndex': [0, 1, 2],
        'ActualWeight': [10.5, 20.3, 15.0],
        'Timestamp': ['2024-01-01T10:00:00', '2024-01-01T10:01:00', '2024-01-01T10:02:00'],
        'ReceiptSets': [1, 1, 1],
        'Remark': ['', 'test', ''],
        'DesignDeduction': [0.0, 0.5, 0.0]
    })
    service.google_service.get_worksheet_data.return_value = mock_draft_data

    mock_worksheet = MagicMock()
    service.google_service.client.open_by_key.return_value.worksheet.return_value = mock_worksheet

    # Clear only designs 0 and 2, keep design 1
    result = service.clear_drafts_for_design_indices('JC-001', [0, 2])

    assert result is True
    mock_worksheet.clear.assert_called_once()

    # Verify that the written data only contains the row for design index 1
    written_data = mock_worksheet.update.call_args[0][0]
    # First row is headers, second row is the preserved data
    assert len(written_data) == 2  # headers + 1 remaining row
    data_row = written_data[1]
    assert data_row[0] == 'JC-001'
    assert data_row[1] == 1  # Design index 1 preserved


def test_clear_drafts_for_design_indices_empty_sheet(wr_service_with_google_mock):
    """Clearing from an empty sheet should succeed without errors."""
    service = wr_service_with_google_mock
    service.google_service.get_worksheet_data.return_value = pd.DataFrame()

    result = service.clear_drafts_for_design_indices('JC-001', [0, 1])

    assert result is True
    # Should not attempt to write anything
    service.google_service.client.open_by_key.assert_not_called()


def test_clear_drafts_for_design_indices_preserves_other_jc(wr_service_with_google_mock):
    """
    Clearing designs for one JC should not affect drafts
    belonging to a different JC.
    """
    service = wr_service_with_google_mock

    mock_draft_data = pd.DataFrame({
        'JobCardNumber': ['JC-001', 'JC-001', 'JC-002'],
        'DesignIndex': [0, 1, 0],
        'ActualWeight': [10.0, 20.0, 30.0],
        'Timestamp': ['2024-01-01T10:00:00', '2024-01-01T10:01:00', '2024-01-01T10:02:00'],
        'ReceiptSets': [1, 1, 2],
        'Remark': ['', '', ''],
        'DesignDeduction': [0.0, 0.0, 0.0]
    })
    service.google_service.get_worksheet_data.return_value = mock_draft_data

    mock_worksheet = MagicMock()
    service.google_service.client.open_by_key.return_value.worksheet.return_value = mock_worksheet

    # Clear all designs for JC-001
    result = service.clear_drafts_for_design_indices('JC-001', [0, 1])

    assert result is True
    written_data = mock_worksheet.update.call_args[0][0]
    # headers + 1 remaining row (JC-002, design 0)
    assert len(written_data) == 2
    data_row = written_data[1]
    assert data_row[0] == 'JC-002'


def test_clear_drafts_for_design_indices_no_matching_indices(wr_service_with_google_mock):
    """
    If the specified indices don't exist in the sheet, all rows should
    be preserved unchanged.
    """
    service = wr_service_with_google_mock

    mock_draft_data = pd.DataFrame({
        'JobCardNumber': ['JC-001'],
        'DesignIndex': [0],
        'ActualWeight': [10.0],
        'Timestamp': ['2024-01-01T10:00:00'],
        'ReceiptSets': [1],
        'Remark': [''],
        'DesignDeduction': [0.0]
    })
    service.google_service.get_worksheet_data.return_value = mock_draft_data

    mock_worksheet = MagicMock()
    service.google_service.client.open_by_key.return_value.worksheet.return_value = mock_worksheet

    # Try to clear design index 5 which doesn't exist
    result = service.clear_drafts_for_design_indices('JC-001', [5])

    assert result is True
    written_data = mock_worksheet.update.call_args[0][0]
    # headers + 1 original row (unchanged)
    assert len(written_data) == 2


# --- Tests for get_next_weight_receipt_number ---
# Regression guard for incident 2026-05-16: a Google Sheets 429 read-quota
# error returned an empty DataFrame, the old code read that as "empty sheet",
# and a Weight Receipt was saved as the seed 10315 instead of 10957.

def test_next_number_is_max_plus_one(weight_receipt_service):
    """Normal case: next number is (max existing numeric number) + 1."""
    df = pd.DataFrame({'WeightReceiptNumber': ['10955', '10956']})
    weight_receipt_service.repository.get_all_weight_receipts.return_value = df

    assert weight_receipt_service.get_next_weight_receipt_number() == 10957


def test_next_number_seed_on_genuinely_empty_sheet(weight_receipt_service):
    """A *successful* read that returns zero rows -> the 10315 seed is valid."""
    weight_receipt_service.repository.get_all_weight_receipts.return_value = pd.DataFrame()

    assert weight_receipt_service.get_next_weight_receipt_number() == 10315


def test_next_number_raises_on_read_failure_no_seed_fallback(weight_receipt_service):
    """
    The core fix: when the receipts sheet cannot be read, numbering must
    RAISE — it must NOT silently fall back to the seed 10315 (or a
    timestamp), because that writes a duplicate/regressed receipt number.
    """
    weight_receipt_service.repository.get_all_weight_receipts.side_effect = (
        Exception("APIError [429]: Quota exceeded for 'Read requests'")
    )

    with pytest.raises(Exception):
        weight_receipt_service.get_next_weight_receipt_number()


def test_next_number_uses_strict_read(weight_receipt_service):
    """
    Numbering must request a strict read (raise_on_error=True) so a failed
    read can never masquerade as an empty sheet.
    """
    df = pd.DataFrame({'WeightReceiptNumber': ['10956']})
    weight_receipt_service.repository.get_all_weight_receipts.return_value = df

    weight_receipt_service.get_next_weight_receipt_number()

    _, kwargs = weight_receipt_service.repository.get_all_weight_receipts.call_args
    assert kwargs.get('raise_on_error') is True
