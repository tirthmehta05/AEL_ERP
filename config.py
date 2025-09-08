"""
Configuration management for AEL ERP using Pydantic.
This module loads environment variables and provides type-safe access to configuration.
"""

from typing import Optional
from pathlib import Path
from pydantic import BaseSettings, Field, validator


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""
    host: str = Field(default="localhost", env="DB_HOST")
    port: int = Field(default=5432, env="DB_PORT")
    username: str = Field(env="DB_USERNAME")
    password: str = Field(env="DB_PASSWORD")
    name: str = Field(env="DB_NAME")
    
    @property
    def url(self) -> str:
        """Get database URL."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.name}"


class APISettings(BaseSettings):
    """API keys and external service configuration."""
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, env="GOOGLE_API_KEY")


class ERPSettings(BaseSettings):
    """ERP-specific configuration."""
    admin_password: str = Field(env="ADMIN_PASSWORD")
    encryption_key: str = Field(env="ENCRYPTION_KEY")
    secret_key: str = Field(env="SECRET_KEY")
    session_timeout: int = Field(default=3600, env="SESSION_TIMEOUT")
    max_login_attempts: int = Field(default=5, env="MAX_LOGIN_ATTEMPTS")
    password_min_length: int = Field(default=8, env="PASSWORD_MIN_LENGTH")


class EmailSettings(BaseSettings):
    """Email service configuration."""
    smtp_server: str = Field(default="smtp.gmail.com", env="SMTP_SERVER")
    smtp_port: int = Field(default=587, env="SMTP_PORT")
    smtp_username: str = Field(env="SMTP_USERNAME")
    smtp_password: str = Field(env="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, env="SMTP_USE_TLS")


class StreamlitSettings(BaseSettings):
    """Streamlit-specific configuration."""
    server_port: int = Field(default=8501, env="STREAMLIT_SERVER_PORT")
    server_address: str = Field(default="0.0.0.0", env="STREAMLIT_SERVER_ADDRESS")
    browser_gather_usage_stats: bool = Field(default=False, env="STREAMLIT_BROWSER_GATHER_USAGE_STATS")


class AppSettings(BaseSettings):
    """General application settings."""
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    max_upload_size: int = Field(default=200, env="MAX_UPLOAD_SIZE")
    upload_folder: str = Field(default="./uploads", env="UPLOAD_FOLDER")
    data_folder: str = Field(default="./data", env="DATA_FOLDER")
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of {valid_levels}')
        return v.upper()
    
    @validator('upload_folder', 'data_folder')
    def create_folders(cls, v):
        """Create folders if they don't exist."""
        Path(v).mkdir(parents=True, exist_ok=True)
        return v


class Settings(BaseSettings):
    """Main settings class that combines all configuration sections."""
    
    # Sub-configurations
    database: DatabaseSettings = DatabaseSettings()
    api: APISettings = APISettings()
    erp: ERPSettings = ERPSettings()
    email: EmailSettings = EmailSettings()
    streamlit: StreamlitSettings = StreamlitSettings()
    app: AppSettings = AppSettings()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Allow nested settings
        env_nested_delimiter = "__"


# Global settings instance
settings = Settings()


# Convenience functions for easy access
def get_database_config() -> dict:
    """Get database configuration as dictionary."""
    return {
        "host": settings.database.host,
        "port": settings.database.port,
        "username": settings.database.username,
        "password": settings.database.password,
        "name": settings.database.name,
        "url": settings.database.url
    }


def get_email_config() -> dict:
    """Get email configuration as dictionary."""
    return {
        "server": settings.email.smtp_server,
        "port": settings.email.smtp_port,
        "username": settings.email.smtp_username,
        "password": settings.email.smtp_password,
        "use_tls": settings.email.smtp_use_tls
    }


def get_streamlit_config() -> dict:
    """Get Streamlit configuration as dictionary."""
    return {
        "port": settings.streamlit.server_port,
        "address": settings.streamlit.server_address,
        "gather_usage_stats": settings.streamlit.browser_gather_usage_stats
    }


def is_debug_mode() -> bool:
    """Check if application is in debug mode."""
    return settings.app.debug


def get_log_level() -> str:
    """Get current log level."""
    return settings.app.log_level


# Example usage:
if __name__ == "__main__":
    print("Database Config:", get_database_config())
    print("Email Config:", get_email_config())
    print("Streamlit Config:", get_streamlit_config())
    print("Debug Mode:", is_debug_mode())
    print("Log Level:", get_log_level())
