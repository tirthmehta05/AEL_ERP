import pandas as pd
from typing import Any, Dict, Optional
from src.shared.utils.logger_config import setup_logger
from src.shared.integrations.google_drive_service import google_drive_service
from config import settings

logger = setup_logger(__name__)

class WeightReceiptRepository:
    BASE_HEADERS = ["WeightReceiptNumber", "Date", "JobCardNumber", "PartyName", "PONumber", "Material", "Sets", "DesignDetailsWithWeightsJSON", "WeightEntryType", "TotalWeight", "Deduction"]

    def __init__(self):
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id
        self.worksheet_name = "WeightReceipts"

    def get_all_weight_receipts(self, raise_on_error: bool = False) -> pd.DataFrame:
        """Fetches all weight receipts from the Google Sheet.

        raise_on_error=True propagates read failures instead of returning an
        empty DataFrame — required for receipt-number allocation.
        """
        return self.google_service.get_worksheet_data(
            self.spreadsheet_id, self.worksheet_name, header_row=1,
            raise_on_error=raise_on_error,
        )

    def save_weight_receipt(self, data_row: list, extra_columns: Optional[Dict[str, Any]] = None) -> bool:
        """Saves a new weight receipt to the Google Sheet.

        `extra_columns` (the QC sign-off) go into the same appended row, placed by
        header name, so a receipt and its QC can never be saved apart.
        """
        return self.google_service.append_row_mapped_to_headers(
            self.spreadsheet_id, self.worksheet_name, self.BASE_HEADERS, data_row, extra_columns or {},
        )
