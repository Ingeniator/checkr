from pydantic import BaseModel, RootModel
from typing import Any

class Dataset(RootModel[dict[str, Any]]): pass

class DatasetValidationRequest(BaseModel):
    dataset: Dataset
    gates: list[str] = []

class ValidatorDetail(BaseModel):
    id: str
    type: str
    stage: str
    description: str
    source: str
