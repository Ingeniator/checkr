"""
---
title: Base G-Eval Validator
type: base
description: Abstract base class for G-Eval-style validators using an LLM to produce numeric evaluation scores.
tags: [abstract, geval, score_based, semantic]
---
"""

from abc import ABC
from collections import defaultdict
from validators.base_validator import BaseValidator, ValidationDetail, MessagesItem
from utils.async_utils import gather_with_semaphore
from utils.vega_charts import vega_histogram
import html
import re
from openai import AsyncOpenAI
from core.config import settings
from utils.yaml import load_and_expand_yaml
import httpx
import contextvars

# Shared context var (to pass headers into the transportlayer
request_headers_vars = contextvars.ContextVar("request_headers", default={})

class ContextHeaderTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner):
        self.inner = inner
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        custom_headers = request_headers_vars.get()
        for key, value in custom_headers.items():
            request.headers[key] = value
        return await self.inner.handle_async_request(request)

class BaseGEvalValidator(BaseValidator, ABC):
    prompt_template: str = ""
    score_title: str = "Score"
    score_code: str = "low_score"
    score_regex: str = r"\b(100|[1-9][0-9]?)(?:\.0)?\b"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        config_path = settings.llm_config_path
        self.config = load_and_expand_yaml(config_path)['geval']

        transport = ContextHeaderTransport(httpx.AsyncHTTPTransport())
        httpx_client = httpx.AsyncClient(transport=transport)

        self.client = AsyncOpenAI(
            api_key=self.config.get("api_key", None),
            base_url=self.config.get("api_base", None),
            http_client=httpx_client
        )

    def format_prompt(self, user: str, assistant: str) -> str:
        if not self.prompt_template:
            raise NotImplementedError("Subclasses must define a prompt_template or override format_prompt()")
        return self.prompt_template.format(user=user, assistant=assistant)

    def _extract_score_from_output(self, raw_output: str) -> float:
        """
        Default implementation: extract score as integer between 1 and 100.
        Override if your LLM prompt format returns different structure.
        """
        match = re.search(self.score_regex, raw_output)
        return float(match.group(1)) if match else 0.0

    async def _validate(self, data: list[MessagesItem]) -> list[ValidationDetail]:
        errors = []

        model = self.config.get("model", "gpt-4")
        threshold = self.options.get("score_threshold", 70)
        preview_limit = self.options.get("preview_limit", 3)
        max_concurrency = self.options.get("max_concurrency", 10)
        dialog_avg_scores = []

        # Phase 1: collect all (item_idx, user, assistant) pairs and items with no pairs
        calls = []  # (item_idx, user, assistant)
        preview_map: dict[int, list[tuple[str, str]]] = {}
        for idx, item in enumerate(data):
            pairs = []
            for i in range(1, len(item.messages)):
                curr, prev = item.messages[i], item.messages[i - 1]
                if curr.role == "assistant" and prev.role == "user":
                    pairs.append((prev.content, curr.content))

            if not pairs:
                errors.append(ValidationDetail(
                    index=idx,
                    error="No user-assistant pairs found.",
                    code="no_valid_pairs"
                ))
                continue

            preview_map[idx] = pairs
            for u, a in pairs:
                calls.append((idx, u, a))

        # Phase 2: fire all LLM calls concurrently with semaphore
        async def _single_llm_call(user: str, assistant: str):
            prompt = self.format_prompt(user, assistant)
            raw = await self.call_llm(prompt, model)
            return self._extract_score_from_output(raw)

        coros = [_single_llm_call(u, a) for _, u, a in calls]
        raw_results = await gather_with_semaphore(coros, max_concurrency=max_concurrency)

        # Phase 3: regroup scores by item_idx
        scores_by_item: dict[int, list[float]] = defaultdict(list)
        error_by_item: dict[int, Exception] = {}
        for (item_idx, _, _), result in zip(calls, raw_results):
            if isinstance(result, BaseException):
                if item_idx not in error_by_item:
                    error_by_item[item_idx] = result
            else:
                scores_by_item[item_idx].append(result)

        # Phase 4: score + threshold check
        for idx in range(len(data)):
            if idx in error_by_item:
                errors.append(ValidationDetail(
                    index=idx,
                    error=f"Evaluation failed: {error_by_item[idx]}",
                    code="eval_error"
                ))
            elif idx in scores_by_item:
                scores = scores_by_item[idx]
                avg_score = sum(scores) / len(scores)
                dialog_avg_scores.append(avg_score)

                if avg_score < threshold:
                    lines = []
                    for u, a in preview_map[idx][:preview_limit]:
                        lines.append(f"user: \"{html.escape(u)}\"")
                        lines.append(f"assistant: \"{html.escape(a)}\"")
                    preview = html.escape("\n".join(lines))

                    errors.append(ValidationDetail(
                        index=idx,
                        error=f"{self.score_title} too low (avg = {avg_score:.2f} < {threshold})",
                        field=f"<pre>{preview}</pre>",
                        code=self.score_code
                    ))

            self.report_progress(idx + 1, len(data))

        if errors and dialog_avg_scores:
            errors.append(ValidationDetail(
                index=None,
                code="score_distribution",
                error=f"{self.score_title} Distribution (n={len(dialog_avg_scores)})",
                severity="info",
                chart=vega_histogram(
                    dialog_avg_scores,
                    title=f"{self.score_title} Distribution",
                    threshold=threshold,
                ),
            ))

        return errors

    async def call_llm(self, prompt: str, model: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.get("temperature", 0.0),
            )
            if not response or not response.choices:
                raise ValueError("No choices returned from LLM response.")

            return response.choices[0].message.content.strip()

        except Exception as e:
            raise RuntimeError(f"G-Eval LLM call failed: {e}")

"""
    Reads all key attributes (prompt_template, score_regex, score_title, score_code, etc.) from options
"""
class DynamicGEvalValidator(BaseGEvalValidator):
    def format_prompt(self, user: str, assistant: str) -> str:
        template = self.options.get("prompt", "")
        return template.format(user=user, assistant=assistant)

    def extract_score_from_output(self, raw_output: str) -> float:
        regex = self.options.get("score_regex", r"\b(100|[1-9][0-9]?)(?:\.0)?\b")
        match = re.search(regex, raw_output)
        return float(match.group(1)) if match else 0.0

    @property
    def score_title(self) -> str:
        return self.options.get("score_title", "G-Eval Score")

    @property
    def score_code(self) -> str:
        return self.options.get("score_code", "low_score")
