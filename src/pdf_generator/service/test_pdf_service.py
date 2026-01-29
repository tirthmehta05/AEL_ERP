import pytest
from unittest.mock import MagicMock, patch, call
import pandas as pd

# Ensure submodule is loaded for patch to work
import src.slitting_plan.service.slitting_plan_service

# Patch the services that PDFService depends on before importing it
with patch('src.slitting_plan.service.slitting_plan_service.SlittingPlanService', MagicMock()) as mock_slitting_service:
    from src.pdf_generator.service.pdf_service import PDFService

@pytest.fixture
def pdf_service():
    """Pytest fixture to provide a PDFService instance with mocked dependencies."""
    with patch('src.pdf_generator.service.pdf_service.WeightReceiptService', MagicMock()):
        mock_so_service = MagicMock()
        service = PDFService(sales_order_service=mock_so_service)
        # The slitting_service is already mocked by the patch at the top level
        # We can re-assign it here if we need to control it per test
        service.slitting_service = MagicMock()
        return service

def test_get_available_coils_for_sticker(pdf_service):
    """Test that the service correctly calls the slitting service to get coils."""
    pdf_service.get_available_coils_for_sticker()
    pdf_service.slitting_service.get_available_coils_by_date.assert_called_once()

@patch('src.pdf_generator.service.pdf_service.FPDF')
@patch('src.pdf_generator.service.pdf_service.qrcode')
def test_generate_sticker_pdf_layout(mock_qrcode, mock_fpdf, pdf_service):
    """Test the layout logic for sticker generation (pages, grid)."""
    mock_pdf_instance = MagicMock()
    mock_fpdf.return_value = mock_pdf_instance
    
    # Test with 11 coils, which should result in 2 pages
    selected_coils = pd.DataFrame([{'Coil Number': f'C{i}'} for i in range(11)])
    
    # Mock the internal draw method so we only test the layout logic
    pdf_service._draw_sticker = MagicMock()

    pdf_service.generate_sticker_pdf(selected_coils)

    # Should be called once at the start. 11 stickers fit on 1 page (limit is 12)
    assert mock_pdf_instance.add_page.call_count == 1
    # Should be called once for each of the 11 coils
    assert pdf_service._draw_sticker.call_count == 11

@patch('src.pdf_generator.service.pdf_service.FPDF')
def test_generate_slitting_plan_pdf_structure(mock_fpdf, pdf_service):
    """Test that the main structural elements of the slitting plan PDF are drawn."""
    mock_pdf_instance = MagicMock()
    mock_fpdf.return_value = mock_pdf_instance

    plan_data = {
        'plan_id': 'SP-1000-251028-01',
        'date': '2025-10-28',
        'raw_materials': [
            {'Coil Number': 'C1', 'grade': 'G1', 'thickness': 0.5, 'available_weight': 1000}
        ],
        'slit_details': [
            {'Size': 100, 'No. of Slits': 2, 'Weight in Kg': 200}
        ],
        'coil_width': 1000,
        'scrap_mm': 10,
        'scrap_weight': 100,
        'total_coil_weight': 1000
    }

    pdf_service.generate_slitting_plan_pdf(plan_data)

    # Check that the main title and headers are being rendered
    # We can check if `cell` was called with content containing these strings
    # This is a bit more advanced, but we can check the call list
    # For simplicity, we'll just check if it was called a reasonable number of times
    assert mock_pdf_instance.set_font.call_count > 5
    assert mock_pdf_instance.cell.call_count > 10


    # Check that it tried to render the plan number
    # The ANY captures the other arguments to the call
    mock_pdf_instance.cell.assert_any_call(0, 8, f"Plan No: {plan_data['plan_id']}", ln=True, align='L')
    # Check a raw material cell
    mock_pdf_instance.cell.assert_any_call(60, 8, 'C1', border=1)
    # Check a slit detail cell
    mock_pdf_instance.cell.assert_any_call(40, 8, '100.0', border=1, align='C')
