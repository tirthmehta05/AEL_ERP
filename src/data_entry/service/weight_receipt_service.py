from typing import List, Optional
from src.shared.utils.logger_config import setup_logger
from src.data_entry.repository.weight_receipt_repository import WeightReceiptRepository
from src.data_entry.models.weight_receipt_models import WeightReceiptRequest, WeightReceiptRecord
from datetime import date, datetime, timedelta
import json
import pandas as pd
import requests
import gspread
from config import settings
from src.shared.integrations.google_drive_service import google_drive_service

logger = setup_logger(__name__)

class WeightReceiptService:
    # Internal cache for all weight receipts data to reduce API calls for number generation
    _cached_all_weight_receipts_df: Optional[pd.DataFrame] = None
    _cached_all_weight_receipts_timestamp: Optional[datetime] = None
    _CACHE_TTL_SECONDS = 5 # Cache lifetime

    def __init__(self):
        self.repository = WeightReceiptRepository()
        self.weighing_scale_api_url = settings.api.weighing_scale_url
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id

    def _get_or_refresh_all_weight_receipts(self, force_refresh: bool = False) -> pd.DataFrame:
        """
        Retrieves all weight receipts from the repository, using an internal cache.
        If the cache is stale or force_refresh is True, it fetches new data.
        """
        current_time = datetime.now()
        if (
            not force_refresh and
            self._cached_all_weight_receipts_df is not None and
            self._cached_all_weight_receipts_timestamp is not None and
            (current_time - self._cached_all_weight_receipts_timestamp).total_seconds() < self._CACHE_TTL_SECONDS
        ):
            logger.debug("Using cached all weight receipts DataFrame.")
            return self._cached_all_weight_receipts_df
        
        logger.debug("Refreshing all weight receipts DataFrame (cache stale or forced).")
        df = self.repository.get_all_weight_receipts()
        self._cached_all_weight_receipts_df = df
        self._cached_all_weight_receipts_timestamp = current_time
        return df

    def get_next_weight_receipt_number(self) -> int:
        """
        Generates the next sequential weight receipt number.
        Starts from 10315 if no higher numeric-only number is found.
        """
        try:
            # Use the internally cached DataFrame
            df = self._get_or_refresh_all_weight_receipts()
            
            if df is None or df.empty or "WeightReceiptNumber" not in df.columns:
                return 10315

            max_receipt_num = 10314  # The base number to compare against
            
            # Filter for strings that are purely numeric, then convert and find max
            numeric_receipts = pd.to_numeric(df['WeightReceiptNumber'], errors='coerce').dropna()
            
            if not numeric_receipts.empty:
                current_max = numeric_receipts.max()
                if current_max > max_receipt_num:
                    max_receipt_num = int(current_max)
            
            return max_receipt_num + 1

        except Exception as e:
            logger.error(f"Error generating next weight receipt number: {e}")
            # Fallback to a timestamp-based unique number in case of error
            return int(datetime.now().timestamp())

    def generate_weight_receipt_number(self) -> str:
        """Generates a new sequential weight receipt number as a string."""
        return str(self.get_next_weight_receipt_number())

    def save_weight_receipt(self, request: WeightReceiptRequest) -> bool:
        """Saves a new weight receipt."""
        try:
            # Calculate total deduction from design-level deductions
            total_design_deduction = sum(d.design_deduction or 0.0 for d in request.designs)
            
            # Hybrid Logic: 
            # If user entered a Total Deduction > 0, use it (it takes precedence).
            # Otherwise, use the sum of individual design deductions.
            if request.deduction <= 0:
                request.deduction = total_design_deduction
            
            # Prepare the list of design dictionaries for JSON serialization
            designs_to_dump = []
            for d in request.designs:
                design_dict = d.model_dump()
                # Ensure 'remark' is never None before dumping to JSON
                if design_dict.get('remark') is None:
                    design_dict['remark'] = ''
                designs_to_dump.append(design_dict)

            designs_json = json.dumps(designs_to_dump)
            
            record = WeightReceiptRecord(
                weight_receipt_number=request.weight_receipt_number,
                receipt_date=request.receipt_date,
                job_card_number=request.job_card_number,
                party_name=request.party_name,
                po_no=request.po_no,
                material=request.material,
                sets=request.sets,
                designs_json=designs_json,
                weight_entry_type=request.weight_entry_type,
                total_weight=request.total_weight,
                deduction=request.deduction,
            )

            success = self.repository.save_weight_receipt(record.to_list())
            
            if success:
                logger.info(f"Successfully saved Weight Receipt {request.weight_receipt_number}")
                self._get_or_refresh_all_weight_receipts(force_refresh=True) # Refresh cache after save
                return True
            else:
                logger.error(f"Failed to save Weight Receipt {request.weight_receipt_number}.")
                return False
        except Exception as e:
            logger.error(f"Error saving weight receipt: {str(e)}")
            return False

    def get_weight_receipts_for_party_and_date_range(self, party_name: str, start_date: date, end_date: date) -> List[dict]:
        """Fetches weight receipts for a specific party within a date range."""
        try:
            df = self.repository.get_all_weight_receipts()
            if df.empty:
                return []

            df['Date'] = pd.to_datetime(df['Date'], errors='coerce', dayfirst=True).dt.date
            
            # Ensure PartyName is string, lowercase, and stripped for robust comparison
            df['PartyName'] = df['PartyName'].astype(str).str.lower().str.strip()
            processed_party_name = party_name.lower().strip()

            filtered_df = df[
                (df['PartyName'] == processed_party_name) &
                (df['Date'] >= start_date) &
                (df['Date'] <= end_date)
            ]
            return filtered_df.to_dict('records')
        except Exception as e:
            logger.error(f"Error fetching weight receipts for party {party_name}: {str(e)}")
            return []

    def get_current_weight_from_scale(self) -> dict:
        """
        Fetches the current weight from the external weighing scale API.
        Returns a dict with 'success', 'weight', and 'status'.
        """
        if not self.weighing_scale_api_url:
            logger.error("Weighing scale API URL is not configured.")
            return {"success": False, "weight": 0.0, "status": "unconfigured"}

        headers = {
            "ngrok-skip-browser-warning": "69420"
        }

        try:
            response = requests.get(self.weighing_scale_api_url, headers=headers, timeout=10)
            response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
            data = response.json()
            return {
                "success": data.get("success", False),
                "weight": abs(data.get("weight", 0.0)),
                "status": data.get("status", "unknown")
            }
        except requests.exceptions.Timeout:
            logger.error(f"Weighing scale API request timed out after 5 seconds.")
            return {"success": False, "weight": 0.0, "status": "timeout"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to weighing scale API: {e}")
            return {"success": False, "weight": 0.0, "status": "error"}
        except ValueError: # Catches JSON decode errors
            logger.error(f"Weighing scale API returned invalid JSON: {response.text}")
            return {"success": False, "weight": 0.0, "status": "invalid_response"}
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching weight: {e}")
            return {"success": False, "weight": 0.0, "status": "unexpected_error"}

    def get_receipted_sets_for_job_card(self, job_card_number: str) -> int:
        """
        Calculates the total number of sets for which a weight receipt has already been created for a given job card.
        """
        try:
            df = self.repository.get_all_weight_receipts()
            if df is None or df.empty:
                return 0

            # Filter for the specific job card
            df['JobCardNumber'] = df['JobCardNumber'].astype(str).str.strip().str.lower()
            processed_job_card_number = job_card_number.strip().lower()
            jc_receipts = df[df['JobCardNumber'] == processed_job_card_number]
            if jc_receipts.empty:
                return 0

            # The 'Sets' column might be read as object/string, so convert to numeric.
            # errors='coerce' will turn any non-numeric values into NaN, which are then ignored by sum().
            total_sets = pd.to_numeric(jc_receipts['Sets'], errors='coerce').sum()
            
            return int(total_sets)
        except Exception as e:
            logger.error(f"Error calculating receipted sets for JC {job_card_number}: {e}")
            return 0
    
    def get_cumulative_weight_for_job_card(self, job_card_number: str) -> float:
        """
        Calculates the total cumulative weight already receipted for a given job card.
        This is used for partial dispatch orders (loose strips and EI ready).
        """
        try:
            # Query Finished Goods Transfer sheet
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Finished Goods Transfer", header_row=2)
            if df is None or df.empty or 'Job Card' not in df.columns or 'FG Qty' not in df.columns:
                return 0.0
            
            # Filter for the specific job card
            df['Job Card'] = df['Job Card'].astype(str).str.strip().str.lower()
            processed_job_card_number = job_card_number.strip().lower()
            jc_entries = df[df['Job Card'] == processed_job_card_number]
            if jc_entries.empty:
                return 0.0
            
            # Sum all FG Qty entries
            cumulative_weight = pd.to_numeric(jc_entries['FG Qty'], errors='coerce').sum()
            return float(cumulative_weight) if not pd.isna(cumulative_weight) else 0.0
        except Exception as e:
            logger.error(f"Error calculating cumulative weight for JC {job_card_number}: {e}")
            return 0.0
    
    def get_material_type_for_job_card(self, job_card_number: str) -> str:
        """
        Looks up the material type for a job card from the flat 'Sales Order' sheet.
        The Sales Order-JC sheet does not store material type, so we read it from
        the per-design rows in 'Sales Order' where it lives in the 'type' column.
        Returns an empty string if no match is found.
        """
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order", header_row=1)
            if df is None or df.empty:
                return ""

            # Identify the job card column (varies in casing/naming across writes)
            jc_col = None
            for candidate in ("Job Card", "job_card_number", "Job Card No", "job_card", "JobCard"):
                if candidate in df.columns:
                    jc_col = candidate
                    break
            if jc_col is None:
                logger.warning("get_material_type_for_job_card: no recognizable Job Card column in 'Sales Order' sheet.")
                return ""

            # Identify the material/type column
            type_col = None
            for candidate in ("type", "Type", "material_type", "Material Type", "Material"):
                if candidate in df.columns:
                    type_col = candidate
                    break
            if type_col is None:
                logger.warning("get_material_type_for_job_card: no recognizable type/material column in 'Sales Order' sheet.")
                return ""

            df[jc_col] = df[jc_col].astype(str).str.strip().str.lower()
            jc_rows = df[df[jc_col] == job_card_number.strip().lower()]
            if jc_rows.empty:
                return ""

            value = jc_rows.iloc[0].get(type_col)
            return "" if pd.isna(value) else str(value).strip()
        except Exception as e:
            logger.error(f"Error in get_material_type_for_job_card for JC {job_card_number}: {e}")
            return ""

    def get_order_type_for_job_card(self, job_card_number: str) -> str:
        """
        Retrieves the order type for a given job card from the Sales Order-JC sheet.
        If order_type is missing, infers it from number_of_cores and designs.
        Returns "CORE_BUILDING" as safe default.
        """
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order-JC", header_row=1)
            if df is None or df.empty or 'job_card_number' not in df.columns:
                return "CORE_BUILDING"
            
            # Find the job card
            df['job_card_number'] = df['job_card_number'].astype(str).str.strip().str.lower()
            processed_job_card_number = job_card_number.strip().lower()
            jc_row = df[df['job_card_number'] == processed_job_card_number]
            if jc_row.empty:
                return "CORE_BUILDING"
            
            # Check if order_type column exists and has a value
            if 'order_type' in df.columns:
                order_type = jc_row.iloc[0]['order_type']
                if pd.notna(order_type) and order_type in ["CORE_BUILDING", "LOOSE_STRIPS", "EI_READY"]:
                    return str(order_type)
            
            # Fallback: infer from number_of_cores and designs
            # Check designs for "Ready Entry"
            if 'designs_json' in df.columns:
                designs_json = jc_row.iloc[0].get('designs_json')
                if pd.notna(designs_json):
                    try:
                        designs = json.loads(designs_json)
                        for design in designs:
                            if design.get('hole') == "Ready Entry":
                                return "EI_READY"
                    except:
                        pass
            
            # Check number_of_cores
            if 'number_of_cores' in df.columns:
                num_cores = pd.to_numeric(jc_row.iloc[0].get('number_of_cores'), errors='coerce')
                if pd.notna(num_cores) and num_cores == 0:
                    return "LOOSE_STRIPS"
            
            # Default to CORE_BUILDING
            return "CORE_BUILDING"
        except Exception as e:
            logger.error(f"Error getting order type for JC {job_card_number}: {e}")
            return "CORE_BUILDING"

    def save_weight_receipt_draft(self, job_card: str, design_index: int, weight: float, remark: str, sets_for_this_receipt: int, design_deduction: float = 0.0) -> bool:
        """Saves a single design's weighed data to a draft sheet."""
        try:
            sheet_name = "Weight Receipt Draft"
            headers = ["JobCardNumber", "DesignIndex", "ActualWeight", "Timestamp", "ReceiptSets", "Remark", "DesignDeduction"]
            self.google_service.ensure_worksheet_with_headers(self.spreadsheet_id, sheet_name, headers)

            timestamp = datetime.now().isoformat()
            
            # Explicitly cast all data to standard Python types to prevent serialization errors.
            row_data = [
                str(job_card), 
                int(design_index), 
                float(weight), 
                str(timestamp), 
                int(sets_for_this_receipt), 
                str(remark),
                float(design_deduction)
            ]

            success = self.google_service.append_data(self.spreadsheet_id, sheet_name, [row_data])
            
            if success:
                logger.info(f"Successfully saved draft for JC {job_card}, Design {design_index}.")
                return True
            else:
                logger.error(f"Failed to save draft for JC {job_card}, Design {design_index}.")
                return False
        except Exception as e:
            logger.error(f"Error in save_weight_receipt_draft for JC {job_card}: {e}")
            return False

    def get_weight_receipt_drafts(self, job_card: str) -> tuple[dict, int | None, float | None, str | None]:
        """
        Retrieves the latest draft data for a given job card.
        Returns a tuple: (
            dictionary mapping design_index to its data (including design_deduction),
            the number of sets for the draft session,
            the total weight if a 'Building Core' draft exists,
            the remark if a 'Building Core' draft exists
        ).
        """
        try:
            sheet_name = "Weight Receipt Draft"
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, sheet_name)
            if df is None or df.empty or 'JobCardNumber' not in df.columns:
                return {}, None, None, None

            # Filter for the job card and ensure correct types
            drafts_df = df[df['JobCardNumber'] == job_card].copy()
            if drafts_df.empty:
                return {}, None, None, None

            drafts_df['Timestamp'] = pd.to_datetime(drafts_df['Timestamp'], errors='coerce')
            drafts_df['DesignIndex'] = pd.to_numeric(drafts_df['DesignIndex'], errors='coerce')
            drafts_df.dropna(subset=['Timestamp', 'DesignIndex'], inplace=True)
            drafts_df['DesignIndex'] = drafts_df['DesignIndex'].astype(int)

            # Find the ReceiptSets value from the single most recent entry
            latest_entry = drafts_df.sort_values('Timestamp', ascending=False).iloc[0]
            draft_sets_value = int(pd.to_numeric(latest_entry.get('ReceiptSets'), errors='coerce'))

            # Separate Building Core drafts (index -1) from Loose Strips drafts
            core_drafts = drafts_df[drafts_df['DesignIndex'] == -1]
            loose_strip_drafts = drafts_df[drafts_df['DesignIndex'] >= 0]

            # Get the latest total weight and remark if a core draft exists
            draft_total_weight = None
            draft_core_remark = None
            if not core_drafts.empty:
                latest_core_draft = core_drafts.sort_values('Timestamp', ascending=False).iloc[0]
                draft_total_weight = pd.to_numeric(latest_core_draft['ActualWeight'], errors='coerce')
                draft_core_remark = str(latest_core_draft.get('Remark', '')) if pd.notna(latest_core_draft.get('Remark')) else ''

            # Sort by timestamp and get the latest entry for each loose strip design index
            latest_drafts_per_design = loose_strip_drafts.sort_values('Timestamp', ascending=False).drop_duplicates(subset=['DesignIndex'], keep='first')

            # Format loose strips into the required dictionary structure
            result = {}
            for _, row in latest_drafts_per_design.iterrows():
                # Ensure remark is a string, default to empty string if it's missing or not a string type
                remark = str(row.get('Remark', '')) if pd.notna(row.get('Remark')) else ''
                # Get design_deduction, default to 0.0 if column doesn't exist or value is missing
                design_deduction = pd.to_numeric(row.get('DesignDeduction', 0.0), errors='coerce')
                design_deduction = design_deduction if pd.notna(design_deduction) else 0.0

                result[row['DesignIndex']] = {
                    'weight': pd.to_numeric(row['ActualWeight'], errors='coerce'),
                    'remark': remark,
                    'design_deduction': design_deduction,
                    'sets': int(row.get('ReceiptSets', 1))
                }
            return result, draft_sets_value, draft_total_weight, draft_core_remark
        except Exception as e:
            logger.error(f"Error in get_weight_receipt_drafts for JC {job_card}: {e}")
            return {}, None, None, None

    def clear_weight_receipt_drafts(self, job_card: str) -> bool:
        """Removes all draft entries for a given job card from the draft sheet."""
        try:
            sheet_name = "Weight Receipt Draft"
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, sheet_name)
            if df is None or df.empty:
                return True # Nothing to clear

            # Keep only the rows that DO NOT match the job card
            remaining_drafts_df = df[df['JobCardNumber'] != job_card]

            # Get all values from the filtered dataframe, including headers
            values_to_write_back = [remaining_drafts_df.columns.values.tolist()] + remaining_drafts_df.values.tolist()

            worksheet = self.google_service.client.open_by_key(self.spreadsheet_id).worksheet(sheet_name)
            worksheet.clear()
            worksheet.update(values_to_write_back, 'A1')
            
            logger.info(f"Cleared drafts for Job Card {job_card}.")
            return True
        except Exception as e:
            logger.error(f"Error clearing drafts for JC {job_card}: {e}")
            return False

    def clear_drafts_for_design_indices(self, job_card: str, design_indices: list[int]) -> bool:
        """Removes draft entries only for specified design indices of a job card.
        
        Preserves drafts for designs not in the list, so they can be
        loaded again later without re-weighing.
        """
        try:
            sheet_name = "Weight Receipt Draft"
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, sheet_name)
            if df is None or df.empty:
                return True

            df['DesignIndex'] = pd.to_numeric(df['DesignIndex'], errors='coerce')

            # Keep rows that either:
            # 1. Don't belong to this job card, OR
            # 2. Belong to this job card but their design index is NOT in the list
            is_target_row = (df['JobCardNumber'] == job_card) & (df['DesignIndex'].isin(design_indices))
            remaining_drafts_df = df[~is_target_row]

            values_to_write_back = [remaining_drafts_df.columns.values.tolist()] + remaining_drafts_df.values.tolist()

            worksheet = self.google_service.client.open_by_key(self.spreadsheet_id).worksheet(sheet_name)
            worksheet.clear()
            worksheet.update(values_to_write_back, 'A1')

            logger.info(f"Cleared drafts for JC {job_card}, design indices {design_indices}.")
            return True
        except Exception as e:
            logger.error(f"Error clearing drafts for JC {job_card}, indices {design_indices}: {e}")
            return False

    def save_to_finished_goods(self, user_id: str, job_card: str, fg_qty: float, weight_receipt_number: str) -> bool:
        """
        Saves a record to the 'Finished Goods Transfer' sheet, ensuring headers are on row 2
        and the new data is inserted before the last row. This version accounts for formula columns.
        """
        try:
            sheet_name = "Finished Goods Transfer"
            
            # Ensure the worksheet exists and is properly initialized
            if not self.google_service.client:
                raise Exception("Google Drive client not initialized")
            
            spreadsheet = self.google_service._execute_with_retry(
                self.google_service.client.open_by_key, 
                self.spreadsheet_id
            )
            
            # Try to get the worksheet, create if it doesn't exist
            try:
                worksheet = self.google_service._execute_with_retry(
                    spreadsheet.worksheet, 
                    sheet_name
                )
                
                # Check if headers exist on row 2, add if missing
                cell_value = self.google_service._execute_with_retry(
                    worksheet.acell, 
                    'A2'
                ).value
                
                if not cell_value:
                    # Headers don't exist, add them to row 2
                    headers = [
                        "USERID", "FG DATE", "Job Card", "FG Qty",  # Columns A, B, C, D
                        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,  # 18 placeholders for E-V
                        "Weight Receipt Number"  # Column W
                    ]
                    self.google_service._execute_with_retry(
                        worksheet.update, 
                        'A2', 
                        [headers]
                    )
                    
            except gspread.exceptions.WorksheetNotFound:
                # Worksheet doesn't exist, create it
                worksheet = self.google_service._execute_with_retry(
                    spreadsheet.add_worksheet, 
                    title=sheet_name, 
                    rows=100, 
                    cols=30
                )
                
                # Add headers to row 2
                headers = [
                    "USERID", "FG DATE", "Job Card", "FG Qty",  # Columns A, B, C, D
                    None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,  # 18 placeholders for E-V
                    "Weight Receipt Number"  # Column W
                ]
                self.google_service._execute_with_retry(
                    worksheet.update, 
                    'A2', 
                    [headers]
                )

            fg_date = datetime.now().strftime("%Y-%m-%d")
            
            # Use None for placeholder values to avoid overwriting formulas in the new row.
            row_data = [
                user_id, fg_date, job_card, fg_qty,
                None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                weight_receipt_number
            ]

            # Use the service's insert_row_before_last method which handles retries
            success = self.google_service.insert_row_before_last(self.spreadsheet_id, sheet_name, [row_data])
            
            if success:
                logger.info(f"Successfully saved Job Card {job_card} to {sheet_name}.")
                return True
            else:
                logger.error(f"Failed to save Job Card {job_card} to {sheet_name}.")
                return False
        except Exception as e:
            logger.error(f"Error in save_to_finished_goods for JC {job_card}: {e}")
            return False

