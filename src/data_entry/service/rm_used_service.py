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

    def _get_used_data(self) -> Optional[pd.DataFrame]:
        """
        Loads and caches data from the 'Raw Material Used' sheet.
        """
        if self._dropdown_df is None:
            try:
                # The header for this sheet is on the third row.
                self._dropdown_df = self.google_service.get_worksheet_data(
                    self.spreadsheet_id, "Raw Material Used", header_row=3
                )
            except Exception as e:
                logger.error(f"Error loading 'Raw Material Used' data: {str(e)}")
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
        """
        Get all dropdown data. The coil numbers are filtered to only include
        coils with a positive available weight.
        """
        try:
            if not self.google_service.client:
                logger.warning("Google Drive client not initialized. Using empty dropdown data.")
                return DropdownData()

            # Test connection once
            if not self.google_service.test_connection(self.spreadsheet_id):
                logger.error(f"Cannot connect to spreadsheet: {self.spreadsheet_id}")
                return DropdownData()

            used_df = self._get_used_data()
            inward_df = self._get_inward_data()
            sales_order_df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order", header_row=1)

            job_cards = self._get_options_from_dataframe(sales_order_df, "Job Card")
            if "Stock" not in job_cards:
                job_cards.insert(0, "Stock")

            # --- Efficiently calculate available coils ---
            available_coils = []
            if inward_df is not None and not inward_df.empty:
                # Ensure weight columns are numeric, coercing errors
                inward_df['Coil Weight'] = pd.to_numeric(inward_df['Coil Weight'], errors='coerce')
                
                # Group by coil to get total inward weight
                inward_totals = inward_df.groupby('Coil Number')['Coil Weight'].sum().reset_index()
                
                # Group by coil to get total used weight
                used_totals = pd.DataFrame({'Coil No': [], 'Weight': []})
                if used_df is not None and not used_df.empty and 'Coil No' in used_df.columns:
                    used_df['Weight'] = pd.to_numeric(used_df['Weight'], errors='coerce')
                    used_totals = used_df.groupby('Coil No')['Weight'].sum().reset_index()

                # Merge inward and used dataframes
                if not used_totals.empty:
                    merged_df = pd.merge(inward_totals, used_totals, left_on='Coil Number', right_on='Coil No', how='left')
                else:
                    merged_df = inward_totals
                    merged_df['Weight'] = 0 # Add empty Weight column if no coils have been used

                # Calculate available weight
                merged_df['Weight'] = merged_df['Weight'].fillna(0)
                merged_df['available_weight'] = merged_df['Coil Weight'] - merged_df['Weight']
                merged_df['available_weight'] = merged_df['available_weight'].round(2)
                
                # Filter for coils with positive available weight
                available_coils_df = merged_df[merged_df['available_weight'] > 0]
                available_coils = sorted(available_coils_df['Coil Number'].dropna().unique().tolist())
            # --- End of new logic ---

            dropdown_data = DropdownData(
                job_cards=job_cards,
                coil_nos=available_coils,  # Use the new filtered list
                machines=self._get_options_from_dataframe(used_df, "Machine"),
                remarks=self._get_options_from_dataframe(used_df, "Remarks"),
            )
            return dropdown_data

        except Exception as e:
            logger.error(f"Error getting dropdown data: {str(e)}")
            return DropdownData()

    def get_available_weight(self, coil_no: str) -> float:
        """
        Calculate the available weight for a given coil number.
        
        Note: For better performance, use get_coil_info() which returns
        both weight and specifications in a single call.
        """
        try:
            inward_df = self._get_inward_data()
            used_df = self._get_used_data()

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

    def get_coil_info(self, coil_no: str) -> Optional[Dict[str, Any]]:
        """
        Get complete coil information including specifications and available weight.
        This method is optimized to fetch all data in a single pass through the DataFrames.
        
        Returns:
            Dictionary with width, thickness, grade, coating, and available_weight,
            or None if coil not found.
        """
        try:
            inward_df = self._get_inward_data()
            used_df = self._get_used_data()

            if inward_df is None or inward_df.empty:
                return None

            # Get coil data from inward sheet (single DataFrame filter)
            inward_coil_data = inward_df[inward_df["Coil Number"] == coil_no]
            if inward_coil_data.empty:
                return None

            # Get the first row for specifications (all rows for same coil have same specs)
            coil_row = inward_coil_data.iloc[0]
            
            # Calculate total weight
            total_weight = pd.to_numeric(inward_coil_data["Coil Weight"], errors='coerce').sum()

            # Calculate used weight
            used_weight = 0.0
            if used_df is not None and not used_df.empty:
                used_coil_data = used_df[used_df["Coil No"] == coil_no]
                if not used_coil_data.empty:
                    used_weight = pd.to_numeric(used_coil_data["Weight"], errors='coerce').sum()
            
            # Calculate available weight
            available_weight = total_weight - used_weight

            return {
                "width": coil_row.get("Width", "N/A"),
                "thickness": coil_row.get("Thk", "N/A"),
                "grade": coil_row.get("Grade", "N/A"),
                "coating": coil_row.get("Coating", "N/A"),
                "available_weight": available_weight,
            }

        except Exception as e:
            logger.error(f"Error getting coil info for {coil_no}: {str(e)}")
            return None

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

    def get_all_used_coils_df(self) -> pd.DataFrame:
        """
        Fetches the entire 'Raw Material Used' sheet.
        Uses internal caching to avoid repeated calls in the same session.
        """
        df = self._get_used_data()
        if df is None:
            return pd.DataFrame()
        return df

    def get_coils_for_job_card(self, job_card_number: str) -> List[dict]:
        """Fetches the coils assigned to a specific job card."""
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Raw Material Used", header_row=3)
            if df.empty or 'Card No' not in df.columns:
                return []

            coils_df = df[df['Card No'] == job_card_number]
            return coils_df.to_dict('records')
        except Exception as e:
            logger.error(f"Error fetching coils for job card {job_card_number}: {str(e)}")
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

            # Insert the new row before the last row to avoid overwriting formulas
            success = self.google_service.insert_row_before_last(
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
