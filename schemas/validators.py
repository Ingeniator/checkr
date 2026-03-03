from pydantic import BaseModel, Field, model_validator, HttpUrl
from typing import Literal, Any

from enum import Enum
import structlog

logger = structlog.get_logger()

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
    dataset: list[DataItem] | None = None  # list of data items
    dataset_url: HttpUrl | None = None  # link to dataset
    index: int | None = None # for validation per item
    options: dict[str, Any] = Field(default_factory=dict) # dict of options used by validators

    @model_validator(mode='before')
    @classmethod
    def load_from_url_if_present(cls, values):
        if values.get("dataset") is None and values.get("dataset_url"):
            import httpx
            resp = httpx.get(str(values["dataset_url"]), timeout=30)
            resp.raise_for_status()
            values["dataset"] = resp.json()
            logger.info(f"Received dataset of size {len(values['dataset'])} from {values['dataset_url']}")
        return values

    @model_validator(mode='before')
    @classmethod
    def validate_inputs(cls, values):
        if not values.get("dataset") and not values.get("dataset_url"):
            raise ValueError("Either 'dataset' or 'dataset_url' must be provided.")
        return values

class DatasetGroupValidationRequest(DatasetValidationRequest):
    dataset: list[DataItem]
    index: int | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    gates: list[str] = Field(default_factory=list) # array of validator's source

class ValidatorDetail(BaseModel):
    source: str # works as uid
    type: ValidatorType
    title: str
    enabled: bool = True
    stage: str
    description: str
    tags: list[str] = []
    options: dict = {}
