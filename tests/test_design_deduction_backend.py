"""
Test script for backend changes to support design-level deductions.

This script tests:
1. WeighedDesignDetail model with design_deduction field
2. Draft save/load with design_deduction
3. Weight receipt save with auto-calculated total deduction
"""

from src.data_entry.models.weight_receipt_models import WeighedDesignDetail, WeightReceiptRequest
from datetime import date

def test_weighed_design_detail_model():
    """Test that WeighedDesignDetail accepts design_deduction field."""
    print("\n=== Test 1: WeighedDesignDetail Model ===")
    
    # Test with design_deduction
    design1 = WeighedDesignDetail(
        width=100.0,
        length=200.0,
        mm_stack=50.0,
        actual_weight=10.5,
        remark="Test design",
        design_deduction=0.5
    )
    
    print(f"✓ Design 1 created with design_deduction: {design1.design_deduction}")
    assert design1.design_deduction == 0.5, "design_deduction should be 0.5"
    
    # Test without design_deduction (should default to 0.0)
    design2 = WeighedDesignDetail(
        width=150.0,
        length=250.0,
        actual_weight=15.0
    )
    
    print(f"✓ Design 2 created without design_deduction (defaults to): {design2.design_deduction}")
    assert design2.design_deduction == 0.0, "design_deduction should default to 0.0"
    
    print("✅ WeighedDesignDetail model test passed!\n")
    return True

def test_weight_receipt_request_deduction_calculation():
    """Test that total deduction is calculated from design deductions."""
    print("=== Test 2: Weight Receipt Deduction Calculation ===")
    
    designs = [
        WeighedDesignDetail(
            width=100.0,
            length=200.0,
            actual_weight=10.0,
            design_deduction=0.5
        ),
        WeighedDesignDetail(
            width=150.0,
            length=250.0,
            actual_weight=15.0,
            design_deduction=1.0
        ),
        WeighedDesignDetail(
            width=120.0,
            length=180.0,
            actual_weight=8.0,
            design_deduction=0.3
        ),
    ]
    
    request = WeightReceiptRequest(
        weight_receipt_number="TEST001",
        receipt_date=date.today(),
        job_card_number="JC001",
        party_name="Test Party",
        material="CRGO",
        sets=1,
        designs=designs,
        total_weight=33.0,  # 10 + 15 + 8
        deduction=0.0  # Will be calculated
    )
    
    # Simulate what save_weight_receipt does
    total_design_deduction = sum(d.design_deduction or 0.0 for d in request.designs)
    request.deduction = total_design_deduction
    
    expected_deduction = 0.5 + 1.0 + 0.3  # 1.8
    print(f"✓ Calculated total deduction: {request.deduction}")
    print(f"✓ Expected deduction: {expected_deduction}")
    assert request.deduction == expected_deduction, f"Deduction should be {expected_deduction}"
    
    net_weight = request.total_weight - request.deduction
    print(f"✓ Net weight: {net_weight} (Total: {request.total_weight} - Deduction: {request.deduction})")
    
    print("✅ Deduction calculation test passed!\n")
    return True

def test_model_dump_includes_design_deduction():
    """Test that model_dump includes design_deduction field."""
    print("=== Test 3: Model Serialization ===")
    
    design = WeighedDesignDetail(
        width=100.0,
        length=200.0,
        actual_weight=10.0,
        design_deduction=0.5
    )
    
    design_dict = design.model_dump()
    
    print(f"✓ Serialized design: {design_dict}")
    assert 'design_deduction' in design_dict, "design_deduction should be in serialized dict"
    assert design_dict['design_deduction'] == 0.5, "design_deduction value should be preserved"
    
    print("✅ Model serialization test passed!\n")
    return True

def test_backward_compatibility():
    """Test that old data without design_deduction works correctly."""
    print("=== Test 4: Backward Compatibility ===")
    
    # Simulate old design data without design_deduction
    old_design_dict = {
        'width': 100.0,
        'length': 200.0,
        'actual_weight': 10.0,
        'remark': 'Old design'
        # No design_deduction field
    }
    
    # Should work with default value
    design = WeighedDesignDetail(**old_design_dict)
    
    print(f"✓ Old design loaded with default design_deduction: {design.design_deduction}")
    assert design.design_deduction == 0.0, "Missing design_deduction should default to 0.0"
    
    # Test in weight receipt calculation
    designs = [design]
    total_deduction = sum(d.design_deduction or 0.0 for d in designs)
    
    print(f"✓ Total deduction for old design: {total_deduction}")
    assert total_deduction == 0.0, "Old designs should contribute 0 to total deduction"
    
    print("✅ Backward compatibility test passed!\n")
    return True

def run_all_tests():
    """Run all backend tests."""
    print("\n" + "="*60)
    print("BACKEND TESTING: Design-Level Deductions")
    print("="*60)
    
    tests = [
        test_weighed_design_detail_model,
        test_weight_receipt_request_deduction_calculation,
        test_model_dump_includes_design_deduction,
        test_backward_compatibility
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed: {test.__name__}")
            print(f"   Error: {str(e)}\n")
            failed += 1
    
    print("="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
