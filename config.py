from typing import Optional
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict



ROOT_DIR = Path(__file__).resolve().parent
ENV_FILE = ROOT_DIR / ".env"



class AppSettings(BaseSettings):
    dev_mode: bool = Field(default=False, env="DEV_MODE")

class APISettings(BaseSettings):
    google_service_account_json: Optional[str] = Field(default=None, env="GOOGLE_SERVICE_ACCOUNT_JSON")
    google_sheets_id: Optional[str] = Field(default=None, env="GOOGLE_SHEETS_ID")








class StreamlitSettings(BaseSettings):
    server_port: int = Field(default=8501, env="STREAMLIT_SERVER_PORT")
    server_address: str = Field(default="0.0.0.0", env="STREAMLIT_SERVER_ADDRESS")
    browser_gather_usage_stats: bool = Field(default=False, env="STREAMLIT_BROWSER_GATHER_USAGE_STATS")





class Settings(BaseSettings):
    app: AppSettings
    api: APISettings
    streamlit: StreamlitSettings
    
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="_",
        extra="ignore",
    )


settings = Settings()
