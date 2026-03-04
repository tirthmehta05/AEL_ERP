"""
Test script for weight receipt service methods.
Tests the new helper methods for partial dispatch functionality.
"""

from src.services import create_services

def test_weight_receipt_methods():
    print("=" * 60)
    print("Testing Weight Receipt Service Methods")
    print("=" * 60)
    
    services = create_services()
    
    # Get a sample job card from Sales Order-JC sheet
    print("\n1. Fetching sample job cards...")
    try:
        df = services.sales_order.google_service.get_worksheet_data(
            services.sales_order.spreadsheet_id, 
            "Sales Order-JC", 
            header_row=1
        )
        
        if df.empty:
            print("❌ No job cards found in Sales Order-JC sheet")
            return
        
        # Get the most recent job card
        sample_jc = df.iloc[-1]['job_card_number']
        print(f"✅ Using job card: {sample_jc}")
        
        # Test 1: Get Order Type
        print(f"\n2. Testing get_order_type_for_job_card('{sample_jc}')...")
        order_type = services.weight_receipt.get_order_type_for_job_card(sample_jc)
        print(f"✅ Order Type: {order_type}")
        
        if order_type not in ["CORE_BUILDING", "LOOSE_STRIPS", "EI_READY"]:
            print(f"⚠️  Warning: Unexpected order type '{order_type}'")
        
        # Test 2: Get Cumulative Weight
        print(f"\n3. Testing get_cumulative_weight_for_job_card('{sample_jc}')...")
        cumulative_weight = services.weight_receipt.get_cumulative_weight_for_job_card(sample_jc)
        print(f"✅ Cumulative Weight: {cumulative_weight:.2f} kg")
        
        # Test 3: Get Receipted Sets
        print(f"\n4. Testing get_receipted_sets_for_job_card('{sample_jc}')...")
        receipted_sets = services.weight_receipt.get_receipted_sets_for_job_card(sample_jc)
        print(f"✅ Receipted Sets: {receipted_sets}")
        
        # Test 4: Test with old job card (if exists)
        print("\n5. Testing backward compatibility with old job cards...")
        if len(df) > 1:
            # Try an older job card (might not have order_type)
            old_jc = df.iloc[0]['job_card_number']
            old_order_type = services.weight_receipt.get_order_type_for_job_card(old_jc)
            print(f"✅ Old Job Card ({old_jc}) Order Type: {old_order_type}")
            print(f"   (Should default to 'CORE_BUILDING' if order_type column missing)")
        
        # Summary
        print("\n" + "=" * 60)
        print("Test Summary:")
        print("=" * 60)
        print(f"Job Card: {sample_jc}")
        print(f"Order Type: {order_type}")
        print(f"Cumulative Weight: {cumulative_weight:.2f} kg")
        print(f"Receipted Sets: {receipted_sets}")
        
        # Interpretation
        print("\n" + "=" * 60)
        print("Interpretation:")
        print("=" * 60)
        if order_type == "CORE_BUILDING":
            print("✅ This is a CORE BUILDING order")
            print(f"   - Validation based on SETS (receipted: {receipted_sets})")
            print(f"   - Weight tracking: {cumulative_weight:.2f} kg")
        elif order_type == "LOOSE_STRIPS":
            print("✅ This is a LOOSE STRIPS order")
            print(f"   - Validation based on WEIGHT (cumulative: {cumulative_weight:.2f} kg)")
            print(f"   - Sets tracked but not enforced: {receipted_sets}")
        elif order_type == "EI_READY":
            print("✅ This is an EI READY order")
            print(f"   - Validation based on WEIGHT (cumulative: {cumulative_weight:.2f} kg)")
            print(f"   - Sets tracked but not enforced: {receipted_sets}")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_weight_receipt_methods()
