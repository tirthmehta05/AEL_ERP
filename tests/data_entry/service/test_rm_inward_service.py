import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, date

# Patch settings and google_drive_service before importing the service
with patch('config.settings', MagicMock()), \
     patch('src.shared.integrations.google_drive_service.google_drive_service', MagicMock()):
    from src.data_entry.service.rm_inward_service import RMInwardService
    from src.data_entry.models.rm_inward_models import RMInwardIssueRequest

@pytest.fixture
def inward_service():
    """Pytest fixture to provide an RMInwardService instance with a mocked GoogleDriveService."""
    service = RMInwardService()
    # The google_drive_service is already mocked by the patch at the top level
    return service

def test_generate_coil_number(inward_service):
    """Test that coil number generation contains the correct components."""
    grade = "CRNGO"
    coating = "C5"
    width = 1250
    coil_number = inward_service.generate_coil_number(grade, coating, width)
    assert coil_number.isdigit() # Assert it is a number series now, not logic based string


def test_get_next_coil_number_filters_by_location(inward_service):
    """Test that get_next_coil_number only considers coils with location 'AEL PUNE'."""
    # Mock the dataframe returned by _get_all_dropdown_data
    mock_df = pd.DataFrame({
        'Coil Number': ['12300', '12400', '12500'],
        'Location': ['AEL PUNE', 'OTHER LOC', 'ael pune '] # Mixed case and spacing
    })
    inward_service._get_all_dropdown_data = MagicMock(return_value=mock_df)
    
    # The max among 'AEL PUNE' is 12500, so next should be 12501
    next_coil = inward_service.get_next_coil_number()
    assert next_coil == 12501

def test_get_next_coil_number_no_location_column(inward_service):
    """Test that get_next_coil_number works if the Location column is missing."""
    mock_df = pd.DataFrame({
        'Coil Number': ['12300', '12400', '12500']
    })
    inward_service._get_all_dropdown_data = MagicMock(return_value=mock_df)
    
    # No Location column, so it considers all. Max is 12500, next is 12501
    next_coil = inward_service.get_next_coil_number()
    assert next_coil == 12501

def test_get_next_coil_number_default_base(inward_service):
    """Test that it returns 12180 if no valid numeric 'AEL PUNE' coils exist."""
    mock_df = pd.DataFrame({
        'Coil Number': ['INVALID', 'ABCD'],
        'Location': ['AEL PUNE', 'AEL PUNE']
    })
    inward_service._get_all_dropdown_data = MagicMock(return_value=mock_df)
    
    # Base is 12179, so next should be 12180
    next_coil = inward_service.get_next_coil_number()
    assert next_coil == 12180


def test_validate_single_entry_success(inward_service):
    """Test a successful validation of a single entry."""
    inward_service.is_coil_number_unique = MagicMock(return_value=True)
    form_data = {
        'receipt_date': datetime.now().date(), 'rm_type': 'HR', 'grade': 'A', 'thk': '1', 'width': '1000',
        'coating': 'None', 'supplier': 'JSW', 'coil_number': 'TEST001', 'coil_weight': 100,
        'slit_ready': 'Ready', 'rate': 55.5
    }
    errors = inward_service.validate_single_entry(form_data)
    assert not errors

    # Test with float width
    form_data_float_width = {
        'receipt_date': datetime.now().date(), 'rm_type': 'HR', 'grade': 'A', 'thk': '1', 'width': '1000.5',
        'coating': 'None', 'supplier': 'JSW', 'coil_number': 'TEST002', 'coil_weight': 100,
        'slit_ready': 'Ready', 'rate': 55.5
    }
    errors_float_width = inward_service.validate_single_entry(form_data_float_width)
    assert not errors_float_width

def test_validate_single_entry_fails_non_unique(inward_service):
    """Test that validation fails for a non-unique coil number."""
    inward_service.is_coil_number_unique = MagicMock(return_value=False)
    form_data = {
        'receipt_date': datetime.now().date(), 'rm_type': 'HR', 'grade': 'A', 'thk': '1', 'width': '1000',
        'coating': 'None', 'supplier': 'JSW', 'coil_number': 'TEST001', 'coil_weight': 100,
        'slit_ready': 'Ready', 'rate': 55.5
    }
    errors = inward_service.validate_single_entry(form_data)
    assert len(errors) == 1
    assert "already exists" in errors[0]

def test_group_df_by_key(inward_service):
    """Test that the dataframe grouping logic works correctly."""
    df = pd.DataFrame({
        'PackingListID': ['A', 'A', 'B'],
        'Weight': [100, 150, 200],
        'Grade': ['G1', 'G1', 'G2']
    })
    mapping = {'coil_weight': 'Weight', 'grade': 'Grade'}
    grouped_df = inward_service.group_df_by_key(df, 'PackingListID', mapping)
    
    assert len(grouped_df) == 2
    # Check that weight for group 'A' is summed (100 + 150)
    assert grouped_df[grouped_df['PackingListID'] == 'A']['Weight'].iloc[0] == 250
    # Check that grade for group 'A' is the first one
    assert grouped_df[grouped_df['PackingListID'] == 'A']['Grade'].iloc[0] == 'G1'

def test_process_bulk_upload_df(inward_service):
    """Test the main bulk upload processing logic."""
    df = pd.DataFrame({
        'Coil': ['C1', 'C2', 'C3'],
        'ReceiptDate': [date(2025, 10, 28), date(2025, 10, 28), date(2025, 10, 28)],
        'Type': ['HR', 'HR', 'HR'],
        'Grade': ['G1', 'G1', 'G2'],
        'Thk': [1.0, 1.0, 2.0],
        'Width': [1000, 1000, 1200],
        'Coat': ['C1', 'C1', 'C2'],
        'Weight': [100, 150, 200],
        'Supplier': ['S1', 'S1', 'S2'],
        'SR': ['Ready', 'Ready', 'Slit'],
        'R': [50.0, 50.0, 60.0]
    })
    mapping = {
        'coil_number': 'Coil', 'rm_receipt_date': 'ReceiptDate', 'rm_type': 'Type',
        'grade': 'Grade', 'thk': 'Thk', 'width': 'Width', 'coating': 'Coat',
        'coil_weight': 'Weight', 'coil_supplier': 'Supplier',
        'slit_ready': 'SR', 'rate': 'R'
    }
    options = {"user_email": "test@test.com", "auto_generate_coil": False, "group_by_col": None}
    existing_coils = {'c0'}

    valid, failed = inward_service.process_bulk_upload_df(df, mapping, options, existing_coils)

    assert len(valid) == 3
    assert len(failed) == 0
    assert isinstance(valid[0], RMInwardIssueRequest)
    assert valid[0].coil_number == 'C1'
    assert valid[0].slit_ready == 'Ready'
    assert valid[0].rate == 50.0

def test_process_bulk_upload_df_with_failures(inward_service):
    """Test bulk processing with a duplicate coil number."""
    df = pd.DataFrame({
        'Coil': ['C1', 'C2', 'C1'], # C1 is duplicated
        'ReceiptDate': [date(2025, 10, 28), date(2025, 10, 28), date(2025, 10, 28)],
        'Type': ['HR', 'HR', 'HR'], 'Grade': ['G1', 'G1', 'G1'], 'Thk': [1.0, 1.0, 1.0],
        'Width': [1000, 1000, 1000], 'Coat': ['C1', 'C1', 'C1'], 'Weight': [100, 150, 200],
        'Supplier': ['S1', 'S1', 'S1'],
        'SR': ['Ready', 'Ready', 'Ready'],
        'R': [50.0, 50.0, 50.0]
    })
    mapping = {
        'coil_number': 'Coil', 'rm_receipt_date': 'ReceiptDate', 'rm_type': 'Type',
        'grade': 'Grade', 'thk': 'Thk', 'width': 'Width', 'coating': 'Coat',
        'coil_weight': 'Weight', 'coil_supplier': 'Supplier',
        'slit_ready': 'SR', 'rate': 'R'
    }
    options = {"user_email": "test@test.com", "auto_generate_coil": False, "group_by_col": None}
    existing_coils = set()

    valid, failed = inward_service.process_bulk_upload_df(df, mapping, options, existing_coils)

    assert len(valid) == 2
    assert len(failed) == 1
    assert failed[0]['Coil Number'] == 'C1'
    assert "already exists" in failed[0]['Error']