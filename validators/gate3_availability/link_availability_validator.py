"""
---
title: Link Availability Validator
description: Checks if any links in message contents are reachable (status 200).
tags: [availability, links, gate3]
---
"""

import re
import asyncio
from validators.base_validator import BaseValidator, ValidationErrorDetail, MessagesItem
from utils.async_utils import gather_with_semaphore


URL_PATTERN = re.compile(r"https?://[^\s]+")

try:
    import js
except ImportError:
    js = None

try:
    from pyodide.ffi import JsException
except ImportError:
    JsException = Exception

class LinkAvailabilityValidator(BaseValidator):
    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        max_concurrency = self.options.get("max_concurrency", 10)

        # Check if js.safeFetch exists; fallback to js.fetch
        if js:
            fetch_func = getattr(js, "safeFetch", js.window.fetch)
        else:
            import requests

        # Phase 1: collect all (sample_idx, msg_idx, url) tuples
        url_tasks: list[tuple[int, int, str]] = []
        for i, sample in enumerate(data):
            for j, msg in enumerate(sample.messages):
                for url in URL_PATTERN.findall(msg.content):
                    url_tasks.append((i, j, url))

        # Phase 2: define per-URL check coroutine
        async def check_url(url: str) -> dict:
            if js:
                response = await fetch_func(url)
                return response.to_py() if hasattr(response, "to_py") else response
            else:
                resp = await asyncio.to_thread(requests.get, url)
                return {"ok": resp.ok, "status": resp.status_code, "text": resp.text}

        # Phase 3: fire all checks concurrently
        coros = [check_url(url) for _, _, url in url_tasks]
        results = await gather_with_semaphore(coros, max_concurrency=max_concurrency)

        # Phase 4: build errors from results
        errors: list[ValidationErrorDetail] = []
        for (i, j, url), result in zip(url_tasks, results):
            if isinstance(result, JsException):
                errors.append(ValidationErrorDetail(
                    index=i,
                    field=f"messages[{j}].content",
                    error=f"JS fetch failed for {url}: {str(result)}",
                    code="fetch_error"
                ))
            elif isinstance(result, BaseException):
                errors.append(ValidationErrorDetail(
                    index=i,
                    field=f"messages[{j}].content",
                    error=f"Python exception while fetching {url}: {str(result)}",
                    code="fetch_error"
                ))
            elif not result.get("ok", False):
                errors.append(ValidationErrorDetail(
                    index=i,
                    field=f"messages[{j}].content",
                    error=f"URL {url} returned status {result.get('status')} or error: {result.get('error', '')}",
                    code="unavailable_url"
                ))

        self.report_progress(len(data), len(data))
        return errors
