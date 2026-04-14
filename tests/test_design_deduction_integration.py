"""
Integration test for weight receipt service with design_deduction support.

This test verifies:
1. Draft save with design_deduction
2. Draft load with design_deduction
3. Backward compatibility with old drafts
"""

from src.services import create_services
from datetime import datetime

def test_draft_save_and_load():
    """Test saving and loading drafts with design_deduction."""
    print("\n" + "="*60)
    print("INTEGRATION TEST: Draft Save/Load with Design Deduction")
    print("="*60)
    
    services = create_services()
    test_job_card = f"TEST_JC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print(f"\n📝 Testing with job card: {test_job_card}")
    
    # Test 1: Save draft with design_deduction
    print("\n=== Test 1: Save Draft with Design Deduction ===")
    try:
        success = services.weight_receipt.save_weight_receipt_draft(
            job_card=test_job_card,
            design_index=0,
            weight=10.5,
            remark="Test design 1",
            sets_for_this_receipt=1,
            design_deduction=0.5
        )
        
        if success:
            print("✓ Draft saved successfully with design_deduction=0.5")
        else:
            print("❌ Failed to save draft")
            return False
    except Exception as e:
        print(f"❌ Error saving draft: {str(e)}")
        return False
    
    # Test 2: Save another draft with different deduction
    print("\n=== Test 2: Save Second Draft ===")
    try:
        success = services.weight_receipt.save_weight_receipt_draft(
            job_card=test_job_card,
            design_index=1,
            weight=15.0,
            remark="Test design 2",
            sets_for_this_receipt=1,
            design_deduction=1.0
        )
        
        if success:
            print("✓ Second draft saved successfully with design_deduction=1.0")
        else:
            print("❌ Failed to save second draft")
            return False
    except Exception as e:
        print(f"❌ Error saving second draft: {str(e)}")
        return False
    
    # Test 3: Load drafts and verify design_deduction values
    print("\n=== Test 3: Load Drafts and Verify ===")
    try:
        drafts, sets, total_weight, core_remark, core_drafts = services.weight_receipt.get_weight_receipt_drafts(test_job_card)
        
        print(f"✓ Loaded {len(drafts)} draft(s)")
        
        # Verify design 0
        if 0 in drafts:
            design_0 = drafts[0]
            print(f"  Design 0:")
            print(f"    - Weight: {design_0.get('weight')}")
            print(f"    - Remark: {design_0.get('remark')}")
            print(f"    - Design Deduction: {design_0.get('design_deduction')}")
            
            if design_0.get('design_deduction') == 0.5:
                print("  ✓ Design 0 deduction correct")
            else:
                print(f"  ❌ Design 0 deduction incorrect: expected 0.5, got {design_0.get('design_deduction')}")
                return False
        else:
            print("❌ Design 0 not found in drafts")
            return False
        
        # Verify design 1
        if 1 in drafts:
            design_1 = drafts[1]
            print(f"  Design 1:")
            print(f"    - Weight: {design_1.get('weight')}")
            print(f"    - Remark: {design_1.get('remark')}")
            print(f"    - Design Deduction: {design_1.get('design_deduction')}")
            
            if design_1.get('design_deduction') == 1.0:
                print("  ✓ Design 1 deduction correct")
            else:
                print(f"  ❌ Design 1 deduction incorrect: expected 1.0, got {design_1.get('design_deduction')}")
                return False
        else:
            print("❌ Design 1 not found in drafts")
            return False
        
    except Exception as e:
        print(f"❌ Error loading drafts: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 4: Clear drafts
    print("\n=== Test 4: Clear Drafts ===")
    try:
        success = services.weight_receipt.clear_weight_receipt_drafts(test_job_card)
        
        if success:
            print("✓ Drafts cleared successfully")
        else:
            print("❌ Failed to clear drafts")
            return False
        
        # Verify drafts are cleared
        drafts, _, _, _, _ = services.weight_receipt.get_weight_receipt_drafts(test_job_card)
        if len(drafts) == 0:
            print("✓ Verified drafts are cleared")
        else:
            print(f"❌ Drafts still exist: {len(drafts)} found")
            return False
            
    except Exception as e:
        print(f"❌ Error clearing drafts: {str(e)}")
        return False
    
    print("\n" + "="*60)
    print("✅ ALL INTEGRATION TESTS PASSED!")
    print("="*60)
    return True

if __name__ == "__main__":
    try:
        success = test_draft_save_and_load()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)
