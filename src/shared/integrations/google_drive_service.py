"""
Google Drive Integration Service
Handles reading from and writing to Google Sheets
Supports both file-based and environment variable credentials
"""

import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from typing import List, Dict, Any, Optional
import streamlit as st
import os
import json
from datetime import datetime


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
    
    Example Usage:
        service = GoogleDriveService()
        
        # Test connection
        if service.test_connection("your_spreadsheet_id"):
            # Get dropdown options
            options = service.get_dropdown_options(
                "spreadsheet_id", "worksheet_name", "column_name"
            )
            
            # Append new data
            new_data = [["value1", "value2", "value3"]]
            success = service.append_data("spreadsheet_id", "worksheet_name", new_data)
    
    Attributes:
        scope (list): Google API scopes for spreadsheet and drive access
        credentials (Credentials): Google service account credentials
        client (gspread.Client): Authorized gspread client for API calls
    
    Methods:
        get_worksheet_data: Retrieve all data from a worksheet as DataFrame
        get_dropdown_options: Extract unique values from a column for dropdowns
        append_data: Add new rows to a worksheet
        get_worksheet_headers: Get column headers from a worksheet
        test_connection: Verify connection to a specific spreadsheet
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
            credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

            if credentials_json:
                try:
                    # Parse JSON from environment variable
                    credentials_dict = json.loads(credentials_json)
                    self.credentials = Credentials.from_service_account_info(
                        credentials_dict, scopes=self.scope
                    )
                    self.client = gspread.authorize(self.credentials)
                    st.success(
                        "✅ Google Drive client initialized from environment variables"
                    )
                    return
                except json.JSONDecodeError as e:
                    st.warning(
                        f"⚠️ Invalid JSON in GOOGLE_SERVICE_ACCOUNT_JSON: {str(e)}"
                    )
                except Exception as e:
                    st.warning(
                        f"⚠️ Error parsing credentials from environment: {str(e)}"
                    )

            # Method 2: Fallback to file-based credentials
            credentials_path = os.getenv(
                "GOOGLE_SERVICE_ACCOUNT_PATH", "credentials/service-account-key.json"
            )

            if os.path.exists(credentials_path):
                self.credentials = Credentials.from_service_account_file(
                    credentials_path, scopes=self.scope
                )
                self.client = gspread.authorize(self.credentials)
                st.success("✅ Google Drive client initialized from file")
            else:
                st.warning(
                    f"⚠️ No credentials found. Please set up Google Service Account credentials."
                )
                st.info("""
                **Setup Options:**
                1. **Environment Variable (Recommended):** Set `GOOGLE_SERVICE_ACCOUNT_JSON` with your service account JSON
                2. **File-based:** Place your service account JSON file at `{credentials_path}`
                """)
                self.client = None

        except Exception as e:
            st.error(f"❌ Failed to initialize Google Drive client: {str(e)}")
            self.client = None

    def get_worksheet_data(
        self, spreadsheet_id: str, worksheet_name: str
    ) -> pd.DataFrame:
        """Get data from a specific worksheet"""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self.client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(worksheet_name)

            # Get all records
            records = worksheet.get_all_records()
            return pd.DataFrame(records)

        except Exception as e:
            st.error(f"Error reading worksheet '{worksheet_name}': {str(e)}")
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
            st.error(f"Error getting dropdown options for {column_name}: {str(e)}")
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

            # Append the new row
            worksheet.append_rows(data)
            return True

        except Exception as e:
            st.error(f"Error appending data to '{worksheet_name}': {str(e)}")
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
            st.error(f"Error getting headers from '{worksheet_name}': {str(e)}")
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
            st.error(f"Connection test failed: {str(e)}")
            return False


# Global instance
google_drive_service = GoogleDriveService()
