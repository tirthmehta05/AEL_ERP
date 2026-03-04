import os
import sys
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
from src.shared.integrations.google_drive_service import google_drive_service
from src.data_entry.service.weight_receipt_service import WeightReceiptService

service = WeightReceiptService()
try:
    df = google_drive_service.get_worksheet_data(service.spreadsheet_id, "Weight Receipt Draft")
    if df is not None:
        print("Columns:", df.columns.tolist())
        print(df.to_dict('records'))
    else:
        print("No draft data found.")
except Exception as e:
    print(f"Error: {e}")
