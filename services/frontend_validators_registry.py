from providers.factory import get_validator_provider
from schemas.validators import ValidatorDetail

async def fetch_frontend_validators(provider_name="mock") -> list[ValidatorDetail]:
    provider = get_validator_provider(provider_name)
    return await provider.fetch_frontend_validators()

async def fetch_frontend_validator_source(file_path: str, provider_name="mock") -> str:
    provider = get_validator_provider(provider_name)
    return await provider.fetch_frontend_validator_source(file_path)
