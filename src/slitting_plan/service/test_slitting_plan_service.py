import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime, date
import json

# Import the service dynamically within the fixture

@pytest.fixture
def slitting_service():
    """Pytest fixture that provides a SlittingPlanService with a mocked google_drive_service."""
    # Patch the global `google_drive_service` object within the slitting_plan_service module
    with patch('src.slitting_plan.service.slitting_plan_service.google_drive_service') as mock_gdrive_service, \
         patch('config.settings', MagicMock()):
        from src.slitting_plan.service.slitting_plan_service import SlittingPlanService
        service = SlittingPlanService()
        # The instance now holds a reference to our mock
        yield service

def test_get_available_coils(slitting_service):
    """Test the logic for calculating available coil weight."""
    inward_df = pd.DataFrame({
        'Coil Number': ['C1', 'C2'], 'Coil Weight': [1000, 2000],
        'Grade': ['A', 'B'], 'Thk': [0.5, 0.6], 'Width': [1000, 1200],
        'Coating': ['C1', 'C2'], 'Coil Location': ['L1', 'L2'], 'Coil Supplier': ['S1', 'S2']
    })
    used_df = pd.DataFrame({'Coil No': ['C1'], 'Weight': [300]})
    slitting_service.google_service.get_worksheet_data.side_effect = [inward_df, used_df]

    result_df = slitting_service.get_available_coils()

    assert len(result_df) == 2
    assert result_df[result_df['Coil Number'] == 'C1']['available_weight'].iloc[0] == 700
    assert result_df[result_df['Coil Number'] == 'C2']['available_weight'].iloc[0] == 2000

def test_get_next_plan_id(slitting_service):
    """Test the generation of the next sequential plan ID."""
    today_str = datetime.now().strftime("%y%m%d")
    prefix = f"SP-1250-{today_str}-"
    mock_df = pd.DataFrame({'PlanID': [f'{prefix}01', f'{prefix}02']})
    slitting_service.google_service.get_worksheet_data.return_value = mock_df

    next_id = slitting_service.get_next_plan_id(1250)
    assert next_id == f"{prefix}03"

def test_save_plan(slitting_service):
    """Test that save_plan calls the correct google service methods."""
    slitting_service.get_next_plan_id = MagicMock(return_value="SP-TEST-01")
    plan_data = {
        'coil_width': 1250, 'total_coil_weight': 5000, 'scrap_mm': 10, 'scrap_weight': 50,
        'selected_coils': [{'Coil Number': 'C1'}], 'slit_details': [{'Size': 500}]
    }

    result_id = slitting_service.save_plan(plan_data)

    assert result_id == "SP-TEST-01"
    slitting_service.google_service.ensure_worksheet_with_headers.assert_called_once()
    slitting_service.google_service.append_data.assert_called_once()

def test_get_printable_plans(slitting_service):
    """Test that it correctly filters for printable plans."""
    mock_df = pd.DataFrame({'PlanID': ['P1', 'P2', 'P3'], 'Status': ['Created', 'In Process', 'Completed']})
    slitting_service.google_service.get_worksheet_data.return_value = mock_df

    result = slitting_service.get_printable_plans()
    assert len(result) == 2
    assert "P3" not in result

def test_get_saved_plan_details(slitting_service):
    """Test that it correctly parses a saved plan from a dataframe row."""
    raw_materials = [{'Coil Number': 'C1'}]
    slit_details = [{'Size': 500}]
    mock_df = pd.DataFrame({
        'PlanID': ['P1'], 'Date': ['2025-10-28'], 'Status': ['Created'],
        'CoilWidth': [1250], 'TotalCoilWeight': [5000], 'ScrapMM': [10], 'ScrapWeight': [50],
        'RawMaterialsJSON': [json.dumps(raw_materials)], 'SlitDetailsJSON': [json.dumps(slit_details)]
    })
    slitting_service.google_service.get_worksheet_data.return_value = mock_df

    result = slitting_service.get_saved_plan_details('P1')

    assert result['plan_id'] == 'P1'
    assert result['raw_materials'][0]['Coil Number'] == 'C1'

def test_update_plan_status(slitting_service):
    """Test that the status of a plan is updated correctly."""
    mock_worksheet = MagicMock()
    mock_cell = MagicMock()
    mock_cell.row = 5
    slitting_service.google_service.client.open_by_key.return_value.worksheet.return_value = mock_worksheet
    mock_worksheet.find.return_value = mock_cell

    result = slitting_service.update_plan_status('P1', 'In Process')

    mock_worksheet.find.assert_called_with('P1', in_column=1)
    mock_worksheet.update_cell.assert_called_with(5, 3, 'In Process')
    assert result is True