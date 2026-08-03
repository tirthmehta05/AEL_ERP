from typing import Optional
from pydantic import BaseModel, Field
import streamlit as st

class AppSettings(BaseModel):
    dev_mode: bool = Field(default=False)

class APISettings(BaseModel):
    google_service_account_json: Optional[str] = Field(default=None)
    google_sheets_id: Optional[str] = Field(default=None)
    weighing_scale_url: Optional[str] = Field(default=None)
    weighing_scale_crane_url: Optional[str] = Field(default=None)
    # Bid Optimizer customer-rate workbook hosted on Google Sheets (one tab
    # per customer). Kept OUT of the repo — the repo is public. Set in
    # .streamlit/secrets.toml (local) and the Streamlit Cloud app secrets.
    bid_optimizer_customer_sheet_id: Optional[str] = Field(default=None)

class PowerAutomateSettings(BaseModel):
    pa_client_id: Optional[str] = Field(default=None)
    pa_client_secret: Optional[str] = Field(default=None)
    pa_tenant_id: Optional[str] = Field(default=None)

class MSGraphSettings(BaseModel):
    """App-registration credentials for Microsoft Graph.

    Used by the Performance module for two things: sending deadline
    reminders via sendMail, and writing locked scores into the
    Performance Master workbook on SharePoint. Raw REST via `requests`
    — no Graph SDK dependency.
    """
    client_id: Optional[str] = Field(default=None)
    client_secret: Optional[str] = Field(default=None)
    tenant_id: Optional[str] = Field(default=None)
    sharepoint_site_url: Optional[str] = Field(default=None)
    excel_file_path: Optional[str] = Field(default=None)
    # Dedicated sender for automated mail. Scope the Mail.Send application
    # permission to this mailbox with an ApplicationAccessPolicy — otherwise
    # the app registration can send as ANY user in the tenant.
    alert_sender_upn: Optional[str] = Field(default=None)

class PerformanceSettings(BaseModel):
    """Employee performance & review system.

    The performance workbook is a SEPARATE spreadsheet from the operations
    sheet — score data is salary-adjacent and does not belong alongside
    day-to-day operational tabs.
    """
    performance_sheets_id: Optional[str] = Field(default=None)
    # Blocks writes to the live Performance Master until explicitly enabled.
    enable_perf_master_export: bool = Field(default=False)
    # Minimum characters for a scoring remark. A floor does not guarantee
    # substance, but it does stop one-word justifications.
    min_remark_chars: int = Field(default=100)

class StreamlitSettings(BaseModel):
    server_port: int = Field(default=8501)
    server_address: str = Field(default="0.0.0.0")
    browser_gather_usage_stats: bool = Field(default=False)

class ConstantsSettings(BaseModel):
    steel_density: float = Field(default=7.41) # Default to a common value

class SlittingPlanSettings(BaseModel):
    plan_id_prefix: str = Field(default="SP")
    initial_status: str = Field(default="Created")
    printable_statuses: list[str] = Field(default_factory=lambda: ["Created", "In Process"])
    validation_weight_tolerance: float = Field(default=0.01)
    slitters: list[str] = Field(default_factory=lambda: ["AEL Pune", "TAIIN"])

class WeightReceiptSettings(BaseModel):
    manual_entry_authorized_emails: list[str] = Field(default_factory=list)

class Settings(BaseModel):
    app: AppSettings
    api: APISettings
    power_automate: PowerAutomateSettings
    streamlit: StreamlitSettings
    constants: ConstantsSettings
    slitting_plan: SlittingPlanSettings
    weight_receipt: WeightReceiptSettings
    # Optional subsystems — defaulted so an existing deployment without these
    # secrets sections still loads. The Performance page reports the missing
    # configuration itself rather than taking the whole app down at import.
    ms_graph: MSGraphSettings = Field(default_factory=MSGraphSettings)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)

# Load settings from st.secrets
def load_settings() -> Settings:
    """Loads settings from Streamlit's secrets.
    
    This function reads the secrets from the .streamlit/secrets.toml file (for local development)
    or from the secrets set in the Streamlit Cloud dashboard.
    """
    # The st.secrets object is a dict-like object. We can access the sections
    # from the TOML file as attributes or keys.
    return Settings(
        app=AppSettings(**st.secrets.get("app", {})),
        api=APISettings(**st.secrets.get("api", {})),
        power_automate=PowerAutomateSettings(**st.secrets.get("power_automate", {})),
        streamlit=StreamlitSettings(**st.secrets.get("streamlit", {})),
        constants=ConstantsSettings(**st.secrets.get("constants", {})),
        slitting_plan=SlittingPlanSettings(**st.secrets.get("slitting_plan", {})),
        weight_receipt=WeightReceiptSettings(**st.secrets.get("weight_receipt", {})),
        ms_graph=MSGraphSettings(**st.secrets.get("ms_graph", {})),
        performance=PerformanceSettings(**st.secrets.get("performance", {})),
    )

settings = load_settings()
