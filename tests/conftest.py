import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.validators import router as validator_router

@pytest.fixture(scope="module")
def test_app():
    app = FastAPI()
    app.include_router(validator_router, prefix="/api/v1")
    yield app

@pytest.fixture(scope="module")
def client(test_app):
    return TestClient(test_app)