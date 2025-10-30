from typing import List
from src.shared.utils.logger_config import setup_logger
from src.shared.integrations.google_drive_service import google_drive_service
from src.data_entry.models.sales_order_models import SalesOrderRequest, SalesOrderDropdownData
from src.data_entry.service.rm_used_service import RMUsedService
from src.data_entry.models.rm_used_models import RMUsedRequest
from config import settings

from datetime import datetime

import json
import pandas as pd

logger = setup_logger(__name__)

class SalesOrderService:
    def __init__(self):
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id
        self.rm_used_service = RMUsedService()

    def generate_job_card_number(self, party_name: str) -> str:
        """Generates a new unique Job Card number."""
        today_str = datetime.now().strftime("%y%m%d")
        time_str = datetime.now().strftime("%H%M%S")
        party_abbr = party_name[:3].upper() if party_name else "UNK"
        return f"JC-{party_abbr}-{today_str}-{time_str}"


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

            return SalesOrderDropdownData(party_names=party_names, hole_sizes=hole_sizes)
        except Exception as e:
            logger.error(f"Error getting dropdown data for Sales Order: {str(e)}")
            return SalesOrderDropdownData()

    def save_sales_order(self, request: SalesOrderRequest) -> bool:
        """Saves a new sales order entry to the 'Sales Order-JC' sheet and the 'Sales Order' sheet."""
        try:
            # This method no longer generates the JC number, it receives it.
            # The UI will generate it for display, but the service will handle it for saving.
            # For consistency, we will re-assign it here to ensure it's unique.
            request.job_card_number = self.generate_job_card_number(request.party_name)

            worksheet_name_jc = "Sales Order-JC"
            headers_jc = [
                "order_date", "po_no", "party_name", "delivery_date", "job_card_number",
                "hole_size", "number_of_cores", "rate_per_kg", "header_core_stack", "designs_json"
            ]
            self.google_service.ensure_worksheet_with_headers(self.spreadsheet_id, worksheet_name_jc, headers_jc)

            designs_json = json.dumps([d.model_dump() for d in request.designs])
            data_row_jc = [
                request.order_date.strftime("%Y-%m-%d"), request.po_no, request.party_name,
                request.delivery_date.strftime("%Y-%m-%d"), request.job_card_number,
                request.hole_size, request.number_of_cores, request.rate_per_kg,
                request.header_core_stack, designs_json
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

            # Third, create Raw Material Used entries for each assigned coil
            for assigned_coil in request.assigned_coils:
                rm_used_request = RMUsedRequest(
                    rm_used_date=datetime.now().date(),
                    card_no=request.job_card_number, # Use the JC number as the card number
                    coil_no=assigned_coil.coil_no,
                    weight=assigned_coil.weight_used,
                    machine='', # No machine specified for this workflow
                    remarks='Slitting'
                )
                self.rm_used_service.create_rm_used(rm_used_request)

            logger.info(f"Successfully saved Sales Order {request.job_card_number} and all related entries.")
            return True
        except Exception as e:
            logger.error(f"Error saving sales order: {str(e)}")
            return False

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
