"""
---
name: Link Availability Validator
description: Checks if any links in message contents are reachable (status 200).
tags: [availability, links, gate3]
---
"""

import re
from validators.base_validator import BaseValidator, ValidationErrorDetail


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
    async def _validate(self, data: list[dict]) -> list[ValidationErrorDetail]:
        errors: list[ValidationErrorDetail] = []
       
        total = sum(len(item.get("messages", [])) for item in data)

        # Check if js.safeFetch exists; fallback to js.fetch
        if js:
            fetch_func = getattr(js, "safeFetch", js.window.fetch)
        else:
            # fallback for local testing (requests, aiohttp, etc.)
            import requests
            def fetch_func(url):
                resp = requests.get(url)
                return {
                    "ok": resp.ok,
                    "status": resp.status_code,
                    "text": resp.text
                }

        current = 0

        for i, sample in enumerate(data):
            messages = sample.get("messages", [])
            for j, msg in enumerate(messages):
                content = msg.get("content", "")
                urls = URL_PATTERN.findall(content)

                for url in urls:
                    try:
                        if js:
                            response = await fetch_func(url)
                            result = response.to_py() if hasattr(response, "to_py") else response
                        else:
                            result = fetch_func(url)

                        if not result.get("ok", False):
                            errors.append(ValidationErrorDetail(
                                index=i,
                                field=f"messages[{j}].content",
                                error=f"URL {url} returned status {result.get('status')} or error: {result.get('error', '')}",
                                code="unavailable_url"
                            ))
                    except JsException as e:
                        errors.append(ValidationErrorDetail(
                            index=i,
                            field=f"messages[{j}].content",
                            error=f"JS fetch failed for {url}: {str(e)}",
                            code="fetch_error"
                        ))
                    except Exception as e:
                        errors.append(ValidationErrorDetail(
                            index=i,
                            field=f"messages[{j}].content",
                            error=f"Python exception while fetching {url}: {str(e)}",
                            code="fetch_error"
                        ))
            current += 1
            self.report_progress(current, total)
        return errors
