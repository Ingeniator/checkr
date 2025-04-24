from pydantic import BaseModel, RootModel
from typing import Any, Literal

from enum import Enum

class ValidatorType(str, Enum):
    dataset_frontend = "dataset/frontend"
    dataset_backend = "dataset/backend"
    artifact = "artifact"
    base = "base"

class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class DataItem(BaseModel):
    messages: list[Message]

class DatasetValidationRequest(BaseModel):
    dataset: list[DataItem]
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
