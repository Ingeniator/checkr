import importlib
import pkgutil
from pathlib import Path
from types import ModuleType
from typing import Type
from providers.base import BaseValidatorProvider

def get_validator_provider(provider_name: str) -> BaseValidatorProvider:
    package = "providers"
    expected_class_name = f"{provider_name.capitalize()}ValidatorProvider"

    for _, module_name, _ in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if module_name == provider_name:
            module: ModuleType = importlib.import_module(f"{package}.{module_name}")
            provider_cls: Type[BaseValidatorProvider] = getattr(module, expected_class_name, None)
            if provider_cls:
                return provider_cls()

    raise ValueError(f"Unknown or invalid provider type: {provider_name}")