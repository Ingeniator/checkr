from core.config import settings

def assert_response_ok(response):
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Body: {response.json()}"

def test_list_dataset_validators(client, monkeypatch):
    monkeypatch.setattr(settings, "provider_name", "mock")
    response = client.get("/api/v0/list")
    assert_response_ok(response)
    data = response.json()
    assert any(v["source"] == "mock/mock-validator.py" for v in data)

def test_get_validator_detail_success(client, monkeypatch):
    monkeypatch.setattr(settings, "provider_name", "mock")
    response = client.get("/api/v0/info/mock/mock-validator.py")
    assert_response_ok(response)
    assert response.json()["source"] == "mock/mock-validator.py"

def test_get_validator_detail_not_found(client, monkeypatch):
    monkeypatch.setattr(settings, "provider_name", "mock")
    response = client.get("/api/v0/info/unknown-validator")
    assert response.status_code == 404

def test_validate_dataset_mock(client):
    payload = {
        "dataset": [
        {
            "messages": [
                { "role": "user", "content": "Hello!" },
                { "role": "assistant", "content": "Hi there!" }
            ]
        }],
        "gates": ["backend/mock/mock_validator.py"]
    }
    response = client.post("/api/v0/validate", json=payload)
    assert_response_ok(response)
    assert response.json()["status"] == "ok"

def test_validate_dataset_with_invalid_gate(client):
    payload = {
        "dataset": [
        {
            "messages": [
                { "role": "user", "content": "Hello!" },
                { "role": "assistant", "content": "Hi there!" }
            ]
        }],
        "gates": ["nonexistent-validator"]
    }
    response = client.post("/api/v0/validate", json=payload)
    assert response.status_code == 400
    assert "Unknown gates" in response.json()["detail"]

def test_get_validator_source_success(client, monkeypatch, caplog):
    monkeypatch.setattr(settings, "provider_name", "mock")
    with caplog.at_level("DEBUG"):
        response = client.get("/api/v0/raw/mock/mock-validator.py")
    # Check for log message
    for record in caplog.records:
        print(record.message)

    assert_response_ok(response)
    assert len(response.text) > 0

def test_get_validator_source_not_found(client, monkeypatch):
    monkeypatch.setattr(settings, "provider_name", "mock")
    response = client.get("/api/v0/raw/nonexistent.py")
    assert response.status_code == 404
    assert response.json() == {"detail":"Validator not found"}
