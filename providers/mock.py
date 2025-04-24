# mock_validator_provider.py

from providers.base import BaseValidatorProvider
from schemas.validators import ValidatorDetail, ValidatorType

class MockValidatorProvider(BaseValidatorProvider):
    
    source_prefix = "mock"

    async def fetch_frontend_validators(self) -> list[ValidatorDetail]:
        return [
            ValidatorDetail(
                title="mock validator",
                type=ValidatorType.dataset_frontend,
                stage="mock",
                tags=["mock"],
                description="This is a mock validator for testing purposes.",
                source=f"{self.source_prefix}/mock-validator.py"
            )
        ]
    
    async def fetch_frontend_validator_source(self, file_path: str) -> str:
        if file_path == f"{self.source_prefix}/mock-validator.py":
            return "Mock content"
        return ""