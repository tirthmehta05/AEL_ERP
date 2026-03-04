
import pytest
from unittest.mock import MagicMock, patch, ANY
import pandas as pd
import json

# Ensure strict import order to avoid circular dependency issues
import src.slitting_plan.service.slitting_plan_service
from src.pdf_generator.service.pdf_service import PDFService

@pytest.fixture
def pdf_service():
    """Pytest fixture to provide a PDFService instance with mocked dependencies."""
    # Patch the internal services instantiated in __init__
    with patch('src.pdf_generator.service.pdf_service.WeightReceiptService', MagicMock()), \
         patch('src.pdf_generator.service.pdf_service.SlittingPlanService', MagicMock()):
        
        mock_so_service = MagicMock()
        service = PDFService(sales_order_service=mock_so_service)
        return service

def test_delivery_challan_shows_sets_in_description(pdf_service):
    """Verify that Delivery Challan PDF appends '(X sets)' to description when sets are present."""
    # Mock Data
    data = {
        'challan_details': {
            'from_company': {'name': 'Test Co', 'address': '123 St'},
            'to_customer': 'Test Cust',
            'challan_no': 'DC-001',
            'vehicle_no': 'MH-01'
        },
        'items': [{
            'job_no': 'J1',
            'po_no': 'P1',
            'line_items': [
                {
                    'description': 'Test Material 100x100', 
                    'sets': 5, 
                    'remark': 'Test Remark', 
                    'weight': 500.0,
                    'deduction': 0.0,
                    'net_weight': 500.0
                }
            ],
            'summary': {
                'material': 'Total', 
                'sets': 5, 
                'total_weight': 500.0,
                'total_deduction': 0.0,
                'net_total_weight': 500.0
            }
        }],
        'grand_total_weight': 500.0,
        'receipts': pd.DataFrame()
    }
    
    mock_pdf = MagicMock()
    # Configure mock dimensions for comparisons
    mock_pdf.get_y.return_value = 50.0
    mock_pdf.h = 297.0
    mock_pdf.w = 210.0
    mock_pdf.l_margin = 10.0
    mock_pdf.r_margin = 10.0
    mock_pdf.t_margin = 10.0
    mock_pdf.b_margin = 10.0
    
    # Mock FPDF to capture calls
    with patch('src.pdf_generator.service.pdf_service.FPDF', return_value=mock_pdf):
        pdf_service.generate_delivery_challan_pdf(data)
        
    # Check for Description with sets
    # We expect a cell call containing "Test Material 100x100 (5 sets)"
    found_desc_with_sets = False
    for call_args in mock_pdf.cell.call_args_list:
        args, _ = call_args
        if len(args) >= 3 and isinstance(args[2], str):
            content = args[2]
            if "Test Material 100x100 (5 sets)" in content:
                found_desc_with_sets = True
                break
    
    assert found_desc_with_sets, "Delivery Challan should display item description with '(5 sets)' appended"

def test_delivery_challan_summary_sets_display(pdf_service):
    """Verify that Delivery Challan Summary shows 'Set : X' only when > 0."""
    # Case 1: Sets > 0
    data_positive = {
        'challan_details': {'from_company': {'name': 'A', 'address': 'B'}, 'to_customer': 'C'},
        'items': [{
            'line_items': [{'description': 'D', 'sets': 0, 'remark': '', 'weight': 0}], 
            'summary': {'material': 'M', 'sets': 10, 'total_weight': 0}
        }],
        'grand_total_weight': 0, 'receipts': pd.DataFrame()
    }
    
    mock_pdf = MagicMock()
    mock_pdf.get_y.return_value = 50.0
    mock_pdf.h = 297.0
    mock_pdf.w = 210.0
    mock_pdf.l_margin = 10.0
    mock_pdf.r_margin = 10.0
    mock_pdf.t_margin = 10.0
    mock_pdf.b_margin = 10.0

    with patch('src.pdf_generator.service.pdf_service.FPDF', return_value=mock_pdf):
        pdf_service.generate_delivery_challan_pdf(data_positive)
    
    # Verify "Set : 10" is printed
    found_set_10 = False
    for call_args in mock_pdf.cell.call_args_list:
        args, _ = call_args
        if len(args) >= 3 and isinstance(args[2], str) and "Set : 10" in args[2]:
            found_set_10 = True
            break
    assert found_set_10, "Summary should display 'Set : 10'"

    # Case 2: Sets = 0 (e.g. Loose Strips itemized without global count)
    data_zero = {
        'challan_details': {'from_company': {'name': 'A', 'address': 'B'}, 'to_customer': 'C'},
        'items': [{
            'line_items': [{'description': 'D', 'sets': 0, 'remark': '', 'weight': 0}], 
            'summary': {'material': 'M', 'sets': 0, 'total_weight': 0}
        }],
        'grand_total_weight': 0, 'receipts': pd.DataFrame()
    }
    
    mock_pdf.reset_mock()
    # Ensure properties persist after reset if needed (MagicMock reset doesn't clear attributes usually, but safe to re-set if needed. 
    # Actually attributes set on instance persist. But reset_mock clears call history)
    
    with patch('src.pdf_generator.service.pdf_service.FPDF', return_value=mock_pdf):
        pdf_service.generate_delivery_challan_pdf(data_zero)
        
    # Verify "Set : 0" is NOT printed (should be empty string or just " ")
    found_set_0 = False
    for call_args in mock_pdf.cell.call_args_list:
        args, _ = call_args
        if len(args) >= 3 and isinstance(args[2], str) and "Set : 0" in args[2]:
            found_set_0 = True
            break
    assert not found_set_0, "Summary should NOT display 'Set : 0' when sets is 0"

def test_weight_receipt_shows_itemized_sets(pdf_service):
    """Verify that Weight Receipt PDF shows sets in item description for itemized mode."""
    # Mock Data
    receipt_data = {
        'WeightReceiptNumber': 'WR-001',
        'PartyName': 'Test Party',
        'WeightEntryType': 'Loose Strips', # Itemized
        'DesignDetailsWithWeightsJSON': json.dumps([
            {
                'width': 100, 'length': 200, 'mm_stack': 50, 
                'sets': 3, # Itemized sets
                'remark': 'Rem', 'actual_weight': 10.0
            }
        ])
    }
    
    mock_pdf = MagicMock()
    # Mock the internal logic of _draw_weight_receipt as called by public method? 
    # Or test _draw_weight_receipt distinct? It's "private" but testable.
    
    # We'll use PDFService._draw_weight_receipt
    
    pdf_service._draw_weight_receipt(mock_pdf, receipt_data)
    
    # Verify description call
    # Logic in code:
    # description = "100 X 200 X 50"
    # if item.get('sets'): description += " (3 sets)"
    # pdf.cell(..., description, ...) OR multi_cell if remark
    
    expected_text = "100 X 200 X 50 (3 sets)"
    
    found_text = False
    # Check both cell and multi_cell calls
    all_calls = mock_pdf.cell.call_args_list + mock_pdf.multi_cell.call_args_list
    
    for call_args in all_calls:
        args, _ = call_args
        # Generally args[2] is text in cell(w, h, txt)
        # But if using keywords...
        # Let's inspect all sting args
        for arg in args:
            if isinstance(arg, str) and expected_text in arg:
                found_text = True
                break
        if found_text: break
            
    assert found_text, f"Weight Receipt should display '{expected_text}'"
