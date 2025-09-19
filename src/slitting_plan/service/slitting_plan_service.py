import pandas as pd
from src.shared.integrations.google_drive_service import google_drive_service
from config import settings
from datetime import datetime

class SlittingPlanService:
    def __init__(self):
        self.google_service = google_drive_service
        self.spreadsheet_id = settings.api.google_sheets_id

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

        # Convert relevant columns to numeric
        filtered_df["Qty"] = pd.to_numeric(filtered_df["Qty"], errors='coerce').fillna(0)
        filtered_df["Width"] = pd.to_numeric(filtered_df["Width"], errors='coerce').fillna(0)
        filtered_df["Thk"] = pd.to_numeric(filtered_df["Thk"], errors='coerce').fillna(0)

        # Group and aggregate
        summary_df = filtered_df.groupby(["Width", "Thk"]).agg(
            Total_Qty=("Qty", "sum")
        ).reset_index()

        return summary_df