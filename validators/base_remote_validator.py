"""
---
title: Base Remote Validator
type: base
description: Delegates validation to a remote backend service and wraps its errors.
tags: [abstract, remote]
---
"""

from abc import ABC
from validators.base_validator import BaseValidator, ValidationErrorDetail, MessagesItem
import json
import asyncio

# Detect runtime environment and define fetch_func accordingly
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
    import requests

    class FakeResponse:
        def __init__(self, resp):
            self.status = resp.status_code
            self._text = resp.text
            self._json = json.loads(resp.text)

        async def text(self): return self._text
        async def json(self): return self._json

        @property
        def ok(self): return 200 <= self.status < 300

    async def fetch_func(url, body):
        # Wrap the sync request in an async-compatible response
        resp = requests.post(
            url,
            data=json.dumps(body),
            headers={"Content-Type": "application/json"}
        )
        return FakeResponse(resp)


class BaseRemoteValidator(BaseValidator, ABC):
    endpoint: str | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.endpoint = getattr(self, "endpoint", None) or self.options.get("endpoint")

    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        if not self.endpoint:
            raise ValueError(f"No 'endpoint' provided in options for {self.validator_name}.")

        self.report_stage("sending to remote")

        # Ensure fetch is awaited properly
        payload = {
            "dataset": [item.model_dump() for item in data],
            "options": self.options,
        }
        resp = await fetch_func(self.endpoint, payload)

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
            return [ValidationErrorDetail(
                error=f"Remote HTTP error {resp.status}: {text}",
                index=None,
                field=None,
                code="remote_http_error"
            )]

        result = await resp.json()
        status = result.get("status", "passed" if resp.status == 200 else "failed")
        raw_errors = result.get("errors", [])

        self.report_stage("processing response")

        # Give time for pending tasks (Pyodide safety)
        await asyncio.sleep(0)

        if status == "passed":
            return []

        details: list[ValidationErrorDetail] = []
        for err in raw_errors:
            if isinstance(err, dict):
                try:
                    details.append(ValidationErrorDetail(**err))
                except Exception as e:
                    details.append(ValidationErrorDetail(
                        error=f"Unexpected error format: {json.dumps(err)} ({e})",
                        index=None,
                        field=None,
                        code="remote_error_parse"
                    ))
            else:
                details.append(ValidationErrorDetail(
                    error=str(err),
                    index=None,
                    field=None,
                    code="remote_error"
                ))

        return details
