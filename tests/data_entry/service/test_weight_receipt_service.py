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
