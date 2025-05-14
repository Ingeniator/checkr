from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse

from services.backend_validators_registry import discover_validators_with_metadata
from services.frontend_validators_registry import fetch_frontend_validators, fetch_frontend_validator_source, fetch_frontend_base_validators_source

from schemas.validators import DatasetGroupValidationRequest, ValidatorDetail, ValidatorType, DataItem, DatasetValidationRequest
from core.config import settings
from core.logging_config import setup_logging
from typing import Any

# Configure logging
logger = setup_logging().bind(module=__name__)

router = APIRouter()

async def init_validators(app: FastAPI):
    # Discover and store validators in app.state
    validators = discover_validators_with_metadata()
    app.state.public_backend_validators_details = [detail for _, detail in validators if "mock" not in detail.tags]
    app.state.backend_validators_dict = {
        detail.source: cls for cls, detail in validators
    }
    # warm-up
    logger.info(f"Warming-up: Getting frontend validators (provider={settings.provider_name})")
    frontend_validators = await fetch_frontend_validators(settings.provider_name)

async def get_list_dataset_validators(request_: Request):
    frontend_validators = await fetch_frontend_validators(settings.provider_name)
    return frontend_validators + request_.app.state.public_backend_validators_details

# === Endpoints ===
@router.get("/list", response_model=list[ValidatorDetail])
async def list_dataset_validators(request_: Request):
    return await get_list_dataset_validators(request_)

@router.get("/info/{source:path}", response_model=ValidatorDetail)
async def get_validator_detail(source: str, request_: Request):
    all_validators = await get_list_dataset_validators(request_)
    for validator in all_validators:
        if validator.source == source:
            return validator
    raise HTTPException(status_code=404, detail="Validator not found")

@router.get("/raw/base")
async def get_base_validators_source(request_: Request):
    logger.info("fetch_frontend_base_validators_source")
    return await fetch_frontend_base_validators_source(settings.provider_name)

@router.get("/raw/{source:path}", response_class=PlainTextResponse)
async def get_validator_source(source: str, request_: Request):
    all_validators = await get_list_dataset_validators(request_)
    for validator in all_validators:
        logger.debug(validator.source)
        if validator.source == source:
            if validator.type == ValidatorType.dataset_frontend:
                return await fetch_frontend_validator_source(source, settings.provider_name)
            if validator.type == ValidatorType.dataset_backend:
                return await fetch_frontend_validator_source(source, "backend")
    raise HTTPException(status_code=404, detail="Validator not found")

async def _validate(gates: [], dataset: list[DataItem], options: dict[str, Any], request_: Request):
    known_sources = {v: v for v in request_.app.state.backend_validators_dict}
    unknown = [g for g in gates if g not in known_sources]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown gates requested: {', '.join(unknown)}"
        )

    all_errors = []
    for gate in gates:
        validator = request_.app.state.backend_validators_dict[gate](options)
        raw_dataset = [item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in dataset]
        result = await validator.validate(raw_dataset)
        logger.debug(result)
        if result["status"] == "fail":
            all_errors.extend(result["errors"])
    print(all_errors)
    logger.debug(f"validate_dataset {all_errors}")
    return {
        "status": "ok" if not all_errors else "failed",
        "validated_gates": gates,
        "errors": all_errors
    }

@router.post("/validate/{source:path}")
async def validate_dataset(source: str, request: DatasetValidationRequest, request_: Request):
    return await _validate([source], request.dataset, request.options, request_)

@router.post("/validate")
async def validate_dataset_on_several_gates(request: DatasetGroupValidationRequest, request_: Request):
    return await _validate(request.gates, request.dataset, request.options, request_)

@router.post("/submit")
async def submit(request: Request):
    body = await request.json()
    print("Received body:", body)
    return {"status": "received", "body": body}

