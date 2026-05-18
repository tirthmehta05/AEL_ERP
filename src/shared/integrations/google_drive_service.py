"""
Google Drive Integration Service
Handles reading from and writing to Google Sheets
Supports both file-based and environment variable credentials
"""

import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from typing import List, Any, Callable
import os
import json
import time
import random
from gspread.exceptions import APIError
from src.shared.utils.logger_config import setup_logger
from config import settings
logger = setup_logger(__name__)


class RateLimitError(Exception):
    """Raised when the Google Sheets API rate limit is exceeded."""
    pass


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
    
    def __init__(self, max_retries: int = 5, initial_backoff: float = 1.0, max_backoff: float = 60.0):
        self.scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        self.credentials = None
        self.client = None
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self._initialize_client()

    def _execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Executes a gspread function with retry logic for rate limiting."""
        retries = 0
        backoff = self.initial_backoff
        while retries < self.max_retries:
            try:
                return func(*args, **kwargs)
            except APIError as e:
                # Specifically handle 429: Too Many Requests
                if e.response.status_code == 429:
                    retries += 1
                    if retries >= self.max_retries:
                        logger.error(f"API rate limit exceeded. Max retries reached. Failing after {self.max_retries} attempts.")
                        raise
                    
                    # Exponential backoff with jitter
                    sleep_time = backoff + random.uniform(0, 1)
                    logger.warning(f"API rate limit exceeded. Retrying in {sleep_time:.2f} seconds... (Attempt {retries}/{self.max_retries})")
                    time.sleep(sleep_time)
                    backoff = min(self.max_backoff, backoff * 2)
                else:
                    # Re-raise other API errors immediately
                    raise
            except Exception:
                # Re-raise non-gspread exceptions
                raise
        # This line should not be reached if max_retries is > 0
        raise Exception("Exited retry loop unexpectedly.")

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
        self, spreadsheet_id: str, worksheet_name: str, header_row: int = 1,
        raise_on_error: bool = False,
    ) -> pd.DataFrame:
        """Get data from a specific worksheet, specifying the header row.

        By default a read failure (rate limit, network, etc.) is swallowed and
        an empty DataFrame is returned (legacy behavior). Pass
        raise_on_error=True for callers where "empty sheet" and "failed to
        read" must NOT be conflated — e.g. sequential ID allocation, where
        treating a failed read as an empty sheet writes a duplicate/seed
        number. With raise_on_error=True the exception propagates.
        """
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self._execute_with_retry(self.client.open_by_key, spreadsheet_id)
            worksheet = self._execute_with_retry(spreadsheet.worksheet, worksheet_name)

            all_values = self._execute_with_retry(worksheet.get_all_values)
            if len(all_values) < header_row:
                return pd.DataFrame()

            headers = all_values[header_row - 1]
            data = all_values[header_row:]

            df = pd.DataFrame(data, columns=headers)
            df = df.loc[:, [col for col in df.columns if col.strip()]]

            return df

        except APIError as e:
            logger.error(f"A gspread API error occurred while reading '{worksheet_name}': {str(e)}")
            if raise_on_error:
                raise
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"An unexpected error occurred while reading worksheet '{worksheet_name}': {str(e)}")
            if raise_on_error:
                raise
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

            spreadsheet = self._execute_with_retry(self.client.open_by_key, spreadsheet_id)
            worksheet = self._execute_with_retry(spreadsheet.worksheet, worksheet_name)

            # Append the new row with USER_ENTERED value input option
            self._execute_with_retry(worksheet.append_rows, data, value_input_option='USER_ENTERED')
            return True

        except APIError as e:
            logger.error(f"A gspread API error occurred while appending to '{worksheet_name}': {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error appending data to '{worksheet_name}': {str(e)}")
            return False

    def insert_row_before_last(
        self, spreadsheet_id: str, worksheet_name: str, data: List[List[Any]]
    ) -> bool:
        """Insert one or more new rows before the last row of a worksheet"""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self._execute_with_retry(self.client.open_by_key, spreadsheet_id)
            worksheet = self._execute_with_retry(spreadsheet.worksheet, worksheet_name)

            # Get all values to find the last row with content
            all_values = self._execute_with_retry(worksheet.get_all_values)
            last_row_index = len(all_values)

            # Insert the new rows before the last row
            self._execute_with_retry(worksheet.insert_rows, data, row=last_row_index, value_input_option='USER_ENTERED')
            return True

        except APIError as e:
            logger.error(f"A gspread API error occurred while inserting rows in '{worksheet_name}': {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error inserting rows in '{worksheet_name}': {str(e)}")
            return False

    def get_worksheet_headers(
        self, spreadsheet_id: str, worksheet_name: str
    ) -> List[str]:
        """Get column headers from a worksheet"""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self._execute_with_retry(self.client.open_by_key, spreadsheet_id)
            worksheet = self._execute_with_retry(spreadsheet.worksheet, worksheet_name)

            # Get the first row (headers)
            headers = self._execute_with_retry(worksheet.row_values, 1)
            return headers

        except APIError as e:
            logger.error(f"A gspread API error occurred while getting headers from '{worksheet_name}': {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting headers from '{worksheet_name}': {str(e)}")
            return []

    def test_connection(self, spreadsheet_id: str) -> bool:
        """Test connection to a specific spreadsheet"""
        try:
            if not self.client:
                return False

            spreadsheet = self._execute_with_retry(self.client.open_by_key, spreadsheet_id)
            worksheets = self._execute_with_retry(spreadsheet.worksheets)
            return len(worksheets) > 0

        except APIError as e:
            logger.error(f"A gspread API error occurred during connection test: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False

    def ensure_worksheet_with_headers(self, spreadsheet_id: str, worksheet_name: str, headers: List[str]) -> bool:
        """Ensures a worksheet exists and has the specified headers."""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")
            
            spreadsheet = self._execute_with_retry(self.client.open_by_key, spreadsheet_id)
            try:
                worksheet = self._execute_with_retry(spreadsheet.worksheet, worksheet_name)
                # If sheet exists but is empty, add headers
                all_values = self._execute_with_retry(worksheet.get_all_values)
                if not all_values:
                    self._execute_with_retry(worksheet.append_row, headers, value_input_option='USER_ENTERED')
            except gspread.exceptions.WorksheetNotFound:
                # If sheet does not exist, create it and add headers
                worksheet = self._execute_with_retry(spreadsheet.add_worksheet, title=worksheet_name, rows=1, cols=len(headers))
                self._execute_with_retry(worksheet.append_row, headers, value_input_option='USER_ENTERED')
            return True
        except APIError as e:
            logger.error(f"A gspread API error occurred while ensuring worksheet '{worksheet_name}': {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error ensuring worksheet '{worksheet_name}': {str(e)}")
            return False

    def upsert_row(self, spreadsheet_id: str, worksheet_name: str, data: List[Any], key_column_index: int = 0) -> bool:
        """Update a row if key exists, otherwise insert a new row."""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self._execute_with_retry(self.client.open_by_key, spreadsheet_id)
            try:
                worksheet = self._execute_with_retry(spreadsheet.worksheet, worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                logger.info(f"Worksheet '{worksheet_name}' not found. Creating it.")
                worksheet = self._execute_with_retry(spreadsheet.add_worksheet, title=worksheet_name, rows=1, cols=len(data))
                self._execute_with_retry(worksheet.append_row, data, value_input_option='USER_ENTERED')
                return True

            key_to_find = data[key_column_index]
            cell_list = self._execute_with_retry(worksheet.findall, key_to_find, in_column=key_column_index + 1)

            if cell_list:
                # Key found, update the first occurrence
                row_index = cell_list[0].row
                self._execute_with_retry(worksheet.update, f'A{row_index}', [data], value_input_option='USER_ENTERED')
                logger.info(f"Updated row {row_index} for key '{key_to_find}' in '{worksheet_name}'.")
            else:
                # Key not found, append new row
                self._execute_with_retry(worksheet.append_row, data, value_input_option='USER_ENTERED')
                logger.info(f"Appended new row for key '{key_to_find}' in '{worksheet_name}'.")
            
            return True
        except APIError as e:
            logger.error(f"A gspread API error occurred while upserting data in '{worksheet_name}': {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error upserting data in '{worksheet_name}': {str(e)}")
            return False

    def delete_rows_by_key(self, spreadsheet_id: str, worksheet_name: str, key_value: str, key_column_index: int = 0) -> bool:
        """Deletes all rows where the key column matches the given value. Deletes from bottom to top to preserve row indices."""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self._execute_with_retry(self.client.open_by_key, spreadsheet_id)
            worksheet = self._execute_with_retry(spreadsheet.worksheet, worksheet_name)

            cell_list = self._execute_with_retry(worksheet.findall, key_value, in_column=key_column_index + 1)

            if not cell_list:
                logger.info(f"No rows found for key '{key_value}' in '{worksheet_name}'. Nothing to delete.")
                return True

            # Delete from bottom to top so row indices don't shift
            rows_to_delete = sorted([cell.row for cell in cell_list], reverse=True)
            for row_index in rows_to_delete:
                self._execute_with_retry(worksheet.delete_rows, row_index)

            logger.info(f"Deleted {len(rows_to_delete)} rows for key '{key_value}' in '{worksheet_name}'.")
            return True
        except RateLimitError:
            raise
        except APIError as e:
            logger.error(f"A gspread API error occurred while deleting rows in '{worksheet_name}': {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error deleting rows in '{worksheet_name}': {str(e)}")
            return False

    def update_cell_by_key(self, spreadsheet_id: str, worksheet_name: str, key_value: str, key_column_index: int, target_column_index: int, new_value: str) -> bool:
        """Finds the first row where key_column matches key_value, then updates the cell at target_column_index."""
        try:
            if not self.client:
                raise Exception("Google Drive client not initialized")

            spreadsheet = self._execute_with_retry(self.client.open_by_key, spreadsheet_id)
            worksheet = self._execute_with_retry(spreadsheet.worksheet, worksheet_name)

            cell = self._execute_with_retry(worksheet.find, key_value, in_column=key_column_index + 1)

            if not cell:
                logger.error(f"Key '{key_value}' not found in column {key_column_index + 1} of '{worksheet_name}'.")
                return False

            # target_column_index is 0-based, update_cell expects 1-based column
            self._execute_with_retry(worksheet.update_cell, cell.row, target_column_index + 1, new_value)
            logger.info(f"Updated column {target_column_index + 1} in row {cell.row} for key '{key_value}' in '{worksheet_name}'.")
            return True
        except RateLimitError:
            raise
        except APIError as e:
            logger.error(f"A gspread API error occurred while updating cell in '{worksheet_name}': {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error updating cell in '{worksheet_name}': {str(e)}")
            return False


# Global instance
google_drive_service = GoogleDriveService()
