import pytest
from services.frontend_validators_registry import fetch_frontend_validators
from schemas.validators import ValidatorDetail

@pytest.mark.asyncio
async def test_fetch_frontend_validators_returns_expected_validator():
    validators = await fetch_frontend_validators()

    assert isinstance(validators, list)
    assert all(isinstance(v, ValidatorDetail) for v in validators)

    validator_ids = [v.id for v in validators]
    assert "summary-style-check" in validator_ids

    summary_validator = next(v for v in validators if v.id == "summary-style-check")
    assert summary_validator.type == "frontend"
    assert summary_validator.stage == "experimental"
    assert summary_validator.source == "/frontend-validators/summary-style-check.py"
