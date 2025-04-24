from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import httpx

from services.backend_validators_registry import build_backend_proxy_entries
from services.frontend_validators_registry import fetch_frontend_validators

from schemas.validators import DatasetValidationRequest, ValidatorDetail

router = APIRouter()

# === Endpoints ===
@router.get("/validators/dataset/", response_model=list[ValidatorDetail])
async def list_dataset_validators():
    frontend = await fetch_frontend_validators()
    backend = await build_backend_proxy_entries()
    return frontend + backend

@router.get("/validators/dataset/{id}", response_model=ValidatorDetail)
async def get_validator_detail(id: str):
    all_validators = await list_dataset_validators()
    for validator in all_validators:
        if validator.id == id:
            return validator
    raise HTTPException(status_code=404, detail="Validator not found")

@router.post("/validate/dataset")
async def validate_dataset(request: DatasetValidationRequest):
    all_validators = await list_dataset_validators()
    known_ids = {v.id for v in all_validators}

    unknown = [g for g in request.gates if g not in known_ids]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown gates requested: {', '.join(unknown)}"
        )

    # Dummy validation logic
    return {
        "status": "ok",
        "validated_gates": request.gates,
        "errors": []
    }
