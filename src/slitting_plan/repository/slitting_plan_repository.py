import pandas as pd
from src.shared.utils.logger_config import setup_logger
from src.shared.integrations.google_drive_service import google_drive_service
from config import settings
from datetime import datetime
import json
import gspread

logger = setup_logger(__name__)

class SlittingPlanRepository:
    def __init__(self):
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id

    def fetch_inward_data(self, start_date=None, end_date=None) -> pd.DataFrame:
        df = self.google_service.get_worksheet_data(self.spreadsheet_id, "RM inward_Issue format", header_row=3)
        if df.empty or (start_date is None and end_date is None):
            return df
        
        try:
            # The date column from the sheet is 'RM Receipt Date'
            date_col = "RM Receipt Date"
            if date_col not in df.columns:
                logger.warning(f"Date column '{date_col}' not found in 'RM inward_Issue format' sheet. Returning unfiltered data.")
                return df

            df[date_col] = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
            
            # Drop rows where date conversion failed
            original_count = len(df)
            df.dropna(subset=[date_col], inplace=True)
            if len(df) < original_count:
                logger.warning(f"Dropped {original_count - len(df)} rows with invalid dates from inward data.")

            # Filter by date range if provided
            if start_date:
                df = df[df[date_col].dt.date >= start_date]
            if end_date:
                df = df[df[date_col].dt.date <= end_date]
        except Exception as e:
            logger.error(f"Error filtering inward data by date: {e}. Returning unfiltered data.")
            # To be safe, re-fetch or return the original unfiltered df if something went wrong
            return self.google_service.get_worksheet_data(self.spreadsheet_id, "RM inward_Issue format", header_row=3)
        
        return df

    def fetch_used_data(self) -> pd.DataFrame:
        return self.google_service.get_worksheet_data(self.spreadsheet_id, "Raw Material Used", header_row=2)

    def fetch_sales_order_data(self) -> pd.DataFrame:
        return self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order", header_row=1)

    def fetch_slitting_plans_data(self) -> pd.DataFrame:
        return self.google_service.get_worksheet_data(self.spreadsheet_id, "SlittingPlans", header_row=1)

    def append_slitting_plan(self, row_to_add: list) -> bool:
        return self.google_service.append_data(self.spreadsheet_id, "SlittingPlans", [row_to_add])

    def update_plan_status_in_sheet(self, plan_id: str, new_status: str) -> bool:
        try:
            worksheet = self.google_service.client.open_by_key(self.spreadsheet_id).worksheet("SlittingPlans")
            cell = worksheet.find(plan_id, in_column=1)
            if not cell:
                logger.warning(f"Plan ID {plan_id} not found for status update.")
                return False
            worksheet.update_cell(cell.row, 3, new_status)
            return True
        except Exception as e:
            logger.error(f"Error updating status for plan {plan_id}: {str(e)}")
            return False
    
    def ensure_slitting_plans_worksheet(self, headers: list):
        self.google_service.ensure_worksheet_with_headers(self.spreadsheet_id, "SlittingPlans", headers)
