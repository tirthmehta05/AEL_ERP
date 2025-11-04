from typing import Optional
from pydantic import BaseModel, Field
import streamlit as st

class AppSettings(BaseModel):
    dev_mode: bool = Field(default=False)

class APISettings(BaseModel):
    google_service_account_json: Optional[str] = Field(default=None)
    google_sheets_id: Optional[str] = Field(default=None)

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

class Settings(BaseModel):
    app: AppSettings
    api: APISettings
    power_automate: PowerAutomateSettings
    streamlit: StreamlitSettings
    constants: ConstantsSettings
    slitting_plan: SlittingPlanSettings

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
    )

settings = load_settings()
