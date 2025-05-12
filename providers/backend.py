import yaml
from pathlib import Path
from core.config import settings
from providers.base import BaseValidatorProvider
from schemas.validators import ValidatorDetail
from core.logging_config import setup_logging
from services.backend_validators_registry import discover_validators_with_metadata

import warnings

import importlib
from utils.frontmatter import extract_frontmatter_from_file, render_frontmatter
from validators.base_validator import BaseValidator

logger = setup_logging()

class BackendValidatorProvider(BaseValidatorProvider):
    source_prefix = "backend"

    def __init__(self, config_path: str = settings.provider_config_path):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)[self.source_prefix]

        self.base_path = self.config.get("path", "")

    def _get_validator_class_from_file(self, file_path: Path) -> type[BaseValidator] | None:
        VALIDATORS_PATH = Path(__file__).parent.parent / self.base_path
        rel_path = file_path.relative_to(VALIDATORS_PATH)
        module_name = f"{self.base_path}." + ".".join(rel_path.with_suffix("").parts)

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning(f"⚠️ Failed to import {file_path}: {e}")
            return None

        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and issubclass(obj, BaseValidator) and obj is not BaseValidator:
                return obj

        return None

    async def fetch_frontend_validators(self) -> list[ValidatorDetail]:
        warnings.warn(
            "BackendValidatorProvider::fetch_frontend_validators is deprecated. Use backend_validator_registry instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return [detail for _, detail in discover_validators_with_metadata()]
    
    async def fetch_frontend_validator_source(self, file_path: str) -> str:
        # Remove the SOURCE_PREFIX only if it exists
        if file_path.startswith(f"{self.source_prefix}/"):
            file_path = file_path[len(self.source_prefix) + 1:]
        try:
            # we need to return remote proxy validator with proper backend validator name
            VALIDATORS_PATH = Path(__file__).parent.parent / self.base_path
            full_file_path = Path(f"{VALIDATORS_PATH}/{file_path}")
            front = extract_frontmatter_from_file(full_file_path)
            obj =  self._get_validator_class_from_file(full_file_path)
            class_name = obj.__name__
            endpoint = f"\'/validate/{self.source_prefix}/{file_path}\'"
            result = f"""
\"\"\"
{render_frontmatter(front)}
\"\"\"
from validators.base_remote_validator import BaseRemoteValidator

class RemoteBackend{class_name}(BaseRemoteValidator):
    endpoint = {endpoint}
            """
            return result
        except Exception as e:
            logger.error(f"[WARN] Failed to fetch source for {file_path}: {e}")
            return ""
