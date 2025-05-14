import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.config import settings
from core.app import lifespan
from api.validators import router as validator_router
from dotenv import load_dotenv
from pathlib import Path

@pytest.fixture(scope="package")
def test_app():
    app = FastAPI(lifespan=lifespan, root_path=settings.root_path)
    app.include_router(validator_router, prefix="/api/v0")
    # load envs
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    yield app

@pytest.fixture(scope="package")
def client(test_app):
    with TestClient(test_app) as c:
        yield c