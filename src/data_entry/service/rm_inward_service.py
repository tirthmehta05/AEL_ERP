"""
Raw Material Inward Issue Service
Business logic for RM Inward Issue operations
"""

from typing import List, Dict, Any
from src.data_entry.models.rm_inward_models import (
    RMInwardIssueRequest,
    RMInwardIssueRecord,
    DropdownData,
)
from src.shared.integrations.google_drive_service import google_drive_service
import streamlit as st
import os


class RMInwardService:
    def __init__(self):
        self.google_service = google_drive_service
        # Get spreadsheet ID from environment variable
        self.spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID", "your_spreadsheet_id_here")

    def get_dropdown_data(self) -> DropdownData:
        """Get all dropdown data from Google Sheets"""
        try:
            if not self.google_service.client:
                st.warning(
                    "⚠️ Google Drive client not initialized. Using empty dropdown data."
                )
                return DropdownData()

            # Test connection first
            if not self.google_service.test_connection(self.spreadsheet_id):
                st.error(f"❌ Cannot connect to spreadsheet: {self.spreadsheet_id}")
                return DropdownData()

            dropdown_data = DropdownData(
                user_ids=self._get_dropdown_options("Users", "User ID"),
                rm_types=self._get_dropdown_options("RM Types", "RM Type"),
                coil_numbers=self._get_dropdown_options("Coil Numbers", "Coil Number"),
                grades=self._get_dropdown_options("Grades", "Grade"),
                thicknesses=self._get_dropdown_options("Thicknesses", "Thickness"),
                widths=self._get_dropdown_options("Widths", "Width"),
                coatings=self._get_dropdown_options("Coatings", "Coating"),
                suppliers=self._get_dropdown_options("Suppliers", "Supplier"),
            )

            return dropdown_data

        except Exception as e:
            st.error(f"Error getting dropdown data: {str(e)}")
            return DropdownData()

    def _get_dropdown_options(self, worksheet_name: str, column_name: str) -> List[str]:
        """Helper method to get dropdown options"""
        try:
            return self.google_service.get_dropdown_options(
                self.spreadsheet_id, worksheet_name, column_name
            )
        except Exception as e:
            st.warning(f"Could not load {column_name} from {worksheet_name}: {str(e)}")
            return []

    def create_rm_inward_issue(self, request: RMInwardIssueRequest) -> bool:
        """Create a new RM Inward Issue record"""
        try:
            if not self.google_service.client:
                raise Exception("Google Drive client not initialized")

            # Convert request to record
            record = RMInwardIssueRecord(**request.dict())

            # Convert to list format for Google Sheets
            data_row = record.to_list()

            # Append to the RM inward_Issue_format sheet
            success = self.google_service.append_data(
                self.spreadsheet_id, "RM inward_Issue_format", [data_row]
            )

            if success:
                st.success("✅ Data successfully added to Google Sheets!")
                return True
            else:
                st.error("❌ Failed to add data to Google Sheets")
                return False

        except Exception as e:
            st.error(f"Failed to create RM Inward Issue: {str(e)}")
            return False

    def get_existing_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get existing RM Inward Issue records"""
        try:
            if not self.google_service.client:
                return []

            df = self.google_service.get_worksheet_data(
                self.spreadsheet_id, "RM inward_Issue_format"
            )

            if df.empty:
                return []

            # Convert to list of dictionaries and limit results
            records = df.tail(limit).to_dict("records")
            return records

        except Exception as e:
            st.error(f"Error getting existing records: {str(e)}")
            return []

    def validate_spreadsheet_setup(self) -> bool:
        """Validate that the spreadsheet is properly set up"""
        try:
            if not self.google_service.client:
                return False

            # Check if spreadsheet exists and is accessible
            if not self.google_service.test_connection(self.spreadsheet_id):
                return False

            # Check if required worksheets exist
            required_worksheets = [
                "RM inward_Issue_format",
                "Users",
                "RM Types",
                "Coil Numbers",
                "Grades",
                "Thicknesses",
                "Widths",
                "Coatings",
                "Suppliers",
            ]

            for worksheet_name in required_worksheets:
                try:
                    headers = self.google_service.get_worksheet_headers(
                        self.spreadsheet_id, worksheet_name
                    )
                    if not headers:
                        st.warning(
                            f"⚠️ Worksheet '{worksheet_name}' is empty or doesn't exist"
                        )
                        return False
                except Exception as e:
                    st.warning(
                        f"⚠️ Cannot access worksheet '{worksheet_name}': {str(e)}"
                    )
                    return False

            return True

        except Exception as e:
            st.error(f"Error validating spreadsheet setup: {str(e)}")
            return False
