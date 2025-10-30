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
import json
import gspread
import logging
from datetime import datetime

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

            if not self.google_service.test_connection(self.spreadsheet_id):
                logging.error(f"Cannot connect to spreadsheet: {self.spreadsheet_id}")
                return DropdownData()

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
                return True

            df = self._get_all_dropdown_data()
            if df is None or df.empty or "Coil Number" not in df.columns:
                return True

            existing_coils = df["Coil Number"].astype(str).str.strip().str.lower()
            return coil_number.strip().lower() not in existing_coils.values

        except Exception as e:
            logger.error(f"Error checking coil number uniqueness: {str(e)}")
            return True

    def create_rm_inward_issue(self, request: RMInwardIssueRequest) -> bool:
        """Create a new RM Inward Issue record"""
        return self.create_rm_inward_issues_bulk([request])

    def create_rm_inward_issues_bulk(
        self, requests: List[RMInwardIssueRequest]
    ) -> bool:
        """Create multiple new RM Inward Issue records in a single API call."""
        try:
            if not self.google_service.client:
                raise Exception("Google Drive client not initialized")

            if not requests:
                logger.info("No records to add.")
                return True

            data_rows = []
            for request in requests:
                record = RMInwardIssueRecord(**request.dict())
                data_rows.append(record.to_list())

            success = self.google_service.insert_row_before_last(
                self.spreadsheet_id, "RM inward_Issue format", data_rows
            )

            if success:
                logger.info(
                    f"Successfully added {len(data_rows)} records to Google Sheets!"
                )
                return True
            else:
                logger.error("Failed to add bulk data to Google Sheets")
                return False

        except Exception as e:
            logger.error(f"Failed to create bulk RM Inward Issue: {str(e)}")
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

    def get_mapping_templates(self) -> Dict[str, Dict[str, Any]]:
        """Get all saved mapping templates from the 'Mapping Templates' sheet."""
        try:
            df = self.google_service.get_worksheet_data(
                self.spreadsheet_id, "Mapping Templates", header_row=1
            )
            if (
                df.empty
                or "TemplateName" not in df.columns
                or "MappingJSON" not in df.columns
            ):
                logger.warning(
                    f"Mapping Templates sheet is missing required headers. Found: {df.columns.tolist()}"
                )
                return {}

            templates = {}
            for _, row in df.iterrows():
                try:
                    templates[row["TemplateName"]] = json.loads(row["MappingJSON"])
                except (json.JSONDecodeError, TypeError):
                    continue
            return templates
        except gspread.exceptions.WorksheetNotFound:
            logger.info(
                "'Mapping Templates' worksheet not found. Returning empty templates."
            )
            return {}
        except Exception as e:
            logger.error(f"Error getting mapping templates: {str(e)}")
            return {}

    def save_mapping_template(
        self, template_name: str, mapping: Dict[str, Any]
    ) -> bool:
        """Save a mapping template to the 'Mapping Templates' sheet."""
        try:
            worksheet_name = "Mapping Templates"
            headers = ["TemplateName", "MappingJSON"]
            spreadsheet = self.google_service.client.open_by_key(self.spreadsheet_id)

            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
                all_values = worksheet.get_all_values()
                if not all_values:
                    worksheet.append_row(headers, value_input_option="USER_ENTERED")
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=worksheet_name, rows=1, cols=2
                )
                worksheet.append_row(headers, value_input_option="USER_ENTERED")

            mapping_json = json.dumps(mapping)
            data_row = [template_name, mapping_json]

            return self.google_service.upsert_row(
                self.spreadsheet_id, worksheet_name, data_row, key_column_index=0
            )
        except Exception as e:
            logger.error(f"Error saving mapping template: {str(e)}")
            return False

    def generate_coil_number(self, grade: str, coating: str, width: Any) -> str:
        """Generates a new coil number based on properties and a timestamp."""
        from datetime import datetime

        timestamp_str = (
            datetime.now().strftime("%d%m%y:%H:%M:%S:")
            + f"{datetime.now().microsecond // 1000:03d}"
        )
        return f"{grade}-{coating}-{width}-{timestamp_str}"

    def validate_single_entry(self, form_data: Dict[str, Any]) -> List[str]:
        """Validates the data from the single entry form."""
        errors = []
        if form_data.get("receipt_date") > datetime.now().date():
            errors.append("Receipt Date cannot be in the future.")

        required_fields = {
            "RM Type": "rm_type",
            "Grade": "grade",
            "Thk (mm)": "thk",
            "Width (mm)": "width",
            "Coating": "coating",
            "Coil Supplier": "supplier",
        }
        for field_name, key in required_fields.items():
            if not form_data.get(key):
                errors.append(f"Please select or enter a value for '{field_name}'.")

        if not form_data.get("coil_number", "").strip():
            errors.append("Please enter a Coil Number.")
        if form_data.get("coil_weight", 0) <= 0:
            errors.append("Coil Weight must be greater than zero.")

        try:
            if form_data.get("thk"):
                float(form_data["thk"])
        except (ValueError, TypeError):
            errors.append("Thk must be a valid number.")
        try:
            if form_data.get("width"):
                int(form_data["width"])
        except (ValueError, TypeError):
            errors.append("Width must be a valid number.")

        if not errors:
            if not self.is_coil_number_unique(form_data["coil_number"].strip()):
                errors.append(
                    f"Coil Number '{form_data['coil_number']}' already exists."
                )

        return errors

    def group_df_by_key(
        self, df: pd.DataFrame, group_by_col: str, mapping: Dict[str, str]
    ) -> pd.DataFrame:
        """Groups a DataFrame by a specified key, summing weights and taking first for others."""
        agg_functions = {
            excel_col: "first"
            for _, excel_col in mapping.items()
            if excel_col and excel_col in df.columns
        }
        weight_col_mapped = mapping.get("coil_weight")
        if weight_col_mapped and weight_col_mapped in df.columns:
            agg_functions[weight_col_mapped] = "sum"
        if group_by_col in agg_functions:
            del agg_functions[group_by_col]

        return df.groupby(group_by_col).agg(agg_functions).reset_index()

    def process_bulk_upload_df(
        self, df: pd.DataFrame, mapping: Dict, options: Dict, existing_coils: set
    ) -> tuple[list, list]:
        """Processes the bulk upload dataframe, returning valid requests and failed records."""
        from pydantic import ValidationError

        valid_requests = []
        failed_records = []
        batch_timestamp = datetime.now().strftime("%d%m%y%H%M%S")

        for index, row in df.iterrows():
            try:
                request_data = {"user_id": options.get("user_email", "")}
                for field_key, excel_col in mapping.items():
                    if (
                        excel_col
                        and excel_col != "auto-generate"
                        and excel_col in row
                        and pd.notna(row[excel_col])
                    ):
                        request_data[field_key] = row[excel_col]

                if options.get("auto_generate_coil") or options.get("group_by_col"):
                    grade = row[mapping["grade"]]
                    coating = row[mapping["coating"]]
                    width = row[mapping["width"]]
                    sequence = index + 1
                    request_data["coil_number"] = (
                        f"{grade}-{coating}-{width}-{batch_timestamp}-{sequence}"
                    )

                if not mapping.get("coil_location") or pd.isna(
                    request_data.get("coil_location")
                ):
                    request_data["coil_location"] = "Amba"
                if not mapping.get("po_number") or pd.isna(
                    request_data.get("po_number")
                ):
                    request_data["po_number"] = None

                coil_num_str = str(request_data.get("coil_number", "")).strip().lower()
                if not coil_num_str:
                    raise ValueError(
                        "Coil Number is missing or could not be generated."
                    )
                if coil_num_str in existing_coils:
                    raise ValueError(f"Coil Number '{coil_num_str}' already exists.")

                request_obj = RMInwardIssueRequest(**request_data)
                valid_requests.append(request_obj)
                existing_coils.add(coil_num_str)

            except (ValidationError, ValueError, Exception) as e:
                failed_records.append(
                    {
                        "Row": index + 2,
                        "Coil Number": str(
                            request_data.get(
                                "coil_number",
                                row.get(mapping.get("coil_number"), "N/A"),
                            )
                        ),
                        "Error": str(e),
                    }
                )
        return valid_requests, failed_records
