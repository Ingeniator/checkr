"""
---
name: Base Remote Validator
type: base
description: Delegates validation to a remote backend service and wraps its errors.
tags: [remote]
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail
import json

# In Pyodide, use pyfetch for HTTP. On a normal Python runtime you'd swap this out for `requests`.
try:
    from pyodide.http import pyfetch
except ImportError:
    pyfetch = None

class BaseRemoteValidator(BaseValidator):
    endpoint: str | None = None

    async def _validate(self, data: list[dict]) -> list[ValidationErrorDetail]:
        if not pyfetch:
            raise RuntimeError("RemoteValidator requires pyodide HTTP support (pyfetch).")
        
        endpoint = self.endpoint or self.options.get("endpoint")
        if not endpoint:
            raise ValueError(f"No 'endpoint' provided in options for {self.validator_name}.")

        # Report that we're about to send the request
        self.report_stage("sending to remote")
        resp = await pyfetch(
            endpoint,
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"data": data})
        )

        # HTTP‐level error
        if resp.status != 200:
            text = await resp.text()
            detail = ValidationErrorDetail(
                error=f"Remote HTTP error {resp.status}: {text}",
                index=None,
                field=None,
                code="remote_http_error"
            )
            return [detail]

        # Parse JSON
        result = await resp.json()
        status = result.get("status")
        raw_errors = result.get("errors", [])

        self.report_stage("processing response")

        # If remote says pass, return no errors
        if status == "pass":
            return []

        # If remote says fail, normalize errors
        details: list[ValidationErrorDetail] = []
        for err in raw_errors:
            if isinstance(err, dict):
                # assume keys match ValidationErrorDetail fields
                try:
                    details.append(ValidationErrorDetail(**err))
                except Exception:
                    # fallback: put the whole dict into the error message
                    details.append(ValidationErrorDetail(
                        error=f"Unexpected error format: {json.dumps(err)}",
                        index=None,
                        field=None,
                        code="remote_error_parse"
                    ))
            else:
                # string or other type
                details.append(ValidationErrorDetail(
                    error=str(err),
                    index=None,
                    field=None,
                    code="remote_error"
                ))

        return details
