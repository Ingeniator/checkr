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
from validators.base_validator import BaseValidator, ValidationDetail, MessagesItem, _resolve_item_type
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


def _format_trace(messages) -> str:
    """Render a full message list as a human-readable transcript for holistic LLM evaluation."""
    return "\n\n".join(f"[{m.role.upper()}]: {m.content}" for m in messages)

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

    def _build_prompt(self, content: str) -> str:
        """Fill the single {content} slot in prompt_template.

        content is either a formatted user/assistant pair (dialog)
        or a full trace transcript — the caller decides which.
        """
        if not self.prompt_template:
            raise NotImplementedError("Subclasses must define prompt_template or override _build_prompt()")
        return self.prompt_template.format(content=content)

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
        info_mode = self.options.get("info_mode", False)
        all_avg_scores = []

        # ── Phase 1: collect (item_idx, prompt) — one per pair (dialog) or per item (trace) ──
        calls: list[tuple[int, str]] = []
        # item_idx → ("dialog", pairs) | ("trace", trace_str)
        preview_map: dict[int, tuple[str, Any]] = {}

        for idx, item in enumerate(data):
            itype = _resolve_item_type(item)

            if itype == "trace":
                trace_str = _format_trace(item.messages)
                preview_map[idx] = ("trace", trace_str)
                calls.append((idx, self._build_prompt(f"Trace:\n{trace_str}")))
            else:
                pairs = [
                    (item.messages[i - 1].content, item.messages[i].content)
                    for i in range(1, len(item.messages))
                    if item.messages[i].role == "assistant" and item.messages[i - 1].role == "user"
                ]
                if not pairs:
                    errors.append(ValidationDetail(
                        index=idx, error="No user-assistant pairs found.", code="no_valid_pairs",
                    ))
                    continue
                preview_map[idx] = ("dialog", pairs)
                for u, a in pairs:
                    calls.append((idx, self._build_prompt(f"User:\n{u}\n\nAssistant:\n{a}")))

        # ── Phase 2: fire all LLM calls concurrently ─────────────────────────
        async def _call(prompt: str) -> float:
            raw = await self.call_llm(prompt, model)
            return self._extract_score_from_output(raw)

        coros = [_call(prompt) for _, prompt in calls]
        raw_results = await gather_with_semaphore(coros, max_concurrency=max_concurrency)

        # ── Phase 3: regroup scores by item_idx ──────────────────────────────
        scores_by_item: dict[int, list[float]] = defaultdict(list)
        error_by_item: dict[int, Exception] = {}

        for (item_idx, _), result in zip(calls, raw_results):
            if isinstance(result, BaseException):
                error_by_item.setdefault(item_idx, result)
            else:
                scores_by_item[item_idx].append(result)

        # ── Phase 4: average scores, apply threshold ──────────────────────────
        for idx in range(len(data)):
            if idx not in preview_map:
                continue
            if idx in error_by_item:
                errors.append(ValidationDetail(
                    index=idx, error=f"Evaluation failed: {error_by_item[idx]}", code="eval_error",
                ))
            elif idx in scores_by_item:
                scores = scores_by_item[idx]
                avg = sum(scores) / len(scores)
                all_avg_scores.append(avg)

                if info_mode:
                    errors.append(ValidationDetail(
                        index=idx,
                        severity="info",
                        code="item_score",
                        error=f"{self.score_title}: {avg:.1f}",
                    ))
                elif avg < threshold:
                    ptype, pdata = preview_map[idx]
                    if ptype == "trace":
                        clipped = pdata[:500] + "…" if len(pdata) > 500 else pdata
                        field = f"<pre>{html.escape(clipped)}</pre>"
                    else:
                        lines = [
                            f"user: \"{html.escape(u)}\"\nassistant: \"{html.escape(a)}\""
                            for u, a in pdata[:preview_limit]
                        ]
                        field = f"<pre>{html.escape(chr(10).join(lines))}</pre>"
                    errors.append(ValidationDetail(
                        index=idx,
                        error=f"{self.score_title} too low (avg = {avg:.2f} < {threshold})",
                        field=field,
                        code=self.score_code,
                    ))
            self.report_progress(idx + 1, len(data))

        if all_avg_scores and (errors or info_mode):
            errors.append(ValidationDetail(
                index=None,
                code="score_distribution",
                error=f"{self.score_title} Distribution (n={len(all_avg_scores)})",
                severity="info",
                chart=vega_histogram(all_avg_scores, title=f"{self.score_title} Distribution", threshold=threshold),
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
    def _build_prompt(self, content: str) -> str:
        template = self.options.get("prompt", "{content}")
        return template.format(content=content)

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
