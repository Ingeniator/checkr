from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    app_name: str = "Checkr"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 5005

    # Logging
    log_level: str = "INFO"
    log_file: str | None = None

    version: str = "0.1.0"


# Load settings
settings = AppSettings()