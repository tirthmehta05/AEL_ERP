import pandas as pd
from src.shared.utils.logger_config import setup_logger
from src.shared.integrations.google_drive_service import google_drive_service
from src.data_entry.service.rm_used_service import RMUsedService
from src.data_entry.models.rm_used_models import RMUsedRequest
from config import settings
from datetime import datetime
import json
import gspread

logger = setup_logger(__name__)

class SlittingPlanService:
    def __init__(self):
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id
        self.rm_used_service = RMUsedService()

    def get_available_coils(self) -> pd.DataFrame:
        inward_df = self.google_service.get_worksheet_data(self.spreadsheet_id, "RM inward_Issue format", header_row=3)
        used_df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Raw Material Used", header_row=2)

        if inward_df.empty:
            return pd.DataFrame()

        # Convert weight columns to numeric, coercing errors to 0
        inward_df["Coil Weight"] = pd.to_numeric(inward_df["Coil Weight"], errors='coerce').fillna(0)
        inward_df["Width"] = pd.to_numeric(inward_df["Width"], errors='coerce').fillna(0)
        if not used_df.empty:
            used_df["Weight"] = pd.to_numeric(used_df["Weight"], errors='coerce').fillna(0)

        # Group inward data
        inward_grouped = inward_df.groupby("Coil Number").agg(
            total_weight=("Coil Weight", "sum"),
            grade=("Grade", "first"),
            thickness=("Thk", "first"),
            width=("Width", "first"),
            coating=("Coating", "first"),
            coil_location=("Coil Location", "first"),
            coil_supplier=("Coil Supplier", "first"),
            rm_type=("RM Type", "first"),
        ).reset_index()

        if used_df.empty:
            inward_grouped["available_weight"] = inward_grouped["total_weight"]
            return inward_grouped

        # Group used data
        used_grouped = used_df.groupby("Coil No")["Weight"].sum().reset_index()
        used_grouped = used_grouped.rename(columns={"Coil No": "Coil Number", "Weight": "used_weight"})

        # Merge and calculate available weight
        available_coils_df = pd.merge(inward_grouped, used_grouped, on="Coil Number", how="left")
        available_coils_df["used_weight"] = available_coils_df["used_weight"].fillna(0)
        available_coils_df["available_weight"] = available_coils_df["total_weight"] - available_coils_df["used_weight"]

        return available_coils_df[available_coils_df["available_weight"] > 0]

    def get_material_type_options(self) -> list:
        sales_order_df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order", header_row=1)
        if sales_order_df.empty:
            return []
        return ["All"] + list(sales_order_df["Material Type"].dropna().unique())

    def get_sales_order_summary(self, start_date, end_date, material_type) -> pd.DataFrame:
        sales_order_df = self.google_service.get_worksheet_data(self.spreadsheet_id, "Sales Order", header_row=1)
        if sales_order_df.empty:
            return pd.DataFrame()

        # Convert date column
        sales_order_df["Order Entry Date"] = pd.to_datetime(sales_order_df["Order Entry Date"], errors='coerce')

        # Filter by date
        filtered_df = sales_order_df[
            (sales_order_df["Order Entry Date"] >= pd.to_datetime(start_date))
            & (sales_order_df["Order Entry Date"] <= pd.to_datetime(end_date))
        ]

        # Filter by material type
        if material_type != "All":
            filtered_df = filtered_df[filtered_df["Material Type"] == material_type]

        # Create an explicit copy to avoid the SettingWithCopyWarning
        filtered_df = filtered_df.copy()

        # Convert relevant columns to numeric using .loc to avoid warnings
        filtered_df.loc[:, "Qty"] = pd.to_numeric(filtered_df["Qty"], errors='coerce').fillna(0)
        filtered_df.loc[:, "Width"] = pd.to_numeric(filtered_df["Width"], errors='coerce').fillna(0)
        filtered_df.loc[:, "Thk"] = pd.to_numeric(filtered_df["Thk"], errors='coerce').fillna(0)

        # Group and aggregate
        summary_df = filtered_df.groupby(["Width", "Thk"]).agg(
            Total_Qty=("Qty", "sum")
        ).reset_index()

        return summary_df

    def get_next_plan_id(self, width: int) -> str:
        """Generates a new unique ID for a slitting plan from the 'SlittingPlans' sheet."""
        today_str = datetime.now().strftime("%y%m%d")
        prefix = f"SP-{width}-{today_str}-"
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "SlittingPlans", header_row=1)
            if df.empty or 'PlanID' not in df.columns:
                return f"{prefix}01"
            
            plan_ids = df[df['PlanID'].str.startswith(prefix, na=False)]['PlanID']
            if plan_ids.empty:
                return f"{prefix}01"
            
            max_seq = plan_ids.str.split('-').str[-1].astype(int).max()
            next_seq = max_seq + 1
            return f"{prefix}{next_seq:02d}"
        except Exception:
            return f"{prefix}01"

    def save_plan(self, plan_data: dict) -> str:
        """Saves a slitting plan as a single row with JSON for details."""
        try:
            plan_id = self.get_next_plan_id(plan_data['coil_width'])
            worksheet_name = "SlittingPlans"
            headers = [
                "PlanID", "Date", "Status", "CoilWidth", "TotalCoilWeight", 
                "ScrapMM", "ScrapWeight", "RawMaterialsJSON", "SlitDetailsJSON"
            ]
            self.google_service.ensure_worksheet_with_headers(self.spreadsheet_id, worksheet_name, headers)

            row_to_add = [
                plan_id,
                datetime.now().strftime("%Y-%m-%d"),
                "Created",
                plan_data['coil_width'],
                plan_data['total_coil_weight'],
                plan_data['scrap_mm'],
                plan_data['scrap_weight'],
                json.dumps(plan_data['selected_coils']),
                json.dumps(plan_data['slit_details'])
            ]

            success = self.google_service.append_data(self.spreadsheet_id, worksheet_name, [row_to_add])
            
            if success:
                # Create Raw Material Used entries for each coil
                today = datetime.now().date()
                for coil in plan_data['selected_coils']:
                    rm_used_request = RMUsedRequest(
                        rm_used_date=today,
                        card_no='stock',
                        coil_no=coil['Coil Number'],
                        weight=coil['available_weight'],
                        machine='',
                        remarks='Slitting'
                    )
                    self.rm_used_service.create_rm_used(rm_used_request)
                return plan_id
            else:
                return ""
        except Exception as e:
            logger.error(f"Error saving slitting plan: {str(e)}")
            return ""

    def get_printable_plans(self) -> list[str]:
        """Fetches a list of Plan IDs that are available to be printed."""
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "SlittingPlans", header_row=1)
            if df.empty or 'PlanID' not in df.columns or 'Status' not in df.columns:
                return []
            
            printable_df = df[df['Status'].isin(["Created", "In Process"])]
            return printable_df['PlanID'].dropna().unique().tolist()
        except Exception as e:
            logger.error(f"Error getting printable plans: {str(e)}")
            return []

    def get_saved_plan_details(self, plan_id: str) -> dict:
        """Retrieves all data for a specific saved slitting plan."""
        try:
            df = self.google_service.get_worksheet_data(self.spreadsheet_id, "SlittingPlans", header_row=1)
            if df.empty or 'PlanID' not in df.columns:
                return {}

            plan_series = df[df['PlanID'] == plan_id].iloc[0]
            if plan_series.empty:
                return {}

            plan_data = {
                'plan_id': plan_series["PlanID"],
                'date': plan_series["Date"],
                'status': plan_series["Status"],
                'coil_width': plan_series["CoilWidth"],
                'total_coil_weight': plan_series["TotalCoilWeight"],
                'scrap_mm': plan_series["ScrapMM"],
                'scrap_weight': plan_series["ScrapWeight"],
                'raw_materials': json.loads(plan_series["RawMaterialsJSON"]),
                'slit_details': json.loads(plan_series["SlitDetailsJSON"])
            }
            return plan_data
        except Exception as e:
            logger.error(f"Error getting saved plan details for {plan_id}: {str(e)}")
            return {}

    def update_plan_status(self, plan_id: str, new_status: str) -> bool:
        """Updates the status for a given slitting plan."""
        try:
            worksheet = self.google_service.client.open_by_key(self.spreadsheet_id).worksheet("SlittingPlans")
            cell = worksheet.find(plan_id, in_column=1)
            if not cell:
                logger.warning(f"Plan ID {plan_id} not found for status update.")
                return False

            # Assuming Status is the 3rd column (index 2)
            worksheet.update_cell(cell.row, 3, new_status)
            logger.info(f"Updated status for Plan ID {plan_id} to '{new_status}'.")
            return True
        except Exception as e:
            logger.error(f"Error updating status for plan {plan_id}: {str(e)}")
            return False

    def validate_packing_list(self, packing_list_df: pd.DataFrame, plan_ids: list[str], mapping: dict) -> dict:
        """Validates a packing list dataframe against the requirements of one or more slitting plans."""
        try:
            # 1. Summarize Packing List
            width_col = mapping.get('width')
            weight_col = mapping.get('coil_weight')
            if not width_col or not weight_col:
                return {"validation_passed": False, "comparison_df": pd.DataFrame(), "message": "Width and Weight must be mapped."}

            packing_list_df[width_col] = pd.to_numeric(packing_list_df[width_col], errors='coerce')
            packing_list_df[weight_col] = pd.to_numeric(packing_list_df[weight_col], errors='coerce')

            packing_list_summary = packing_list_df.groupby(width_col).agg(
                found_coils=(width_col, 'count'),
                found_weight=(weight_col, 'sum')
            ).reset_index()

            # 2. Summarize Slitting Plans
            total_plan_summary = {}
            for plan_id in plan_ids:
                plan_details = self.get_saved_plan_details(plan_id)
                for slit in plan_details.get('slit_details', []):
                    size = float(slit.get('Size', 0))
                    slits = int(slit.get('No. of Slits', 0))
                    weight = float(slit.get('Weight in Kg', 0))
                    if size in total_plan_summary:
                        total_plan_summary[size]['planned_slits'] += slits
                        total_plan_summary[size]['planned_weight'] += weight
                    else:
                        total_plan_summary[size] = {'planned_slits': slits, 'planned_weight': weight}
            
            plan_summary_df = pd.DataFrame.from_dict(total_plan_summary, orient='index').reset_index().rename(columns={'index': width_col})

            # 3. Compare Summaries
            comparison_df = pd.merge(plan_summary_df, packing_list_summary, on=width_col, how='outer').fillna(0)
            
            def get_status(row):
                # Allow a small tolerance for weight matching, e.g., 1%
                weight_tolerance = row['planned_weight'] * 0.01
                weight_match = abs(row['planned_weight'] - row['found_weight']) <= weight_tolerance
                slits_match = row['planned_slits'] == row['found_coils']
                if weight_match and slits_match:
                    return "✅ Match"
                else:
                    return "❌ Mismatch"

            comparison_df['Status'] = comparison_df.apply(get_status, axis=1)
            validation_passed = "❌ Mismatch" not in comparison_df['Status'].unique()

            return {"validation_passed": validation_passed, "comparison_df": comparison_df}
        except Exception as e:
            logger.error(f"Error validating packing list: {str(e)}")
            return {"validation_passed": False, "comparison_df": pd.DataFrame(), "message": str(e)}