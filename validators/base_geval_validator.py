"""
---
title: Base G-Eval Validator
type: base
description: Abstract base class for G-Eval-style validators using an LLM to produce numeric evaluation scores.
tags: [abstract, geval, score_based, semantic]
---
"""

from abc import ABC
from validators.base_validator import BaseValidator, ValidationErrorDetail, MessagesItem
import matplotlib.pyplot as plt
import html
import re
import io
import base64
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

        trasport = ContextHeaderTransport(httpx.AsyncHTTPTransport())
        httpx_client = httpx.AsyncClient(transport=trasport)

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

    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        errors = []

        model = self.config.get("model", "gpt-4")
        threshold = self.options.get("score_threshold", 70)
        preview_limit = self.options.get("preview_limit", 3)
        dialog_avg_scores = []

        for idx, item in enumerate(data):
            user_inputs, assistant_outputs, preview_pairs = [], [], []

            for i in range(1, len(item.messages)):
                curr, prev = item.messages[i], item.messages[i - 1]
                if curr.role == "assistant" and prev.role == "user":
                    user_inputs.append(prev.content)
                    assistant_outputs.append(curr.content)
                    preview_pairs.append((prev.content, curr.content))

            if not assistant_outputs:
                errors.append(ValidationErrorDetail(
                    index=idx,
                    error="No user-assistant pairs found.",
                    code="no_valid_pairs"
                ))
                continue

            try:
                scores = []
                for u, a in zip(user_inputs, assistant_outputs):
                    prompt = self.format_prompt(u, a)
                    raw = await self.call_llm(prompt, model)
                    score = self._extract_score_from_output(raw)
                    scores.append(score)

                avg_score = sum(scores) / len(scores)
                dialog_avg_scores.append(avg_score)

                if avg_score < threshold:
                    lines = []
                    for u, a in preview_pairs[:preview_limit]:
                        lines.append(f"user: \"{html.escape(u)}\"")
                        lines.append(f"assistant: \"{html.escape(a)}\"")
                    preview = html.escape("\n".join(lines))

                    errors.append(ValidationErrorDetail(
                        index=idx,
                        error=f"{self.score_title} too low (avg = {avg_score:.2f} < {threshold})",
                        field=f"<pre>{preview}</pre>",
                        code=self.score_code
                    ))

            except Exception as e:
                errors.append(ValidationErrorDetail(
                    index=idx,
                    error=f"Evaluation failed: {e}",
                    code="eval_error"
                ))

            self.report_progress(idx + 1, len(data))

        if errors and dialog_avg_scores:
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.hist(dialog_avg_scores, bins=10, color="lightgreen", edgecolor="black")
            ax.set_title(f"{self.score_title} Distribution")
            ax.set_xlabel("Score")
            ax.set_ylabel("Frequency")
            ax.grid(True)

            buf = io.BytesIO()
            plt.tight_layout()
            fig.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)

            errors.append(ValidationErrorDetail(
                index=None,
                code="score_distribution_plot",
                error="Score distribution attached.",
                field="data:image/png;base64," + base64.b64encode(buf.read()).decode("utf-8")
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
