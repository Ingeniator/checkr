import pytest
from services.backend_validators_registry import discover_validators_with_metadata
from schemas.validators import ValidatorDetail, ValidatorType
from validators.base_validator import BaseValidator

@pytest.mark.asyncio
async def test_backend_validators_metadata_and_classes(caplog):
    with caplog.at_level("DEBUG"):
        validators = discover_validators_with_metadata()
     # Check for log message
    for record in caplog.records:
        print(record.message)

    # Ensure we have a list of (class, detail) pairs
    assert isinstance(validators, list)
    assert len(validators) > 0
    assert all(isinstance(cls, type) and issubclass(cls, BaseValidator) for cls, _ in validators)
    assert all(isinstance(detail, ValidatorDetail) for _, detail in validators)

    # Ensure all are backend and well-formed
    for cls, detail in validators:
        assert detail.type == ValidatorType.dataset_backend
        assert detail.title
        assert detail.source.endswith(".py") or "." in detail.source  # Accept either module or file path


@pytest.mark.asyncio
async def test_all_backend_validators_execute_without_exceptions(client):
    dummy_data = [{"text": "test"}]  # Minimal mock input

    known_sources = {v: v for v in client.app.state.backend_validators_dict}

    for source in known_sources:
        validator = client.app.state.backend_validators_dict[source]
        try:
            result = await validator.validate(dummy_data)
            assert "status" in result
        except Exception as e:
            pytest.fail(f"Validator {source} raised exception: {e}")
