import pandas as pd
from src.shared.utils.logger_config import setup_logger
from src.data_entry.service.rm_used_service import RMUsedService
from src.data_entry.models.rm_used_models import RMUsedRequest
from src.slitting_plan.repository.slitting_plan_repository import SlittingPlanRepository
from config import settings
from datetime import datetime
import json

logger = setup_logger(__name__)

class SlittingPlanService:
    def __init__(self):
        self.repository = SlittingPlanRepository()
        self.rm_used_service = RMUsedService()

    def get_available_coils(self) -> pd.DataFrame:
        """
        Calculates the available weight for each coil by processing inward and used data.
        """
        inward_df = self.repository.fetch_inward_data()
        used_df = self.repository.fetch_used_data()

        if inward_df.empty:
            return pd.DataFrame()

        inward_grouped = self._process_inward_data(inward_df)
        used_grouped = self._process_used_data(used_df)
        
        available_coils_df = self._calculate_available_weight(inward_grouped, used_grouped)

        return available_coils_df[available_coils_df["available_weight"] > 0]

    def _process_inward_data(self, inward_df: pd.DataFrame) -> pd.DataFrame:
        """Groups and aggregates the inward raw material data."""
        inward_df["Coil Weight"] = pd.to_numeric(inward_df["Coil Weight"], errors='coerce').fillna(0)
        inward_df["Width"] = pd.to_numeric(inward_df["Width"], errors='coerce').fillna(0)
        
        return inward_df.groupby("Coil Number").agg(
            total_weight=("Coil Weight", "sum"),
            grade=("Grade", "first"),
            thickness=("Thk", "first"),
            width=("Width", "first"),
            coating=("Coating", "first"),
            coil_location=("Location", "first"),
            coil_supplier=("Coil Supplier", "first"),
            rm_type=("RM Type", "first"),
        ).reset_index()

    def _process_used_data(self, used_df: pd.DataFrame) -> pd.DataFrame:
        """Groups and aggregates the used raw material data."""
        if used_df.empty:
            return pd.DataFrame(columns=["Coil Number", "used_weight"])
            
        used_df["Weight"] = pd.to_numeric(used_df["Weight"], errors='coerce').fillna(0)
        used_grouped = used_df.groupby("Coil No")["Weight"].sum().reset_index()
        return used_grouped.rename(columns={"Coil No": "Coil Number", "Weight": "used_weight"})

    def _calculate_available_weight(self, inward_grouped: pd.DataFrame, used_grouped: pd.DataFrame) -> pd.DataFrame:
        """Merges inward and used data to calculate available weight."""
        if used_grouped.empty:
            inward_grouped["available_weight"] = inward_grouped["total_weight"]
            return inward_grouped

        available_coils_df = pd.merge(inward_grouped, used_grouped, on="Coil Number", how="left")
        available_coils_df["used_weight"] = available_coils_df["used_weight"].fillna(0)
        available_coils_df["available_weight"] = available_coils_df["total_weight"] - available_coils_df["used_weight"]
        return available_coils_df

    def get_material_type_options(self) -> list:
        sales_order_df = self.repository.fetch_sales_order_data()
        if sales_order_df.empty:
            return []
        return ["All"] + list(sales_order_df["Material Type"].dropna().unique())

    def get_sales_order_summary(self, start_date, end_date, material_type) -> pd.DataFrame:
        sales_order_df = self.repository.fetch_sales_order_data()
        if sales_order_df.empty:
            return pd.DataFrame()

        sales_order_df["Order Entry Date"] = pd.to_datetime(sales_order_df["Order Entry Date"], errors='coerce')

        filtered_df = sales_order_df[
            (sales_order_df["Order Entry Date"] >= pd.to_datetime(start_date))
            & (sales_order_df["Order Entry Date"] <= pd.to_datetime(end_date))
        ]

        if material_type != "All":
            filtered_df = filtered_df[filtered_df["Material Type"] == material_type]

        filtered_df = filtered_df.copy()

        filtered_df.loc[:, "Qty"] = pd.to_numeric(filtered_df["Qty"], errors='coerce').fillna(0)
        filtered_df.loc[:, "Width"] = pd.to_numeric(filtered_df["Width"], errors='coerce').fillna(0)
        filtered_df.loc[:, "Thk"] = pd.to_numeric(filtered_df["Thk"], errors='coerce').fillna(0)

        summary_df = filtered_df.groupby(["Width", "Thk"]).agg(
            Total_Qty=("Qty", "sum")
        ).reset_index()

        return summary_df

    def get_next_plan_id(self, width: int, supplier_name: str, slitter_name: str) -> str:
        """Generates a new unique ID for a slitting plan from the 'SlittingPlans' sheet."""
        today_str = datetime.now().strftime("%y%m%d")
        supplier_abbr = supplier_name[:3].upper() if supplier_name else "UNK"
        slitter_abbr = slitter_name[:3].upper() if slitter_name else "UNK"
        prefix = f"{settings.slitting_plan.plan_id_prefix}-{slitter_abbr}-{supplier_abbr}-{width}-{today_str}-"
        try:
            df = self.repository.fetch_slitting_plans_data()
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

    def calculate_slitting_plan(self, selected_coils_df, edited_df):
        errors = []
        summary = {}
        
        if selected_coils_df.empty:
            errors.append("Please select at least one coil to proceed.")
            return {"errors": errors, "calculated_plan": pd.DataFrame(), "summary": summary}

        single_coil_width = selected_coils_df["width"].iloc[0]
        
        edited_df["Size"] = pd.to_numeric(edited_df["Size"], errors='coerce').fillna(0)
        edited_df["No. of Slits"] = pd.to_numeric(edited_df["No. of Slits"], errors='coerce').fillna(0)

        max_slit_size = edited_df["Size"].max()
        if max_slit_size > single_coil_width:
            errors.append(f"Error: Requested slit size of {max_slit_size}mm is wider than the selected coil width ({single_coil_width}mm).")
            return {"errors": errors, "calculated_plan": edited_df, "summary": summary}

        edited_df["MM"] = edited_df["Size"] * edited_df["No. of Slits"]
        total_mm_used = edited_df["MM"].sum()

        if total_mm_used > single_coil_width:
            errors.append(f"Error: Total planned width ({total_mm_used}mm) exceeds the width of a single coil ({single_coil_width}mm).")
            return {"errors": errors, "calculated_plan": edited_df, "summary": summary}

        total_weight_selected = selected_coils_df["available_weight"].sum()
        if single_coil_width > 0:
            weight_per_mm = total_weight_selected / single_coil_width
            edited_df["Weight in Kg"] = weight_per_mm * edited_df["MM"]
        else:
            edited_df["Weight in Kg"] = 0
        
        scrap_per_coil = single_coil_width - total_mm_used
        scrap_weight = weight_per_mm * scrap_per_coil if single_coil_width > 0 else 0

        summary = {
            "total_slits": edited_df["No. of Slits"].sum(),
            "total_mm_used": total_mm_used,
            "total_weight_kg": edited_df['Weight in Kg'].sum(),
            "scrap_per_coil_mm": scrap_per_coil,
            "scrap_weight_kg": scrap_weight,
            "total_weight_selected": total_weight_selected,
            "single_coil_width": single_coil_width,
        }

        return {"errors": errors, "calculated_plan": edited_df, "summary": summary}

    def save_plan(self, plan_data: dict) -> str:
        try:
            supplier_name = plan_data['selected_coils'][0]['coil_supplier'] if plan_data['selected_coils'] else ""
            plan_id = self.get_next_plan_id(plan_data['coil_width'], supplier_name, plan_data['slitter'])
            headers = [
                "PlanID", "Date", "Status", "CoilWidth", "TotalCoilWeight", 
                "ScrapMM", "ScrapWeight", "RawMaterialsJSON", "SlitDetailsJSON"
            ]
            self.repository.ensure_slitting_plans_worksheet(headers)

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

            success = self.repository.append_slitting_plan(row_to_add)
            
            if success:
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
        try:
            df = self.repository.fetch_slitting_plans_data()
            if df.empty or 'PlanID' not in df.columns or 'Status' not in df.columns:
                return []
            
            printable_df = df[df['Status'].isin(["Created", "In Process"])]
            return printable_df['PlanID'].dropna().unique().tolist()
        except Exception as e:
            logger.error(f"Error getting printable plans: {str(e)}")
            return []

    def get_saved_plan_details(self, plan_id: str) -> dict:
        try:
            df = self.repository.fetch_slitting_plans_data()
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
        try:
            return self.repository.update_plan_status_in_sheet(plan_id, new_status)
        except Exception as e:
            logger.error(f"Error updating status for plan {plan_id}: {str(e)}")
            return False

    def validate_packing_list(self, packing_list_df: pd.DataFrame, plan_ids: list[str], mapping: dict) -> dict:
        try:
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

            total_plan_summary = {}
            for plan_id in plan_ids:
                plan_details = self.get_saved_plan_details(plan_id)
                if not plan_details:
                    logger.warning(f"Could not retrieve details for plan_id: {plan_id}. Skipping in validation.")
                    continue
                
                num_coils_in_plan = len(plan_details.get('raw_materials', []))
                if num_coils_in_plan == 0:
                    logger.warning(f"Slitting plan {plan_id} has no raw materials. Skipping in validation.")
                    continue

                for slit in plan_details.get('slit_details', []):
                    size = float(slit.get('Size', 0))
                    slits_per_coil = int(slit.get('No. of Slits', 0))
                    weight = float(slit.get('Weight in Kg', 0))

                    total_slits_for_size_in_plan = slits_per_coil * num_coils_in_plan
                    
                    if size in total_plan_summary:
                        total_plan_summary[size]['planned_slits'] += total_slits_for_size_in_plan
                        total_plan_summary[size]['planned_weight'] += weight
                    else:
                        total_plan_summary[size] = {
                            'planned_slits': total_slits_for_size_in_plan, 
                            'planned_weight': weight
                        }
            
            plan_summary_df = pd.DataFrame.from_dict(total_plan_summary, orient='index').reset_index().rename(columns={'index': width_col})

            comparison_df = pd.merge(plan_summary_df, packing_list_summary, on=width_col, how='outer').fillna(0)
            
            def get_status(row):
                slits_match = row['planned_slits'] == row['found_coils']
                
                # Calculate 5% weight tolerance
                weight_tolerance_5_percent = row['planned_weight'] * 0.05
                weight_within_5_percent = abs(row['planned_weight'] - row['found_weight']) <= weight_tolerance_5_percent

                if slits_match:
                    if weight_within_5_percent:
                        return "✅ Match"
                    else:
                        # Calculate actual percentage deviation
                        if row['planned_weight'] != 0:
                            actual_deviation_percent = (abs(row['planned_weight'] - row['found_weight']) / row['planned_weight']) * 100
                            return f"⚠️ Weight Mismatch ({actual_deviation_percent:.2f}% deviation)"
                        else:
                            # Handle case where planned_weight is 0 to avoid division by zero
                            return "⚠️ Weight Mismatch (Planned weight is 0)"
                else:
                    # Coils do not match exactly, this is a hard mismatch
                    return "❌ Mismatch"

            comparison_df['Status'] = comparison_df.apply(get_status, axis=1)
            validation_passed = "❌ Mismatch" not in comparison_df['Status'].unique()

            return {"validation_passed": validation_passed, "comparison_df": comparison_df}
        except Exception as e:
            logger.error(f"Error validating packing list: {str(e)}")
            return {"validation_passed": False, "comparison_df": pd.DataFrame(), "message": str(e)}