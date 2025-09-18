# File: test_runner.py

import pandas as pd
from datetime import datetime
from src.shared.integrations.google_drive_service import GoogleDriveService

# --- CONFIGURATION ---
# Replace with your actual Spreadsheet ID
SPREADSHEET_ID = '1M1CsVZAXJ2ADfeLOlFESG3_HUKIYCK8gJz14JTwPRag' 
# Assuming your sheet is named 'Sheet1', change if needed
WORKSHEET_NAME = 'RM_Inward_Issue' 

def run_tests():
    """Initializes the service and runs a series of tests."""
    
    print("🚀 Initializing Google Drive Service...")
    service = GoogleDriveService()

    if not service.client:
        print("\n❌ Client initialization failed. Aborting tests.")
        return

    print("\n--- Test 1: Connection ---")
    if service.test_connection(SPREADSHEET_ID):
        print("✅ Connection successful!")
    else:
        print("❌ Connection failed. Check Spreadsheet ID and share settings.")
        return # Stop if we can't connect

    print("\n--- Test 2: Get Headers ---")
    headers = service.get_worksheet_headers(SPREADSHEET_ID, WORKSHEET_NAME)
    print(f"✅ Headers found: {headers}")

    print("\n--- Test 3: Get All Worksheet Data ---")
    df = service.get_worksheet_data(SPREADSHEET_ID, WORKSHEET_NAME)
    print("✅ Data fetched successfully:")
    print(df.to_string())

    print("\n--- Test 4: Get Dropdown Options from 'Col2' ---")
    options = service.get_dropdown_options(SPREADSHEET_ID, WORKSHEET_NAME, "Col2")
    print(f"✅ Unique options in 'Col2': {options}")

    print("\n--- Test 5: Append New Row ---")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = [['m', 'n', 'o', f'p_at_{timestamp}']]
    print(f"Appending data: {new_row}")
    if service.append_data(SPREADSHEET_ID, WORKSHEET_NAME, new_row):
        print("✅ Data appended successfully!")
    else:
        print("❌ Failed to append data.")

    print("\n--- Test 6: Verify Appended Data ---")
    df_after_append = service.get_worksheet_data(SPREADSHEET_ID, WORKSHEET_NAME)
    print("✅ Full data after append operation:")
    print(df_after_append.to_string())
    
    print("\n🎉 All tests completed.")


if __name__ == "__main__":
    if SPREADSHEET_ID == 'YOUR_SPREADSHEET_ID_HERE':
        print("🔴 ERROR: Please update the SPREADSHEET_ID in test_runner.py before running.")
    else:
        run_tests()