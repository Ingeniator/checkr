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
from pydantic import BaseModel
import time

try:
    from pyodide.ffi import JsProxy
except ImportError:
    JsProxy = None  # We're not in Pyodide

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

    async def validate(self, js_data: "JsProxy | list[dict[str, Any]]") -> dict[str, Any]:
        """
        Entry point for Pyodide: receives JsProxy or Python list
        """
        if hasattr(js_data, "to_py"):
            data = js_data.to_py()
        else:
            data = js_data
        try:
            start = time.time()
            self.report_stage("starting")
            errors = await self._validate(data)
            self.report_stage(f"complete ({time.time() - start:.2f}s)")
            if errors:
                return {
                    "status": "fail",
                    "errors": [e.model_dump() for e in errors],
                    "validator": self.__class__.__name__
                }
            return {
                "status": "pass",
                "validator": self.__class__.__name__
            }
        except Exception as e:
            return {
                    "status": "fail",
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
    async def _validate(self, data: list[dict[str, Any]]) -> list[ValidationErrorDetail]:
        """
        Implement this in subclasses. Must return a error array if any
        """
        pass
