from typing import List
import requests
import msal
from src.shared.utils.logger_config import setup_logger
from src.shared.integrations.google_drive_service import google_drive_service
from src.data_entry.models.sales_order_models import SalesOrderRequest, SalesOrderDropdownData, PowerAutomatePlannerRequest
from src.data_entry.service.rm_used_service import RMUsedService
from src.data_entry.models.rm_used_models import RMUsedRequest
from config import settings

from datetime import date, datetime

import json
import pandas as pd

logger = setup_logger(__name__)

class SalesOrderService:
    def __init__(self, pa_client_id: str, pa_client_secret: str, pa_tenant_id: str):
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id
        self.rm_used_service = RMUsedService()
        self.pa_client_id = pa_client_id
        self.pa_client_secret = pa_client_secret
        self.pa_tenant_id = pa_tenant_id

    def generate_job_card_number(self, type: str) -> str:
        """Generates a new unique Job Card number based on the type (CRNO/CRNGO)."""
        prefix = "N-" if type == "CRNO" else "G-"
        start_number = 6160

        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order-JC", header_row=1)
            if df.empty or 'job_card_number' not in df.columns:
                return f"{prefix}{start_number}"

            # Filter job card numbers for the given type
            jc_series = df['job_card_number'][df['job_card_number'].str.startswith(prefix, na=False)]

            if jc_series.empty:
                return f"{prefix}{start_number}"

            # Extract numbers, convert to int, and find max
            max_num = jc_series.str.split('-').str[1].astype(int).max()
            
            if max_num < start_number:
                return f"{prefix}{start_number}"

            next_num = max_num + 1
            return f"{prefix}{next_num}"
        except Exception as e:
            logger.error(f"Error generating job card number: {str(e)}")
            # Fallback to a safe, but different, format to avoid duplicates
            return f"{prefix}{datetime.now().strftime('%y%m%d%H%M%S')}"


    def get_dropdown_data(self) -> SalesOrderDropdownData:
        """Fetches dropdown data for the Sales Order form."""
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order", header_row=1)
            if df.empty:
                return SalesOrderDropdownData()

            party_names = []
            if "Party Name" in df.columns:
                party_names = sorted(df["Party Name"].dropna().unique().tolist())
            
            hole_sizes = []
            if "Hole Size" in df.columns:
                # Ensure values are integers
                hole_sizes = sorted([int(s) for s in df["Hole Size"].dropna().unique() if str(s).isdigit()])

            coatings = []
            if "Coating" in df.columns:
                coatings = sorted(df["Coating"].dropna().unique().tolist())

            return SalesOrderDropdownData(party_names=party_names, hole_sizes=hole_sizes, coatings=coatings)
        except Exception as e:
            logger.error(f"Error getting dropdown data for Sales Order: {str(e)}")
            return SalesOrderDropdownData()

    def save_sales_order(self, request: SalesOrderRequest) -> bool:
        """Saves a new sales order entry to the 'Sales Order-JC' sheet and the 'Sales Order' sheet."""
        try:
            request.job_card_number = self.generate_job_card_number(request.designs[0].type)

            worksheet_name_jc = "Sales Order-JC"
            headers_jc = [
                "order_date", "po_no", "party_name", "delivery_date", "job_card_number",
                "hole_size", "number_of_cores", "rate_per_kg", "header_core_stack", "coating", "designs_json",
                "status"
            ]
            self.google_service.ensure_worksheet_with_headers(self.spreadsheet_id, worksheet_name_jc, headers_jc)

            designs_json = json.dumps([d.model_dump() for d in request.designs])
            
            status = "Coils Assigned" if request.assigned_coils else "Pending Coil Assignment"

            data_row_jc = [
                request.order_date.strftime("%Y-%m-%d"), request.po_no, request.party_name,
                request.delivery_date.strftime("%Y-%m-%d"), request.job_card_number,
                request.hole_size, request.number_of_cores, request.rate_per_kg,
                request.header_core_stack, request.coating, designs_json, status
            ]

            success_jc = self.google_service.append_data(self.spreadsheet_id, worksheet_name_jc, [data_row_jc])
            if not success_jc:
                logger.error(f"Failed to save new Sales Order to {worksheet_name_jc}.")
                return False

            # Save design details to the main 'Sales Order' sheet
            sales_order_rows = []
            for design in request.designs:
                sales_order_rows.append([
                    request.job_card_number, request.order_date.strftime("%m/%d/%Y"), request.po_no,
                    design.party_job_no, request.party_name, design.width, design.length, design.mm_stack,
                    design.mm_stack, request.hole_size, None, design.sets, design.sets, design.type,
                    design.thk, request.rate_per_kg, request.delivery_date.strftime("%m/%d/%Y"), None
                ])
            
            logger.info(f"Attempting to save {len(sales_order_rows)} rows to 'Sales Order' sheet.")
            success_so = self.google_service.append_data(self.spreadsheet_id, "Sales Order", sales_order_rows)

            if not success_so:
                logger.error(f"Failed to save design details for SO {request.job_card_number}.")
                return False

            # Conditionally create Raw Material Used entries
            if request.assigned_coils:
                for assigned_coil in request.assigned_coils:
                    rm_used_request = RMUsedRequest(
                        rm_used_date=datetime.now().date(),
                        card_no=request.job_card_number,
                        coil_no=assigned_coil.coil_no,
                        weight=assigned_coil.weight_used,
                        machine='',
                        remarks='Slitting'
                    )
                    self.rm_used_service.create_rm_used(rm_used_request)

            logger.info(f"Successfully saved Sales Order {request.job_card_number} and all related entries.")
            return True
        except Exception as e:
            logger.error(f"Error saving sales order: {str(e)}")
            return False

    def invoke_power_automate_flow(self, request: SalesOrderRequest):
        """Invokes the Power Automate flow to create a new task in Planner."""
        try:
            power_automate_url = "https://default86082795378140f4a43d78edf0f958.cf.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/ab661c7ddcdf4d889726125b8c0e52d9/triggers/manual/paths/invoke?api-version=1"
            
            planner_request = PowerAutomatePlannerRequest(
                companyName=request.party_name,
                jobNumber=request.job_card_number,
                poNumber=request.po_no,
                jobDate=request.order_date.strftime("%Y-%m-%d"),
                orderType="MFG"
            )
            data = planner_request.model_dump()

            authority = f"https://login.microsoftonline.com/{self.pa_tenant_id}"
            scope = ["https://service.flow.microsoft.com//.default"]

            app = msal.ConfidentialClientApplication(
                client_id=self.pa_client_id,
                client_credential=self.pa_client_secret,
                authority=authority
            )

            result = app.acquire_token_for_client(scopes=scope)

            if "access_token" in result:
                headers = {
                    'Authorization': f'Bearer {result["access_token"]}',
                    'Content-Type': 'application/json'
                }
                response = requests.post(power_automate_url, headers=headers, json=data)
                response.raise_for_status()  # Raise an exception for bad status codes
                logger.info(f"Successfully invoked Power Automate flow for job card {request.job_card_number}.")
            else:
                logger.error(f"Failed to acquire access token for Power Automate flow. Error: {result.get('error_description')}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error invoking Power Automate flow: {str(e)}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during Power Automate invocation: {str(e)}")

    def get_sales_orders_for_job_card(self, start_date=None, end_date=None, include_designs: bool = False) -> List[dict]:
        """Fetches sales orders from the 'Sales Order-JC' sheet, optionally filtered by date."""
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order-JC", header_row=1)
            if df.empty:
                return []

            # Convert order_date to datetime for filtering
            df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')

            # Filter by date range if provided
            if start_date:
                df = df[df['order_date'].dt.date >= start_date]
            if end_date:
                df = df[df['order_date'].dt.date <= end_date]
            
            if not include_designs:
                if 'designs_json' in df.columns:
                    df = df.drop(columns=['designs_json'])

            return df.to_dict('records')
        except Exception as e:
            logger.error(f"Error fetching sales orders for job card: {str(e)}")
            return []

    def get_pending_sales_orders(self) -> List[dict]:
        """Fetches sales orders with 'Pending Coil Assignment' status."""
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order-JC", header_row=1)
            if df.empty or 'status' not in df.columns:
                return []

            pending_df = df[df['status'] == 'Pending Coil Assignment']
            return pending_df.to_dict('records')
        except Exception as e:
            logger.error(f"Error fetching pending sales orders: {str(e)}")
            return []

    def assign_coils_to_sales_order(self, job_card_number: str, assigned_coils: List) -> bool:
        """Assigns coils to an existing sales order and updates its status."""
        try:
            # 1. Update the status in the 'Sales Order-JC' sheet
            worksheet = self.google_service.client.open_by_key(self.spreadsheet_id).worksheet("Sales Order-JC")
            cell = worksheet.find(job_card_number, in_column=5) # job_card_number is in the 5th column
            if not cell:
                logger.error(f"Sales Order with Job Card No. {job_card_number} not found.")
                return False
            
            # Assuming 'status' is the 11th column
            worksheet.update_cell(cell.row, 11, "Coils Assigned")

            # 2. Create Raw Material Used entries
            today = datetime.now().date()
            for coil in assigned_coils:
                rm_used_request = RMUsedRequest(
                    rm_used_date=today,
                    card_no=job_card_number,
                    coil_no=coil.coil_no,
                    weight=coil.weight_used,
                    machine='',
                    remarks='Slitting'
                )
                self.rm_used_service.create_rm_used(rm_used_request)

            logger.info(f"Coils assigned and status updated for Sales Order {job_card_number}.")
            return True
        except Exception as e:
            logger.error(f"Error assigning coils to sales order {job_card_number}: {str(e)}")
            return False

    def get_job_cards_for_party_and_date_range(self, party_name: str, start_date: date, end_date: date) -> List[dict]:
        """Fetches job cards for a specific party within a date range."""
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order-JC", header_row=1)
            if df.empty:
                return []

            df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce').dt.date
            
            filtered_df = df[
                (df['party_name'] == party_name) &
                (df['order_date'] >= start_date) &
                (df['order_date'] <= end_date)
            ]
            return filtered_df.to_dict('records')
        except Exception as e:
            logger.error(f"Error fetching job cards for party {party_name}: {str(e)}")
            return []
