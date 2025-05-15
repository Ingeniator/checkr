"""
---
title: Remote Validator Per Item
type: base
description: It sends each item separately to a remote backend for validation, with native progress reporting.
tags: [remote]
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail, MessagesItem
import json
import asyncio

# In Pyodide, use pyfetch. In CPython you might swap in requests.
try:
    from pyodide.http import pyfetch

    async def fetch_func(url, body):
        task = asyncio.create_task(pyfetch(
            url=url,
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(body)
        ))
        return await task
except ImportError:
    pyfetch = None

class BaseRemoteValidatorPerItem(BaseValidator):
    endpoint: str | None = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.endpoint = getattr(self, "endpoint", None) or self.options.get("endpoint")

    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        if not pyfetch:
            raise RuntimeError(f"{self.validator_name} requires pyodide HTTP support (pyfetch).")

        endpoint = self.endpoint
        if not endpoint:
            raise ValueError(f"No 'endpoint' provided in options for {self.validator_name}.")

        errors: list[ValidationErrorDetail] = []
        total = len(data)
        self.report_stage(f"validating {total} items remotely")

        for idx, item in enumerate(data):
            # Report per-item progress
            self.report_progress(idx + 1, total)

            # Send single-item request
            resp = await fetch_func(self.endpoint, {"dataset": [item.model_dump()], "index": idx, "options": self.options})

            # HTTP error?
            if resp.status != 200:
                try:
                    if hasattr(resp, "text"):
                        text = await resp.text()
                    elif hasattr(resp, "json"):
                        text = json.dumps(await resp.json())
                    else:
                        text = f"⚠️ Could not extract body from response: {resp}"
                except Exception as e:
                    text = f"⚠️ Failed to parse response body: {e}"
                errors.append(ValidationErrorDetail(
                    error=f"HTTP {resp.status}: {text}",
                    index=idx,
                    code="remote_http_error"
                ))
                continue

            # Parse JSON
            result = await resp.json()
            status = result.get("status")
            raw_errs = result.get("errors", [])

            if status == "failed":
                # Wrap each returned error detail
                for err in raw_errs:
                    if isinstance(err, dict):
                        # Merge remote detail with local index
                        detail = ValidationErrorDetail(
                            **{**err, "index": err.get("index", idx)}
                        )
                    else:
                        detail = ValidationErrorDetail(
                            error=str(err),
                            index=idx,
                            code="remote_item_error"
                        )
                    errors.append(detail)

        self.report_stage("complete")
        return errors
