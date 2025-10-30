import pytest
from unittest.mock import MagicMock, patch
import pandas as pd

# Patch dependencies before importing the service
with patch('src.slitting_plan.repository.slitting_plan_repository.SlittingPlanRepository', MagicMock()), \
     patch('src.data_entry.service.rm_used_service.RMUsedService', MagicMock()):
    from src.slitting_plan.service.slitting_plan_service import SlittingPlanService

@pytest.fixture
def slitting_plan_service():
    """Pytest fixture to provide a SlittingPlanService instance with mocked dependencies."""
    service = SlittingPlanService()
    return service

def test_calculate_slitting_plan_success(slitting_plan_service):
    """Test the successful calculation of a slitting plan."""
    # --- Arrange ---
    selected_coils_data = {
        'Coil Number': ['COIL001'],
        'width': [1000],
        'available_weight': [5000]
    }
    selected_coils_df = pd.DataFrame(selected_coils_data)

    edited_df_data = {
        'Size': [200, 300],
        'No. of Slits': [2, 1]
    }
    edited_df = pd.DataFrame(edited_df_data)

    # --- Act ---
    result = slitting_plan_service.calculate_slitting_plan(selected_coils_df, edited_df)

    # --- Assert ---
    assert len(result['errors']) == 0
    
    summary = result['summary']
    assert summary['total_slits'] == 3
    assert summary['total_mm_used'] == 700
    assert summary['scrap_per_coil_mm'] == 300
    assert pytest.approx(summary['total_weight_kg'], 0.01) == 3500
    assert pytest.approx(summary['scrap_weight_kg'], 0.01) == 1500

    calculated_plan_df = result['calculated_plan']
    assert 'Weight in Kg' in calculated_plan_df.columns
    assert pytest.approx(calculated_plan_df.loc[0, 'Weight in Kg'], 0.01) == 2000
    assert pytest.approx(calculated_plan_df.loc[1, 'Weight in Kg'], 0.01) == 1500

def test_calculate_slitting_plan_slit_too_wide(slitting_plan_service):
    """Test validation error when a slit size is wider than the coil."""
    # --- Arrange ---
    selected_coils_data = {'width': [1000], 'available_weight': [1000]}
    selected_coils_df = pd.DataFrame(selected_coils_data)

    edited_df_data = {'Size': [1200], 'No. of Slits': [1]}
    edited_df = pd.DataFrame(edited_df_data)

    # --- Act ---
    result = slitting_plan_service.calculate_slitting_plan(selected_coils_df, edited_df)

    # --- Assert ---
    assert "Error: Requested slit size of 1200.0mm is wider than the selected coil width (1000)." in result['errors']

def test_calculate_slitting_plan_total_width_exceeded(slitting_plan_service):
    """Test validation error when total slit width exceeds coil width."""
    # --- Arrange ---
    selected_coils_data = {'width': [1000], 'available_weight': [5000]}
    selected_coils_df = pd.DataFrame(selected_coils_data)

    edited_df_data = {'Size': [500, 600], 'No. of Slits': [1, 1]}
    edited_df = pd.DataFrame(edited_df_data)

    # --- Act ---
    result = slitting_plan_service.calculate_slitting_plan(selected_coils_df, edited_df)

    # --- Assert ---
    assert "Error: Total planned width (1100.0mm) exceeds the width of a single coil (1000)." in result['errors']
