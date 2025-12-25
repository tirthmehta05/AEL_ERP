import pandas as pd
from src.shared.utils.logger_config import setup_logger
from src.shared.integrations.google_drive_service import google_drive_service
from config import settings

logger = setup_logger(__name__)

class WeightReceiptRepository:
    def __init__(self):
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id
        self.worksheet_name = "WeightReceipts"

    def get_all_weight_receipts(self) -> pd.DataFrame:
        """Fetches all weight receipts from the Google Sheet."""
        return self.google_service.get_worksheet_data(self.spreadsheet_id, self.worksheet_name, header_row=1)

    def save_weight_receipt(self, data_row: list) -> bool:
        """Saves a new weight receipt to the Google Sheet."""
        headers = ["WeightReceiptNumber", "Date", "JobCardNumber", "PartyName", "PONumber", "Material", "Sets", "DesignDetailsWithWeightsJSON", "WeightEntryType", "TotalWeight", "Deduction"]
        self.google_service.ensure_worksheet_with_headers(self.spreadsheet_id, self.worksheet_name, headers)
        return self.google_service.append_data(self.spreadsheet_id, self.worksheet_name, [data_row])
