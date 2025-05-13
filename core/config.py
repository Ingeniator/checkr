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

    # validators provider
    provider_name: str = "mock"
    provider_config_path: str = "config/provider.yaml"
    provider_cache_ttl: int = 600 #10 min

    model_config = SettingsConfigDict(env_prefix="CHECKR_", env_file=".env", env_file_encoding="utf-8", extra='allow')

# Load settings
settings = AppSettings()