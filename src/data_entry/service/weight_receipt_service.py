from typing import List
from src.shared.utils.logger_config import setup_logger
from src.data_entry.repository.weight_receipt_repository import WeightReceiptRepository
from src.data_entry.models.weight_receipt_models import WeightReceiptRequest, WeightReceiptRecord
from datetime import date, datetime
import json
import pandas as pd
import requests
from config import settings

logger = setup_logger(__name__)

class WeightReceiptService:
    def __init__(self):
        self.repository = WeightReceiptRepository()
        self.weighing_scale_api_url = settings.api.weighing_scale_url

    def get_next_weight_receipt_number(self) -> int:
        """
        Generates the next sequential weight receipt number.
        Starts from 10315 if no higher numeric-only number is found.
        """
        try:
            df = self.repository.get_all_weight_receipts()
            if df is None or df.empty or "WeightReceiptNumber" not in df.columns:
                return 10315

            max_receipt_num = 10314  # The base number to compare against
            
            # Filter for strings that are purely numeric, then convert and find max
            numeric_receipts = pd.to_numeric(df['WeightReceiptNumber'], errors='coerce').dropna()
            
            if not numeric_receipts.empty:
                current_max = numeric_receipts.max()
                if current_max > max_receipt_num:
                    max_receipt_num = int(current_max)
            
            return max_receipt_num + 1

        except Exception as e:
            logger.error(f"Error generating next weight receipt number: {e}")
            return int(datetime.now().timestamp())

    def generate_weight_receipt_number(self) -> str:
        """Generates a new sequential weight receipt number as a string."""
        return str(self.get_next_weight_receipt_number())

    def save_weight_receipt(self, request: WeightReceiptRequest) -> bool:
        """Saves a new weight receipt."""
        try:
            designs_json = json.dumps([d.model_dump() for d in request.designs])
            
            record = WeightReceiptRecord(
                weight_receipt_number=request.weight_receipt_number,
                receipt_date=request.receipt_date,
                job_card_number=request.job_card_number,
                party_name=request.party_name,
                po_no=request.po_no,
                material=request.material,
                sets=request.sets,
                designs_json=designs_json,
                weight_entry_type=request.weight_entry_type,
                total_weight=request.total_weight,
            )

            success = self.repository.save_weight_receipt(record.to_list())
            
            if success:
                logger.info(f"Successfully saved Weight Receipt {request.weight_receipt_number}")
                return True
            else:
                logger.error(f"Failed to save Weight Receipt {request.weight_receipt_number}.")
                return False
        except Exception as e:
            logger.error(f"Error saving weight receipt: {str(e)}")
            return False

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

    def get_current_weight_from_scale(self) -> dict:
        """
        Fetches the current weight from the external weighing scale API.
        Returns a dict with 'success', 'weight', and 'status'.
        """
        if not self.weighing_scale_api_url:
            logger.error("Weighing scale API URL is not configured.")
            return {"success": False, "weight": 0.0, "status": "unconfigured"}

        try:
            response = requests.get(self.weighing_scale_api_url, timeout=5)
            response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
            data = response.json()
            return {
                "success": data.get("success", False),
                "weight": data.get("weight", 0.0),
                "status": data.get("status", "unknown")
            }
        except requests.exceptions.Timeout:
            logger.error(f"Weighing scale API request timed out after 5 seconds.")
            return {"success": False, "weight": 0.0, "status": "timeout"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to weighing scale API: {e}")
            return {"success": False, "weight": 0.0, "status": "error"}
        except ValueError: # Catches JSON decode errors
            logger.error(f"Weighing scale API returned invalid JSON: {response.text}")
            return {"success": False, "weight": 0.0, "status": "invalid_response"}
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching weight: {e}")
            return {"success": False, "weight": 0.0, "status": "unexpected_error"}
