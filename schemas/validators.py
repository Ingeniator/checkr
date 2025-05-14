from pydantic import BaseModel, model_validator
from typing import Literal, Any

from enum import Enum

class ValidatorType(str, Enum):
    dataset_frontend = "dataset/frontend"
    dataset_backend = "dataset/backend"
    artifact = "artifact"
    base = "base"

class Message(BaseModel):
    role: Literal["user", "assistant", "system", "function"]
    content: str

class DataItem(BaseModel):
    messages: list[Message]

    @model_validator(mode='before')
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if isinstance(data, dict) and "messages" in data:
            return data

        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return { "messages": data}
        raise ValueError("Expected either {'messages': [...]} or list of  dicts")

class DatasetValidationRequest(BaseModel):
    dataset: list[DataItem]
    index: int | None = None # for validation per item
    options: dict[str, Any] = {} # dict of options used by validators

class DatasetGroupValidationRequest(DatasetValidationRequest):
    dataset: list[DataItem]
    index: int | None = None
    options: dict[str, Any] = {}
    gates: list[str] = [] # array of validator's source

class ValidatorDetail(BaseModel):
    source: str # works as uid
    type: ValidatorType
    title: str
    enabled: bool = True
    stage: str
    description: str
    tags: list[str] = []
    options: dict = {}
