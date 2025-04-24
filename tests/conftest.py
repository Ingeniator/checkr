import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.app import lifespan
from api.validators import router as validator_router
 
@pytest.fixture(scope="package")
def test_app():
    app = FastAPI(lifespan=lifespan)
    app.include_router(validator_router, prefix="/api/v1")
    yield app

@pytest.fixture(scope="package")
def client(test_app):
    with TestClient(test_app) as c:
        yield c