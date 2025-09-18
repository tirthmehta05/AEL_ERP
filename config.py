from typing import Optional
from pydantic import BaseModel, Field
import streamlit as st

class AppSettings(BaseModel):
    dev_mode: bool = Field(default=False)

class APISettings(BaseModel):
    google_service_account_json: Optional[str] = Field(default=None)
    google_sheets_id: Optional[str] = Field(default=None)

class StreamlitSettings(BaseModel):
    server_port: int = Field(default=8501)
    server_address: str = Field(default="0.0.0.0")
    browser_gather_usage_stats: bool = Field(default=False)

class Settings(BaseModel):
    app: AppSettings
    api: APISettings
    streamlit: StreamlitSettings

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
        streamlit=StreamlitSettings(**st.secrets.get("streamlit", {})),
    )

settings = load_settings()
