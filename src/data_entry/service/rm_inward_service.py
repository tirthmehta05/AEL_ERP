from typing import List, Dict, Any, Optional
from src.shared.utils.logger_config import setup_logger
import pandas as pd
from src.data_entry.models.rm_inward_models import (
    RMInwardIssueRequest,
    RMInwardIssueRecord,
    DropdownData,
)
from src.shared.integrations.google_drive_service import google_drive_service
from config import settings


# Configure logger
logger = setup_logger(__name__)


class RMInwardService:
    def __init__(self):
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id
        self._dropdown_df: Optional[pd.DataFrame] = None

    def _get_all_dropdown_data(self) -> Optional[pd.DataFrame]:
        """
        Loads all required dropdown data from the main
        'RM inward_Issue_format' sheet into a DataFrame.
        """
        if self._dropdown_df is None:
            try:
                self._dropdown_df = self.google_service.get_worksheet_data(
                    self.spreadsheet_id, "RM inward_Issue format", header_row=3
                )
            except Exception as e:
                logger.error(f"Error loading dropdown data: {str(e)}")
                self._dropdown_df = pd.DataFrame()
        return self._dropdown_df

    def _get_options_from_dataframe(self, column_name: str) -> List[str]:
        """
        Helper method to get unique, sorted options from a DataFrame column.
        """
        df = self._get_all_dropdown_data()
        if df is None or df.empty or column_name not in df.columns:
            return []

        options = df[column_name].dropna().unique().tolist()
        return sorted([str(option) for option in options if str(option).strip()])

    def get_dropdown_data(self) -> DropdownData:
        """Get all dropdown data from the main RM inward issue sheet"""
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

            # Load the main dataframe once for all dropdowns
            self._get_all_dropdown_data()
            if self._dropdown_df.empty:
                logging.warning("The main data sheet is empty. Cannot load dropdowns.")
                return DropdownData()

            dropdown_data = DropdownData(
                user_ids=self._get_options_from_dataframe("User ID"),
                rm_types=self._get_options_from_dataframe("RM Type"),
                coil_numbers=self._get_options_from_dataframe("Coil Number"),
                grades=self._get_options_from_dataframe("Grade"),
                thks=self._get_options_from_dataframe("Thk"),
                widths=self._get_options_from_dataframe("Width"),
                coatings=self._get_options_from_dataframe("Coating"),
                suppliers=self._get_options_from_dataframe("Coil Supplier"),
            )
            return dropdown_data

        except Exception as e:
            logger.error(f"Error getting dropdown data: {str(e)}")
            return DropdownData()

    def is_coil_number_unique(self, coil_number: str) -> bool:
        """
        Checks if a given coil number already exists in the sheet.
        This check is case-insensitive and ignores leading/trailing whitespace.
        """
        try:
            if not self.google_service.client:
                logger.warning("Google client not ready; assuming coil is unique.")
                return True # Fail open to not block entry if connection fails

            df = self._get_all_dropdown_data()
            if df is None or df.empty or "Coil Number" not in df.columns:
                return True # No data means the new number is unique

            # Perform a case-insensitive check
            existing_coils = df["Coil Number"].astype(str).str.strip().str.lower()
            return coil_number.strip().lower() not in existing_coils.values

        except Exception as e:
            logger.error(f"Error checking coil number uniqueness: {str(e)}")
            # In case of error, fail open to not block the user.
            return True

    def create_rm_inward_issue(self, request: RMInwardIssueRequest) -> bool:
        """Create a new RM Inward Issue record"""
        try:
            if not self.google_service.client:
                raise Exception("Google Drive client not initialized")

            
            # Convert request to record
            record = RMInwardIssueRecord(**request.dict())

            # Convert to list format for Google Sheets
            data_row = record.to_list()
            
            

            # Insert into the RM inward_Issue_format sheet before the last row
            success = self.google_service.insert_row_before_last(
                self.spreadsheet_id, "RM inward_Issue format", [data_row]
            )

            if success:
                logger.info("Data successfully added to Google Sheets!")
                return True
            else:
                logger.error("Failed to add data to Google Sheets")
                return False

        except Exception as e:
            logger.error(f"Failed to create RM Inward Issue: {str(e)}")
            return False

    def get_existing_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get existing RM Inward Issue records"""
        try:
            if not self.google_service.client:
                return []

            df = self.google_service.get_worksheet_data(
                self.spreadsheet_id, "RM inward_Issue format", header_row=3
            )

            if df.empty:
                return []

            # Convert to list of dictionaries and limit results
            records = df.tail(limit).to_dict("records")
            return records

        except Exception as e:
            logger.error(f"Error getting existing records: {str(e)}")
            return []

    def validate_spreadsheet_setup(self) -> bool:
        """Validate that the spreadsheet is properly set up"""
        try:
            if not self.google_service.client:
                return False

            if not self.google_service.test_connection(self.spreadsheet_id):
                return False

            # Check if the primary worksheet exists and has data
            try:
                headers = self.google_service.get_worksheet_headers(
                    self.spreadsheet_id, "RM inward_Issue format"
                )
                
                if not headers:
                    logger.warning(
                        "Primary worksheet 'RM inward_Issue_format' is empty or doesn't exist."
                    )
                    return False
            except Exception as e:
                logger.warning(
                    f"Cannot access worksheet 'RM inward_Issue_format': {str(e)}"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating spreadsheet setup: {str(e)}")
            return False
