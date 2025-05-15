# backend_validators_registry.py
import importlib
from pathlib import Path
from typing import Type, List, Tuple
from validators.base_validator import BaseValidator
from schemas.validators import ValidatorDetail, ValidatorType
from utils.frontmatter import extract_frontmatter_from_file
from core.logging_config import setup_logging

logger = setup_logging()

VALIDATORS_PACKAGE = "validators"
VALIDATORS_PATH = Path(__file__).parent.parent / VALIDATORS_PACKAGE
SOURCE_PREFIX="backend"

def discover_validators_with_metadata() -> List[Tuple[Type[BaseValidator], ValidatorDetail]]:
    results: List[Tuple[Type[BaseValidator], ValidatorDetail]] = []

    for file_path in VALIDATORS_PATH.rglob("*.py"):
        if file_path.name == "base_validator.py":
            continue
        
        rel_path = file_path.relative_to(VALIDATORS_PATH)
        module_name = f"{VALIDATORS_PACKAGE}." + ".".join(rel_path.with_suffix("").parts)

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            logger.warning(f"⚠️ Skipping {file_path} (couldn't load spec)")
            continue

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning(f"⚠️ Failed to import {file_path}: {e}")
            continue

        front = extract_frontmatter_from_file(file_path)

        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and issubclass(obj, BaseValidator) and obj is not BaseValidator:
                raw_tags = front.get("tags", [])
                tags = raw_tags if isinstance(raw_tags, list) else [raw_tags] if raw_tags else []
                validator_type = front.get("type", ValidatorType.dataset_backend)
                # Skip abstract/base validators
                if validator_type == "base":
                    continue
                results.append((
                    obj,
                    ValidatorDetail(
                        title=front.get("title", Path(file_path).stem),
                        enabled=front.get("enabled", True),
                        type=ValidatorType.dataset_backend,
                        stage=front.get("stage", "experimental"),
                        description=front.get("description", ""),
                        tags=tags,
                        options=front.get("options", {}),
                        source=f"{SOURCE_PREFIX}/{rel_path}"
                    )
                ))
                logger.debug(f'Discovered validator source: {SOURCE_PREFIX}/{rel_path}')

    return results
