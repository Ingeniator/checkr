# mock_validator_provider.py

from providers.base import BaseValidatorProvider
from schemas.validators import ValidatorDetail, ValidatorType
from core.logging_config import setup_logging
from utils.frontmatter import extract_frontmatter
from pathlib import Path

logger = setup_logging()

class MockValidatorProvider(BaseValidatorProvider):

    def __init__(self,):
        self.source_prefix = "mock"
        self.base_path = "validators"

    async def fetch_frontend_validators(self) -> list[ValidatorDetail]:
        return [
            ValidatorDetail(
                title="mock validator",
                enabled=False,
                type=ValidatorType.dataset_frontend,
                stage="mock",
                tags=["mock"],
                description="This is a mock validator for testing purposes.",
                source=f"{self.source_prefix}/mock-validator.py"
            )
        ]
    
    async def fetch_frontend_validator_source(self, file_path: str) -> str:
        if file_path == f"{self.source_prefix}/mock-validator.py":
            return """
from validators.base_validator import BaseValidator, ValidationErrorDetail
class MockValidator(BaseValidator):
    async def _validate(self, data: list[dict]) -> list[ValidationErrorDetail]:
        return []
"""
        return ""
    
    async def fetch_frontend_base_validators_source(self) -> dict[str, str]:
        base_dir = Path(self.base_path)
        result: dict[str, str] = {}

        for file_path in base_dir.glob("*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
                result[file_path] = content

                # Optionally register it as a base validator for reuse
                front = extract_frontmatter(content)
                if front.get("type") == "base":
                    self.base_validators.append(ValidatorDetail(
                        title=front.get("title", file_path.stem),
                        type=ValidatorType(front.get("type", "dataset_backend")),
                        enabled=front.get("enabled", True),
                        stage=front.get("stage", "experimental"),
                        description=front.get("description", ""),
                        tags=front.get("tags", []),
                        options=front.get("options", {}),
                        source=f"{self.source_prefix}/{file_path}"
                    ))

            except Exception as e:
                logger.warning(f"Failed to load mock base validator {file_path}: {e}")
                continue

        return result