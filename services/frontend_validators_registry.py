from providers.factory import get_validator_provider
from schemas.validators import ValidatorDetail
from providers.base import BaseValidatorProvider
import asyncio
import time
from typing import Tuple
from core.config import settings

_provider_cache_lock = asyncio.Lock()
_provider_cache: dict[str, Tuple[float, BaseValidatorProvider]] = {}

def clear_provider_cache():
    _provider_cache.clear()

async def get_cached_provider(provider_name: str) -> BaseValidatorProvider:
    async with _provider_cache_lock:
        now = time.time()

        if provider_name in _provider_cache:
            # Check if in cache and still valid
            cached = _provider_cache.get(provider_name)
            if cached:
                ts, provider = cached
                if now - ts < settings.provider_cache_ttl:
                    return provider

        # Refresh and cache
        provider = get_validator_provider(provider_name)
        _provider_cache[provider_name] = (now, provider)
        return provider

async def fetch_frontend_validators(provider_name="mock") -> list[ValidatorDetail]:
    provider = await get_cached_provider(provider_name)
    return await provider.fetch_frontend_validators()

async def fetch_frontend_validator_source(file_path: str, provider_name="mock") -> str:
    provider = await get_cached_provider(provider_name)
    return await provider.fetch_frontend_validator_source(file_path)

async def fetch_frontend_base_validators_source(provider_name="mock") -> str:
    provider = await get_cached_provider(provider_name)
    return await provider.fetch_frontend_base_validators_source()
