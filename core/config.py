from pydantic_settings import BaseSettings

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
    provider_name: str = "gitlab"
    provider_config_path: str = "config/provider.yaml"
    provider_cache_ttl: int = 600 #10 min

# Load settings
settings = AppSettings()