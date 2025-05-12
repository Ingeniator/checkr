# tests/test_validators_runtime.py
import os
import json
import pytest
from services.backend_validators_registry import discover_validators_with_metadata

# Adjust path to your test data dir
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

@pytest.fixture(params=os.listdir(DATA_DIR))
def unified_test_case(request):
    file_path = os.path.join(DATA_DIR, request.param)
    with open(file_path) as f:
        content = json.load(f)
    return request.param, content["input"], content.get("expect", {})

@pytest.mark.asyncio
async def test_validators_against_unified_json(unified_test_case):
    file_name, input_data, expectations = unified_test_case

    discovered = discover_validators_with_metadata()

    for ValidatorClass, detail in discovered:
        validator_name = ValidatorClass.__name__
        expected_status = expectations.get(validator_name)

        if expected_status is None:
            print(f"⏩ {validator_name} skipped on {file_name}")
            continue

        validator = ValidatorClass()
        result = await validator.validate(input_data)

        assert result["status"] == expected_status, (
            f"❌ {validator_name} in {file_name} expected {expected_status}, got {result['status']}.\nFull result: {result}"
        )
        print(f"✅ {validator_name} passed on {file_name}")
