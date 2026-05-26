from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    app_name: str = "Checkr"
    root_path: str = "/validators"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 5000

    # SSL
    http_verify_ssl: bool = True

    # Logging
    log_level: str = "INFO"
    log_file: str | None = None
    silence_probes: bool = True

    version: str = "0.1.0"

    # validators provider
    provider_name: str = "mock"
    provider_config_path: str = "config/provider.yaml"
    provider_cache_ttl: int = 600 #10 min

    # llm
    llm_config_path: str = "config/llm.yaml"

    # async job queue (Redis)
    # When unset checkr operates in sync mode and /jobs/validate behaves
    # like /validate — blocking, no job_id returned.
    redis_url: str | None = None          # CHECKR_REDIS_URL
    job_ttl: int = 86400                  # CHECKR_JOB_TTL  (seconds, default 24 h)
    job_queue_key: str = "checkr:queue"   # CHECKR_JOB_QUEUE_KEY
    job_key_prefix: str = "checkr:jobs:"  # CHECKR_JOB_KEY_PREFIX

    model_config = SettingsConfigDict(env_prefix="CHECKR_", env_file=".env", env_file_encoding="utf-8", extra='allow')

# Load settings
settings = AppSettings()
