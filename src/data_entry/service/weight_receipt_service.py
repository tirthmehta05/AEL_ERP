from typing import List
from src.shared.utils.logger_config import setup_logger
from src.data_entry.repository.weight_receipt_repository import WeightReceiptRepository
from src.data_entry.models.weight_receipt_models import WeightReceiptRequest, WeightReceiptRecord
from datetime import date, datetime
import json
import pandas as pd

logger = setup_logger(__name__)

class WeightReceiptService:
    def __init__(self):
        self.repository = WeightReceiptRepository()

    def generate_weight_receipt_number(self) -> str:
        """Generates a new unique Weight Receipt number."""
        today_str = datetime.now().strftime("%Y%m%d")
        time_str = datetime.now().strftime("%H%M%S")
        return f"WR-{today_str}-{time_str}"

    def save_weight_receipt(self, request: WeightReceiptRequest) -> str:
        """Saves a new weight receipt."""
        try:
            receipt_number = self.generate_weight_receipt_number()
            designs_json = json.dumps([d.model_dump() for d in request.designs])
            
            record = WeightReceiptRecord(
                weight_receipt_number=receipt_number,
                receipt_date=request.receipt_date,
                job_card_number=request.job_card_number,
                party_name=request.party_name,
                po_no=request.po_no,
                material=request.material,
                sets=request.sets,
                designs_json=designs_json,
            )

            success = self.repository.save_weight_receipt(record.to_list())
            
            if success:
                logger.info(f"Successfully saved Weight Receipt {receipt_number}")
                return receipt_number
            else:
                logger.error("Failed to save Weight Receipt.")
                return ""
        except Exception as e:
            logger.error(f"Error saving weight receipt: {str(e)}")
            return ""

    def get_weight_receipts_for_party_and_date_range(self, party_name: str, start_date: date, end_date: date) -> List[dict]:
        """Fetches weight receipts for a specific party within a date range."""
        try:
            df = self.repository.get_all_weight_receipts()
            if df.empty:
                return []

            df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
            
            filtered_df = df[
                (df['PartyName'] == party_name) &
                (df['Date'] >= start_date) &
                (df['Date'] <= end_date)
            ]
            return filtered_df.to_dict('records')
        except Exception as e:
            logger.error(f"Error fetching weight receipts for party {party_name}: {str(e)}")
            return []
