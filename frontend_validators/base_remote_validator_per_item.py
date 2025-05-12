"""
---
name: Remote Validator Per Item
description: It sends each item separately to a remote backend for validation, with native progress reporting.
tags: [remote]
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail
import json

# In Pyodide, use pyfetch. In CPython you might swap in requests.
try:
    from pyodide.http import pyfetch
except ImportError:
    pyfetch = None

class RemoteValidatorPerItem(BaseValidator):
    endpoint: str | None = None
    
    async def _validate(self, data: list[dict]) -> list[ValidationErrorDetail]:
        if not pyfetch:
            raise RuntimeError(f"{self.validator_name} requires pyodide HTTP support (pyfetch).")

        endpoint = self.endpoint or self.options.get("endpoint")
        if not endpoint:
            raise ValueError(f"No 'endpoint' provided in options for {self.validator_name}.")

        errors: list[ValidationErrorDetail] = []
        total = len(data)
        self.report_stage(f"validating {total} items remotely")

        for idx, item in enumerate(data):
            # Report per-item progress
            self.report_progress(idx + 1, total)

            # Send single-item request
            resp = await pyfetch(
                endpoint,
                method="POST",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"item": item, "index": idx})
            )

            # HTTP error?
            if resp.status != 200:
                text = await resp.text()
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

            if status == "fail":
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
