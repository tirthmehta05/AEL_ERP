"""
Google Drive Integration Service
Handles reading from and writing to Google Sheets
Supports both file-based and environment variable credentials
"""

import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from typing import List, Any
import os
import json
from src.shared.utils.logger_config import setup_logger
from config import settings
logger = setup_logger(__name__)


class GoogleDriveService:
    """
    Google Drive Integration Service for AEL ERP System
    
    This service provides comprehensive functionality for interacting with Google Sheets
    through the Google Drive API. It supports both environment variable and file-based
    authentication methods for flexible deployment scenarios.
    
    Features:
    - Read data from Google Sheets worksheets
    - Extract dropdown options from specific columns
    - Append new data to worksheets
    - Get worksheet headers
    - Test connection to spreadsheets
    - Support for both environment variable and file-based credentials
    
    Authentication Methods:
    1. Environment Variable (Recommended): Set GOOGLE_SERVICE_ACCOUNT_JSON
    2. File-based: Place service account JSON at credentials/service-account-key.json
    """
    
    def __init__(self):
        self.scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        self.credentials = None
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Google Sheets client using environment variables or file"""
        try:
            # Method 1: Try to get credentials from environment variable (preferred)
            # Assuming settings.api.google_service_account_json exists
            try:
                credentials_json = settings.api.google_service_account_json
                if credentials_json:
                    credentials_dict = json.loads(credentials_json)
                    self.credentials = Credentials.from_service_account_info(
                        credentials_dict, scopes=self.scope
                    )
                    self.client = gspread.authorize(self.credentials)
                    logger.info("✅ Google Drive client initialized from environment variables")
                    return
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"⚠️ Invalid JSON or missing setting in GOOGLE_SERVICE_ACCOUNT_JSON: {str(e)}")
            except Exception as e:
                logger.warning(f"⚠️ Error parsing credentials from environment: {str(e)}")

            # Method 2: Fallback to file-based credentials
            credentials_path = "secrets/secret_google.json"

            if os.path.exists(credentials_path):
                self.credentials = Credentials.from_service_account_file(
                    credentials_path, scopes=self.scope
                )
                self.client = gspread.authorize(self.credentials)
                logger.info("✅ Google Drive client initialized from file")
            else:
                logger.warning(
                    f"⚠️ No credentials found. Please set up Google Service Account credentials."
                )
                logger.info(
                    "Setup Options: 1. Environment Variable (Recommended): Set `GOOGLE_SERVICE_ACCOUNT_JSON`"
                    f" 2. File-based: Place service account JSON file at `{credentials_path}`"
                )
                self.client = None

        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Drive client: {str(e)}")
            self.client = None

    def get_worksheet_data(
        self, spreadsheet_id: str, worksheet_name: str, header_row: int = 1
    ) -> pd.DataFrame:
        """Get data from a specific worksheet, specifying the header row."""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self.client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)

            all_values = worksheet.get_all_values()
            if len(all_values) < header_row:
                return pd.DataFrame()

            headers = all_values[header_row - 1]
            data = all_values[header_row:]

            df = pd.DataFrame(data, columns=headers)
            df = df.loc[:, [col for col in df.columns if col.strip()]]

            return df

        except gspread.exceptions.GSpreadException as e:
            logger.error(f"Error reading worksheet '{worksheet_name}' with gspread: {str(e)}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"An unexpected error occurred while reading worksheet '{worksheet_name}': {str(e)}")
            return pd.DataFrame()

    def get_dropdown_options(
        self, spreadsheet_id: str, worksheet_name: str, column_name: str
    ) -> List[str]:
        """Get unique values from a specific column for dropdown options"""
        try:
            df = self.get_worksheet_data(spreadsheet_id, worksheet_name)
            if df.empty or column_name not in df.columns:
                return []

            # Get unique values, remove NaN, and sort
            options = df[column_name].dropna().unique().tolist()
            return sorted([str(option) for option in options if str(option).strip()])

        except Exception as e:
            logger.error(f"Error getting dropdown options for {column_name}: {str(e)}")
            return []

    def append_data(
        self, spreadsheet_id: str, worksheet_name: str, data: List[List[Any]]
    ) -> bool:
        """Append new data to a worksheet"""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self.client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)

            # Append the new row with USER_ENTERED value input option
            worksheet.append_rows(data, value_input_option='USER_ENTERED')
            return True

        except Exception as e:
            logger.error(f"Error appending data to '{worksheet_name}': {str(e)}")
            return False

    def insert_row_before_last(
        self, spreadsheet_id: str, worksheet_name: str, data: List[List[Any]]
    ) -> bool:
        """Insert a new row before the last row of a worksheet"""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self.client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)

            # Get all values to find the last row with content
            all_values = worksheet.get_all_values()
            last_row_index = len(all_values)

            # Insert the new row before the last row
            worksheet.insert_row(data[0], index=last_row_index, value_input_option='USER_ENTERED')
            return True

        except Exception as e:
            logger.error(f"Error inserting row in '{worksheet_name}': {str(e)}")
            return False

    def get_worksheet_headers(
        self, spreadsheet_id: str, worksheet_name: str
    ) -> List[str]:
        """Get column headers from a worksheet"""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self.client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)

            # Get the first row (headers)
            headers = worksheet.row_values(1)
            return headers

        except Exception as e:
            logger.error(f"Error getting headers from '{worksheet_name}': {str(e)}")
            return []

    def test_connection(self, spreadsheet_id: str) -> bool:
        """Test connection to a specific spreadsheet"""
        try:
            if not self.client:
                return False

            spreadsheet = self.client.open_by_key(spreadsheet_id)
            worksheets = spreadsheet.worksheets()
            return len(worksheets) > 0

        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False

# Global instance
google_drive_service = GoogleDriveService()
