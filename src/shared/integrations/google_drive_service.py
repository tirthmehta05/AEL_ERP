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


class TransientAPIError(Exception):
    """Raised when a transient Sheets API failure survives every retry.

    Distinct from APIError so callers can tell "the API was unreachable" apart
    from "the API answered, and the answer was no". Handlers that catch APIError
    and return False must not swallow this: an exhausted retry means the
    operation's outcome is unknown, not that it failed cleanly.
    """
    pass


class RateLimitError(TransientAPIError):
    """Raised when the Google Sheets API rate limit is exceeded."""
    pass


# HTTP statuses worth retrying, split by whether replaying the call is safe.
#
# A 429 is a pre-execution quota rejection: the request never ran, so replaying
# it is free. A 5xx is not that — Google returns 502/504 routinely *after* a
# mutation has already been applied, when only the response was lost. Replaying
# a write on 5xx therefore risks applying it twice.
#
# Anything outside these sets — 400, 403, 404 — is a real answer and raises on
# the first attempt rather than hiding behind a minute of pointless backoff.
RETRYABLE_READ_STATUS_CODES = frozenset({
    408,  # Request Timeout
    429,  # Too Many Requests (rate limit)
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
})

# Non-idempotent calls (append/insert/delete/create) retry on quota pushback
# only. Replaying these after a 5xx duplicates rows or, for index-based
# deletes, removes a different row than the one that was found.
RETRYABLE_WRITE_STATUS_CODES = frozenset({
    429,  # Too Many Requests (rate limit)
})


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
    
    # Budget chosen against the 30s double-click lock in the data-entry pages
    # (pages/sales_order.py, pages/weight_receipt.py). A save issues several
    # wrapped calls in sequence, so the per-call worst case has to stay small
    # enough that a whole save cannot outlive the lock and let a second click
    # start a duplicate. 3 retries at 1s/2s + jitter ≈ 5s per call worst case.
    def __init__(self, max_retries: int = 3, initial_backoff: float = 1.0, max_backoff: float = 8.0):
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

    def _execute_with_retry(self, func: Callable, *args, _idempotent: bool = True, **kwargs) -> Any:
        """Executes a gspread function, retrying transient API failures.

        Backs off exponentially with jitter between attempts. Which failures
        are retried depends on whether replaying the call is safe:

        - _idempotent=True (default, reads and fixed-range writes): retries the
          full transient set — 408/429/500/502/503/504.
        - _idempotent=False (append, insert, delete, create): retries 429 only,
          because a 5xx may mean the mutation already landed and only the
          response was lost. See RETRYABLE_WRITE_STATUS_CODES.

        Raises RateLimitError / TransientAPIError once the retry budget is
        exhausted, so an unknown outcome is never mistaken by callers for a
        clean failure. Every other APIError is raised on the first attempt.
        """
        retryable = RETRYABLE_READ_STATUS_CODES if _idempotent else RETRYABLE_WRITE_STATUS_CODES
        retries = 0
        backoff = self.initial_backoff
        while retries < self.max_retries:
            try:
                return func(*args, **kwargs)
            except APIError as e:
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code not in retryable:
                    # Re-raise immediately: either a real error, or a 5xx on a
                    # call we must not replay.
                    raise

                reason = "API rate limit exceeded" if status_code == 429 else f"Transient API error [{status_code}]"
                retries += 1
                if retries >= self.max_retries:
                    logger.error(f"{reason}. Max retries reached. Failing after {self.max_retries} attempts.")
                    error_cls = RateLimitError if status_code == 429 else TransientAPIError
                    raise error_cls(f"{reason}; giving up after {self.max_retries} attempts.") from e

                # Exponential backoff with jitter
                sleep_time = backoff + random.uniform(0, 1)
                logger.warning(f"{reason}. Retrying in {sleep_time:.2f} seconds... (Attempt {retries}/{self.max_retries})")
                time.sleep(sleep_time)
                backoff = min(self.max_backoff, backoff * 2)
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

    def get_all_worksheets_data(
        self, spreadsheet_id: str, header_row: int = 1,
    ) -> dict:
        """Read EVERY worksheet (tab) in a spreadsheet into a
        {tab_name: DataFrame} mapping — the same shape pandas returns from
        pd.read_excel(path, sheet_name=None).

        Empty cells are coerced to NaN so downstream parsers that test for
        blank rows via pd.isna() behave the same as with an .xlsx source.
        Always raises on a read failure: a caller using this for pricing
        data must NOT silently proceed on a partial/empty read.
        """
        if not self.client:
            raise Exception("Google Drive client not initialized")
        spreadsheet = self._execute_with_retry(self.client.open_by_key,
                                               spreadsheet_id)
        worksheets = self._execute_with_retry(spreadsheet.worksheets)
        out: dict = {}
        for ws in worksheets:
            all_values = self._execute_with_retry(ws.get_all_values)
            if len(all_values) < header_row:
                out[ws.title] = pd.DataFrame()
                continue
            headers = all_values[header_row - 1]
            data = all_values[header_row:]
            df = pd.DataFrame(data, columns=headers)
            df = df.loc[:, [c for c in df.columns if c.strip()]]
            # blank string → NaN so pd.isna()-based blank-row checks work
            df = df.replace("", pd.NA)
            out[ws.title] = df
        return out

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
            self._execute_with_retry(worksheet.append_rows, data, value_input_option='USER_ENTERED', _idempotent=False)
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
            self._execute_with_retry(worksheet.insert_rows, data, row=last_row_index, value_input_option='USER_ENTERED', _idempotent=False)
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
                    self._execute_with_retry(worksheet.append_row, headers, value_input_option='USER_ENTERED', _idempotent=False)
            except gspread.exceptions.WorksheetNotFound:
                # If sheet does not exist, create it and add headers
                worksheet = self._execute_with_retry(spreadsheet.add_worksheet, title=worksheet_name, rows=1, cols=len(headers), _idempotent=False)
                self._execute_with_retry(worksheet.append_row, headers, value_input_option='USER_ENTERED', _idempotent=False)
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
                worksheet = self._execute_with_retry(spreadsheet.add_worksheet, title=worksheet_name, rows=1, cols=len(data), _idempotent=False)
                self._execute_with_retry(worksheet.append_row, data, value_input_option='USER_ENTERED', _idempotent=False)
                return True

            key_to_find = data[key_column_index]
            cell_list = self._execute_with_retry(worksheet.findall, key_to_find, in_column=key_column_index + 1)

            if cell_list:
                # Key found, update the first occurrence. Writing fixed values to
                # a fixed range is idempotent — a replay lands on the same cells
                # with the same data — so this keeps the full retry set.
                row_index = cell_list[0].row
                self._execute_with_retry(worksheet.update, f'A{row_index}', [data], value_input_option='USER_ENTERED')
                logger.info(f"Updated row {row_index} for key '{key_to_find}' in '{worksheet_name}'.")
            else:
                # Key not found, append new row
                self._execute_with_retry(worksheet.append_row, data, value_input_option='USER_ENTERED', _idempotent=False)
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

            # Delete from bottom to top so row indices don't shift.
            #
            # These indices are absolute and were resolved by the findall above,
            # so this is the least replayable call in the class: if a delete
            # commits and only its response is lost, the row that slid into that
            # index belongs to a different record. Never retry it on a 5xx.
            rows_to_delete = sorted([cell.row for cell in cell_list], reverse=True)
            for row_index in rows_to_delete:
                self._execute_with_retry(worksheet.delete_rows, row_index, _idempotent=False)

            logger.info(f"Deleted {len(rows_to_delete)} rows for key '{key_value}' in '{worksheet_name}'.")
            return True
        except TransientAPIError:
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

            # target_column_index is 0-based, update_cell expects 1-based column.
            # Fixed cell, fixed value: a replay is a no-op, so the full retry set
            # applies.
            self._execute_with_retry(worksheet.update_cell, cell.row, target_column_index + 1, new_value)
            logger.info(f"Updated column {target_column_index + 1} in row {cell.row} for key '{key_value}' in '{worksheet_name}'.")
            return True
        except TransientAPIError:
            raise
        except APIError as e:
            logger.error(f"A gspread API error occurred while updating cell in '{worksheet_name}': {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error updating cell in '{worksheet_name}': {str(e)}")
            return False


# Global instance
google_drive_service = GoogleDriveService()
