def test_list_dataset_validators(client):
    response = client.get("/api/v1/validators/dataset")
    assert response.status_code == 200
    data = response.json()
    assert any(v["id"] == "summary-style-check" for v in data)
    assert any(v["id"] == "task-schema-check" for v in data)

def test_get_validator_detail_success(client):
    response = client.get("/api/v1/validators/dataset/task-schema-check")
    assert response.status_code == 200
    assert response.json()["id"] == "task-schema-check"

def test_get_validator_detail_not_found(client):
    response = client.get("/api/v1/validators/dataset/unknown-validator")
    assert response.status_code == 404

def test_validate_dataset_mock(client):
    payload = {
        "dataset": {"some": "data"},
        "gates": ["task-schema-check"]
    }
    response = client.post("/api/v1/validate/dataset", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_validate_dataset_with_invalid_gate(client):
    payload = {
        "dataset": {"some": "data"},
        "gates": ["nonexistent-validator"]
    }
    response = client.post("/api/v1/validate/dataset", json=payload)
    assert response.status_code == 400
    assert "Unknown gates" in response.json()["detail"]
