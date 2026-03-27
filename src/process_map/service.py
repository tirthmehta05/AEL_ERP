"""
ProcessMapService — reads process hierarchy, SOP index, and business areas
from the 'AEL Process Map' Google Sheet.

Falls back to local CSV files (scripts/output/) when the Google Sheet
is not yet configured.
"""

import pandas as pd
from pathlib import Path
from src.shared.integrations.google_drive_service import GoogleDriveService
from src.shared.utils.logger_config import setup_logger

logger = setup_logger(__name__)

CSV_FALLBACK_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "output"


class ProcessMapService:
    def __init__(self, google_service: GoogleDriveService, spreadsheet_id: str | None = None):
        self.google_service = google_service
        self.spreadsheet_id = spreadsheet_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_process_map(self) -> pd.DataFrame:
        """Return the full ProcessMap sheet as a DataFrame."""
        df = self._read_sheet("ProcessMap", "process_map.csv")
        if df.empty:
            return df
        # Ensure numeric ordering columns
        for col in ("stage_order", "step_order"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        return df.sort_values(["business_area", "process", "stage_order", "path", "step_order"])

    def get_sop_index(self) -> pd.DataFrame:
        """Return the SOPIndex sheet as a DataFrame."""
        return self._read_sheet("SOPIndex", "sop_index.csv")

    def save_process_map(self, df: pd.DataFrame) -> None:
        """Write process map DataFrame back to local CSV."""
        csv_path = CSV_FALLBACK_DIR / "process_map.csv"
        df.to_csv(csv_path, index=False)
        logger.info(f"Saved process map to {csv_path}")

    def save_sop_index(self, df: pd.DataFrame) -> None:
        """Write SOP index DataFrame back to local CSV."""
        csv_path = CSV_FALLBACK_DIR / "sop_index.csv"
        df.to_csv(csv_path, index=False)
        logger.info(f"Saved SOP index to {csv_path}")

    def get_business_areas(self) -> pd.DataFrame:
        """Return the BusinessAreas sheet as a DataFrame."""
        df = self._read_sheet("BusinessAreas", "business_areas.csv")
        if not df.empty and "order" in df.columns:
            df["order"] = pd.to_numeric(df["order"], errors="coerce").fillna(0).astype(int)
            df = df.sort_values("order")
        return df

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _read_sheet(self, sheet_name: str, csv_fallback: str) -> pd.DataFrame:
        """Try Google Sheet first, fall back to local CSV."""
        if self.spreadsheet_id:
            try:
                df = self.google_service.get_worksheet_data(
                    self.spreadsheet_id, sheet_name, header_row=1
                )
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.warning(f"Google Sheet read failed for '{sheet_name}': {e}. Falling back to CSV.")

        # CSV fallback
        csv_path = CSV_FALLBACK_DIR / csv_fallback
        if csv_path.exists():
            logger.info(f"Reading from local CSV: {csv_path}")
            return pd.read_csv(csv_path, keep_default_na=False)

        logger.warning(f"No data source found for '{sheet_name}'")
        return pd.DataFrame()
