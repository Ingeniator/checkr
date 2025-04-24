import pytest
from services.frontend_validators_registry import fetch_frontend_validators, fetch_frontend_validator_source
from schemas.validators import ValidatorDetail, ValidatorType

@pytest.mark.asyncio
async def test_mock_fetch_frontend_validators_returns_expected_validator(caplog):
    provider_name = "mock"
    with caplog.at_level("DEBUG"):
        validators = await fetch_frontend_validators(provider_name)
     # Check for log message
    for record in caplog.records:
        print(record.message)

    # Basic type assertions
    assert isinstance(validators, list)
    assert all(isinstance(v, ValidatorDetail) for v in validators)

    # Ensure the mock validator is present
    validator_sources = [v.source for v in validators]
    assert "mock/mock-validator.py" in validator_sources

    # Get the mock validator and verify its attributes
    summary_validator = next(v for v in validators if v.source == "mock/mock-validator.py")
    assert summary_validator.type == ValidatorType.dataset_frontend
    assert summary_validator.stage == "mock"

    # Fetch and verify the content of the validator source
    content = await fetch_frontend_validator_source(summary_validator.source, provider_name)
    assert content == "Mock content"

    # Fetch and verify the content of non-existed path
    content = await fetch_frontend_validator_source("not/exist", provider_name)
    assert content == ""

@pytest.mark.asyncio
async def test_gitlab_fetch_frontend_validators_returns_expected_validator():
    provider_name = "gitlab"
    validators = await fetch_frontend_validators(provider_name)

    assert isinstance(validators, list)
    assert all(isinstance(v, ValidatorDetail) for v in validators)

    validator_sources = [v.source for v in validators]
    assert f"{provider_name}/validators/gate1_structural_validation/chat_struct_validator.py" in validator_sources

    selected_validator = next(v for v in validators if v.source == f"{provider_name}/validators/gate1_structural_validation/chat_struct_validator.py")
    assert selected_validator.type == ValidatorType.dataset_frontend
    assert selected_validator.stage == "experimental"

    content = await fetch_frontend_validator_source(selected_validator.source, provider_name)
    assert isinstance(content, str)
    assert "Chat Structure Validator" in content  # Based on known docstring/frontmatter
    assert "class" in content and "BaseValidator" in content