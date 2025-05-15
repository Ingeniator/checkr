"""
---
title: Base Abstract Validator
type: base
description: Set validation logic and make pyodide integration
tags: [abstract]
---
"""

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, field_validator, model_validator, ValidationError
import time

try:
    from pyodide.ffi import JsProxy
except ImportError:
    JsProxy = None  # We're not in Pyodide

class Message(BaseModel):
    role: str
    content: str

class MessagesItem(BaseModel):
    messages: list[Message]

    @model_validator(mode='before')
    @classmethod
    def accept_two_input_styles(cls, value):
        # Accepts either [{"role": ..., "content": ...}, ...] or {"messages": [...]}
        if isinstance(value, dict) and "messages" in value:
            # Option 1: already in expected format
            return value
        elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
            # Option 2: a list of messages
            return {"messages": value}
        raise ValueError("Expected either a dict with 'messages' or a list of messages")


    @field_validator('messages', mode='before')
    @classmethod
    def normalize_messages(cls, value):
        if not isinstance(value, list):
            raise ValueError("messages must be a list")
        for item in value:
            if not isinstance(item, dict) or 'role' not in item or 'content' not in item:
                raise ValueError("Each message must be a dict with 'role' and 'content'")
        return value

class ValidationErrorDetail(BaseModel):
    error: str
    index: int | None = None  # None for general errors not tied to an item
    field: str |  None = None  # Optional: which field caused the error
    code: str | None = None   # Optional: machine-readable error code

class BaseValidator(ABC):

    def __init__(self, options: dict[str, Any] = None, progress_callback=None):
        self.options = options or {}
        self.progress_callback = progress_callback
        self.validator_name = self.__class__.__name__

    async def validate(self, js_data: "JsProxy | list[Any]") -> dict[str, Any]:
        """
        Entry point for Pyodide: receives JsProxy or Python list
        """
        if hasattr(js_data, "to_py"):
            raw_data = js_data.to_py()
        else:
            raw_data = js_data
        try:
            start = time.time()
            self.report_stage("starting")

            dataset = []
            for item in raw_data:
                try:
                    validated = MessagesItem.model_validate(item)
                except ValidationError as e:
                    return {
                        "status": "failed",
                        "errors": str(e),
                        "validator": self.validator_name
                    }
                dataset.append(validated)

            errors = await self._validate(dataset)
            self.report_stage(f"complete ({time.time() - start:.2f}s)")
            if errors:
                return {
                    "status": "failed",
                    "errors": [e.model_dump() if hasattr(e, "model_dump") else e.dict() for e in errors],
                    "validator": self.__class__.__name__
                }
            return {
                "status": "passed",
                "validator": self.__class__.__name__
            }
        except Exception as e:
            return {
                    "status": "failed",
                    "errors": str(e),
                    "validator": self.__class__.__name__
                }

    def report_stage(self, stage_name: str):
        if self.progress_callback:
            try:
                self.progress_callback({
                    "validator": self.__class__.__name__,
                    "stage": stage_name
                })
            except Exception as e:
                print(f"Report stage callback failed: {e}")
                pass

    def report_progress(self, current: int, total: int):
        if self.progress_callback:
            try:
                self.progress_callback({
                    "validator": self.validator_name,
                    "current": current,
                    "total": total
                })
            except Exception as e:
                print(f"Report progress callback failed: {e}")
                pass

    @abstractmethod
    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        """
        Implement this in subclasses. Must return a error array if any
        """
        pass
