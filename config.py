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

class SalesOrderSettings(BaseModel):
    # Dropdown values for the Sales Order form. Override any of these in a
    # [sales_order] section of secrets.toml to add an option without a deploy.
    # Hole sizes already used on past orders are merged in automatically.
    hole_sizes: list[int] = Field(default_factory=lambda: [13, 16])
    default_hole_size: int = Field(default=16)
    hole_types: list[str] = Field(default_factory=lambda: [
        "Plain", "Centre", "Both Side", "Side",
        "3-Hole", "4-Hole", "5-Hole",
        "Daimond", "V-Noch",
    ])
    material_types: list[str] = Field(default_factory=lambda: [
        "CR COIL", "CRGO EI", "CRNO", "CRNO COIL", "CRNO EI", "CRNO EI TRD", "CRNO TL",
    ])

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
    sales_order: SalesOrderSettings = Field(default_factory=SalesOrderSettings)

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
        sales_order=SalesOrderSettings(**st.secrets.get("sales_order", {})),
    )

settings = load_settings()
