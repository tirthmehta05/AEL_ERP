from typing import List, Optional, Dict, Any
from src.shared.utils.logger_config import setup_logger
import pandas as pd
from src.data_entry.models.rm_used_models import (
    RMUsedRequest,
    DropdownData,
    RMUsedRecord,
)
from src.shared.integrations.google_drive_service import google_drive_service
from config import settings


# Configure logger
logger = setup_logger(__name__)


class RMUsedService:
    def __init__(self):
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id
        self._dropdown_df: Optional[pd.DataFrame] = None
        self._inward_df: Optional[pd.DataFrame] = None

    def _get_all_dropdown_data(self) -> Optional[pd.DataFrame]:
        """
        Loads all required dropdown data from the main
        'Raw Material Used' sheet into a DataFrame.
        """
        if self._dropdown_df is None:
            try:
                self._dropdown_df = self.google_service.get_worksheet_data(
                    self.spreadsheet_id, "Raw Material Used", header_row=2
                )
            except Exception as e:
                logger.error(f"Error loading dropdown data: {str(e)}")
                self._dropdown_df = pd.DataFrame()
        return self._dropdown_df

    def _get_inward_data(self) -> Optional[pd.DataFrame]:
        """
        Loads all required data from the 'RM inward_Issue format' sheet.
        """
        if self._inward_df is None:
            try:
                self._inward_df = self.google_service.get_worksheet_data(
                    self.spreadsheet_id, "RM inward_Issue format", header_row=3
                )
            except Exception as e:
                logger.error(f"Error loading inward data: {str(e)}")
                self._inward_df = pd.DataFrame()
        return self._inward_df

    def _get_options_from_dataframe(self, df: pd.DataFrame, column_name: str) -> List[str]:
        """
        Helper method to get unique, sorted options from a DataFrame column.
        """
        if df is None or df.empty or column_name not in df.columns:
            return []

        options = df[column_name].dropna().unique().tolist()
        return sorted([str(option) for option in options if str(option).strip()])

    def get_dropdown_data(self) -> DropdownData:
        """Get all dropdown data from the main Raw Material Used sheet"""
        try:
            if not self.google_service.client:
                logging.warning(
                    "Google Drive client not initialized. Using empty dropdown data."
                )
                return DropdownData()

            # Test connection once
            if not self.google_service.test_connection(self.spreadsheet_id):
                logging.error(f"Cannot connect to spreadsheet: {self.spreadsheet_id}")
                return DropdownData()

            # Load data from all sheets
            used_df = self._get_all_dropdown_data()
            inward_df = self._get_inward_data()
            sales_order_df = self.google_service.get_worksheet_data(
                self.spreadsheet_id, "Sales Order", header_row=1
            )

            job_cards = self._get_options_from_dataframe(sales_order_df, "Job Card")
            if "Stock" not in job_cards:
                job_cards.insert(0, "Stock")

            dropdown_data = DropdownData(
                job_cards=job_cards,
                coil_nos=self._get_options_from_dataframe(inward_df, "Coil Number"),
                machines=self._get_options_from_dataframe(used_df, "Machine"),
                remarks=self._get_options_from_dataframe(used_df, "Remarks"),
            )
            return dropdown_data

        except Exception as e:
            logger.error(f"Error getting dropdown data: {str(e)}")
            return DropdownData()

    def get_available_weight(self, coil_no: str) -> float:
        """Calculate the available weight for a given coil number."""
        try:
            inward_df = self._get_inward_data()
            used_df = self._get_all_dropdown_data()

            if inward_df is None or inward_df.empty:
                return 0.0

            # Get total weight from inward sheet
            inward_coil_data = inward_df[inward_df["Coil Number"] == coil_no]
            if inward_coil_data.empty:
                return 0.0
            total_weight = pd.to_numeric(inward_coil_data["Coil Weight"], errors='coerce').sum()

            # Get used weight from used sheet
            used_weight = 0.0
            if used_df is not None and not used_df.empty:
                used_coil_data = used_df[used_df["Coil No"] == coil_no]
                if not used_coil_data.empty:
                    used_weight = pd.to_numeric(used_coil_data["Weight"], errors='coerce').sum()
            
            return total_weight - used_weight

        except Exception as e:
            logger.error(f"Error getting available weight for {coil_no}: {str(e)}")
            return 0.0

    def get_existing_records(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get existing RM Used records"""
        try:
            if not self.google_service.client:
                return []

            df = self.google_service.get_worksheet_data(
                self.spreadsheet_id, "Raw Material Used"
            )

            if df.empty:
                return []

            # Convert to list of dictionaries and limit results
            records = df.tail(limit).to_dict("records")
            return records

        except Exception as e:
            logger.error(f"Error getting existing records: {str(e)}")
            return []

    def create_rm_used(self, request: RMUsedRequest) -> bool:
        """Create a new RM Used record"""
        try:
            if not self.google_service.client:
                raise Exception("Google Drive client not initialized")

            # Convert request to record
            record = RMUsedRecord(**request.dict())

            # Convert to list format for Google Sheets
            data_row = record.to_list()

            # Append to the Raw Material Used sheet
            success = self.google_service.append_data(
                self.spreadsheet_id, "Raw Material Used", [data_row]
            )

            if success:
                logger.info("Data successfully added to Google Sheets!")
                return True
            else:
                logger.error("Failed to add data to Google Sheets")
                return False

        except Exception as e:
            logger.error(f"Failed to create RM Used: {str(e)}")
            return False
