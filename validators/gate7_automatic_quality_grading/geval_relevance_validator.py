"""
---
title: Assistant Relevance Validator (G-Eval Style)
description: Uses a custom OpenAI-compatible LLM as a judge to evaluate assistant responses.
tags: [semantic, relevance, geval, gate7]
options:
  model: thebloke/tinyllama-1.1b-chat-v1.0 #gpt-4
  score_threshold: 70
  preview_limit: 3
  api_key: "none"  # Optional for local
  api_base: http://localhost:1234/v1
---
"""

import html
import re
from openai import AsyncOpenAI
from textwrap import indent
import matplotlib.pyplot as plt
import io
import base64

from validators.base_validator import BaseValidator, ValidationErrorDetail, MessagesItem


class GEvalRelevanceValidator(BaseValidator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.client = AsyncOpenAI(
            api_key=self.options.get("api_key", None),
            base_url=self.options.get("api_base", None)
        )

    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        errors: list[ValidationErrorDetail] = []

        model = self.options.get("model", "gpt-4")
        threshold = self.options.get("score_threshold", 3.5)
        preview_limit = self.options.get("preview_limit", 3)

        dialog_avg_scores = []
        for idx, item in enumerate(data):
            user_inputs = []
            assistant_outputs = []
            preview_pairs = []

            for i in range(1, len(item.messages)):
                current = item.messages[i]
                prev = item.messages[i - 1]

                if current.role == "assistant" and prev.role == "user":
                    user_inputs.append(prev.content)
                    assistant_outputs.append(current.content)
                    preview_pairs.append((prev.content, current.content))

            if not assistant_outputs:
                errors.append(ValidationErrorDetail(
                    index=idx,
                    error="No user-assistant pairs found for relevance evaluation.",
                    code="no_valid_pairs"
                ))
                continue

            try:
                scores = []
                for u, a in zip(user_inputs, assistant_outputs):
                    prompt = (
                        f"You are a helpful and fair assistant evaluator.\n\n"
                        f"Evaluate how relevant the assistant's response is to the user's message.\n"
                        f"Score from 1 (completely irrelevant) to 100 (fully relevant).\n\n"
                        f"User message:\n{u}\n\n"
                        f"Assistant reply:\n{a}\n\n"
                        f"Only respond with a number from 1 to 100."
                    )

                    response_text = await self.call_custom_llm(prompt, model)

                    print(response_text)
                    # Try to extract score from messy LLM output                    
                    # Match a number from 1 to 100 (integer or optional ".0")
                    match = re.search(r"\b(100|[1-9][0-9]?)(?:\.0)?\b", response_text)

                    if match:
                        score = float(match.group(1))
                    else:
                        score = 0.0

                    scores.append(score)

                avg_score = sum(scores) / len(scores)
                dialog_avg_scores.append(avg_score)

                if avg_score < threshold:
                    preview_lines = []
                    for u, a in preview_pairs[:preview_limit]:
                        preview_lines.append(f"user: \"{html.escape(u)}\"")
                        preview_lines.append(f"assistant: \"{html.escape(a)}\"")
                    preview_block = indent("\n".join(preview_lines), "  ")

                    errors.append(ValidationErrorDetail(
                        index=idx,
                        error=f"Low assistant relevance (avg G-Eval score = {avg_score:.2f} < {threshold})",
                        field=f"<pre>{preview_block}</pre>",
                        code="low_relevance"
                    ))

            except Exception as e:
                errors.append(ValidationErrorDetail(
                    index=idx,
                    error=f"G-Eval call failed: {e}",
                    code="geval_error"
                ))

            self.report_progress(idx + 1, len(data))

        if len(errors) > 0 and dialog_avg_scores:
            # Create histogram of score distribution
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.hist(dialog_avg_scores, bins=10, color='skyblue', edgecolor='black')
            ax.set_title("G-Eval Score Distribution")
        ax.set_xlabel("Score")
        ax.set_ylabel("Frequency")
        ax.grid(True, linestyle="--", alpha=0.5)

        # Save plot to memory buffer
        buf = io.BytesIO()
        plt.tight_layout()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        img_data = base64.b64encode(buf.read()).decode("utf-8")

        # Attach image as a visual error
        errors.append(ValidationErrorDetail(
            index=None,
            code="score_distribution_plot",
            error=f"Score distribution plot attached as base64 PNG: data:image/png;base64,{img_data}",
            field="visualization",
        ))
        return errors

    async def call_custom_llm(self, prompt: str, model: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            if not response or not response.choices:
                raise ValueError("No choices returned from LLM response.")

            return response.choices[0].message.content.strip()

        except Exception as e:
            raise RuntimeError(f"G-Eval LLM call failed: {e}")
