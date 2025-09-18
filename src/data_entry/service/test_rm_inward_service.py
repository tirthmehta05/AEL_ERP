# run_test.py

import time
from datetime import datetime
from src.data_entry.models.rm_inward_models import RMInwardIssueRequest
from src.data_entry.service.rm_inward_service import RMInwardService
from src.shared.integrations.google_drive_service import google_drive_service
from config import settings


def run_all_tests():
    """
    Executes a series of live tests for the RMInwardService.
    """
    print("--- Starting Live End-to-End Tests for RMInwardService ---")

    # Initialize the service
    service = RMInwardService()

    # Test 1: Validate Spreadsheet Setup
    print("\n--- Test 1: Validating Spreadsheet Setup ---")
    if test_validate_spreadsheet_setup(service):
        print("✅ Spreadsheet setup is valid.")
    else:
        print("❌ Spreadsheet validation failed. Aborting tests.")
        return

    # Test 2: Get Dropdown Data
    print("\n--- Test 2: Getting Dropdown Data ---")
    if test_get_dropdown_data(service):
        print("✅ Dropdown data retrieved successfully.")
    else:
        print("❌ Failed to retrieve dropdown data.")

    # Test 3: Create and Read a New Record
    print("\n--- Test 3: Creating and Verifying a New Record ---")
    if test_create_and_read_record(service):
        print("✅ New record successfully created and verified.")
    else:
        print("❌ Failed to create or verify the new record.")

    print("\n--- All Tests Completed ---")


def test_validate_spreadsheet_setup(service: RMInwardService) -> bool:
    """Tests if the spreadsheet is properly configured."""
    try:
        is_valid = service.validate_spreadsheet_setup()
        if not is_valid:
            print("Spreadsheet validation failed.")
            return False
        return True
    except Exception as e:
        print(f"An error occurred during validation: {e}")
        return False


def test_get_dropdown_data(service: RMInwardService) -> bool:
    """Tests the retrieval of dropdown data."""
    try:
        dropdown_data = service.get_dropdown_data()
        if not dropdown_data.user_ids or not dropdown_data.rm_types:
            print("Dropdown data is empty. Check your sheet content.")
            return False
        return True
    except Exception as e:
        print(f"An error occurred while getting dropdown data: {e}")
        return False


def test_create_and_read_record(service: RMInwardService) -> bool:
    """Tests creating a record and then reading it back to verify."""
    try:
        unique_id = int(datetime.now().timestamp())
        request_data = RMInwardIssueRequest(
            user_id=f"test_user_{unique_id}",
            rm_receipt_date=datetime.now().date(),
            rm_type="LiveTest",
            coil_number=f"LIVE-TEST-{unique_id}",
            grade="TestGrade",
            thickness="1.5",
            width="1000",
            coating="Z300",
            coil_weight=unique_id,
            po_number=f"PO-{unique_id}",
            coil_supplier="JSW"
        )

        # Step 1: Create the record
        print(f"Submitting new record with Coil Number: {request_data.coil_number}...")
        success = service.create_rm_inward_issue(request_data)
        if not success:
            print("Failed to submit the new record.")
            return False

        # Give Google Sheets time to process the write
        time.sleep(2)

        # Step 2: Verify the record exists
        print("Verifying the record was added...")
        existing_records = service.get_existing_records(limit=5)

        if not existing_records:
            print("No records found after submission.")
            return False
        latest_record = existing_records[-1]
        print(latest_record.get("Coil Number"))
        if latest_record.get("Coil Number") != request_data.coil_number:
            print(
                f"Verification failed. Expected Coil Number: {request_data.coil_number}, Found: {latest_record.get('Coil Number')}"
            )
            return False

        return True
    except Exception as e:
        print(f"An error occurred during the create/read test: {e}")
        return False


if __name__ == "__main__":
    run_all_tests()
