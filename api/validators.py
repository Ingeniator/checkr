from fastapi import FastAPI, APIRouter, Request, HTTPException
from pydantic import BaseModel
import httpx

from services.backend_validators_registry import discover_validators_with_metadata
from services.frontend_validators_registry import fetch_frontend_validators, fetch_frontend_validator_source

from schemas.validators import DatasetValidationRequest, ValidatorDetail, ValidatorType
from validators.base_validator import BaseValidator
from core.config import settings
from core.logging_config import setup_logging

# Configure logging
logger = setup_logging().bind(module=__name__)

router = APIRouter()

def init_validators(app: FastAPI):
    # Discover and store validators in app.state
    validators = discover_validators_with_metadata()
    app.state.public_backend_validators_details = [detail for _, detail in validators if "mock" not in detail.tags]
    app.state.backend_validators_dict = {
        detail.source: cls() for cls, detail in validators
    }

async def get_list_dataset_validators(request_: Request):
    frontend_validators = await fetch_frontend_validators(settings.provider_name)
    return frontend_validators + request_.app.state.public_backend_validators_details

# === Endpoints ===
@router.get("/validators", response_model=list[ValidatorDetail])
async def list_dataset_validators(request_: Request):
    return await get_list_dataset_validators(request_)

@router.get("/validators/info/{source:path}", response_model=ValidatorDetail)
async def get_validator_detail(source: str, request_: Request):
    logger.debug(f"get info about source={source}")
    all_validators = await get_list_dataset_validators(request_)
    for validator in all_validators:
        if validator.source == source:
            return validator
    raise HTTPException(status_code=404, detail="Validator not found")

@router.get("/validators/raw/{source:path}")
async def get_validator_source(source: str, request_: Request):
    logger.debug(f"get raw source={source}")
    all_validators = await get_list_dataset_validators(request_)
    for validator in all_validators:
        if validator.source == source and validator.type == ValidatorType.dataset_frontend:
            return await fetch_frontend_validator_source(source, settings.provider_name)
    raise HTTPException(status_code=404, detail="Validator not found")

@router.post("/validate")
async def validate_dataset(request: DatasetValidationRequest, request_: Request):
    known_sources = {v: v for v in request_.app.state.backend_validators_dict}

    unknown = [g for g in request.gates if g not in known_sources]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown gates requested: {', '.join(unknown)}"
        )

    all_errors = []
    for gate in request.gates:
        validator = request_.app.state.backend_validators_dict[gate]
        result = await validator.validate(request.dataset)
        if result["status"] == "fail":
            all_errors.extend(result["errors"])
    print(all_errors)
    logger.debug(f"validate_dataset {all_errors}")
    return {
        "status": "ok" if not all_errors else "failed",
        "validated_gates": request.gates,
        "errors": all_errors
    }
