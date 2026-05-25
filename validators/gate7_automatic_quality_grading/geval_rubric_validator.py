"""
---
title: G-Eval Rubric Scoring Validator
description: Uses LLM-as-judge to score assistant responses against a weighted rubric. Each criterion is evaluated independently and combined into a single weighted composite score.
tags: [semantic, quality, geval, rubric, scoring, gate7]
type: dataset_backend
options:
  rubric:
    helpfulness:
      description: "How helpful and useful the response is for addressing the user's needs"
      weight: 1.0
    clarity:
      description: "How clear, well-organized, and easy to understand the response is"
      weight: 1.0
    accuracy:
      description: "How factually correct and reliable the information in the response is"
      weight: 1.0
  score_threshold: 70
  preview_limit: 3
  max_concurrency: 10
doc:
  rubric: "Scoring rubric as a dict. Each key is a criterion name, value is an object with 'description' (what to evaluate) and 'weight' (relative importance). Weights are automatically normalized to sum to 1."
  score_threshold: "Minimum weighted composite score (0–100). Items scoring below this are flagged."
  preview_limit: "Number of low-scoring dialog turns to include in the error preview."
  max_concurrency: "Maximum number of concurrent LLM calls."
---
"""

import html
from collections import defaultdict

from utils.async_utils import gather_with_semaphore
from utils.vega_charts import vega_histogram
from validators.base_geval_validator import BaseGEvalValidator
from validators.base_validator import MessagesItem, ValidationDetail

_CRITERION_PROMPT = (
    "You are an objective evaluator.\n\n"
    "Evaluate the assistant's response on the following criterion:\n"
    "Criterion: {criterion}\n"
    "{description}\n\n"
    "Score from 1 (very poor) to 100 (excellent).\n\n"
    "User:\n{user}\n\n"
    "Assistant:\n{assistant}\n\n"
    "Only respond with a number from 1 to 100."
)


def _normalize_rubric(raw: dict) -> dict[str, dict]:
    """
    Parse and weight-normalize a rubric dict.

    Accepts two value formats:
      - Full: {"description": "...", "weight": 2.0}
      - Short: "plain description string"  (weight defaults to 1.0)

    Returns: {name: {"description": str, "weight": float}}
    where all weights sum to 1.0.
    """
    parsed: dict[str, dict] = {}
    for name, val in raw.items():
        if isinstance(val, dict):
            desc = val.get("description", "")
            w = float(val.get("weight", 1.0))
        else:
            desc = str(val)
            w = 1.0
        parsed[name] = {"description": desc, "weight": w}

    total = sum(c["weight"] for c in parsed.values()) or 1.0
    for c in parsed.values():
        c["weight"] = c["weight"] / total

    return parsed


class GEvalRubricValidator(BaseGEvalValidator):
    """
    LLM-as-judge rubric scoring validator.

    For every dialog item, fires one LLM call per (criterion, user-assistant pair).
    Scores are averaged across pairs to produce a per-criterion item score, then
    combined into a weighted composite score that is checked against score_threshold.
    """

    async def _validate(self, data: list[MessagesItem]) -> list[ValidationDetail]:
        errors: list[ValidationDetail] = []

        raw_rubric = self.options.get("rubric", {
            "helpfulness": {
                "description": "How helpful and useful the response is for addressing the user's needs",
                "weight": 1.0,
            },
            "clarity": {
                "description": "How clear, well-organized, and easy to understand the response is",
                "weight": 1.0,
            },
            "accuracy": {
                "description": "How factually correct and reliable the information in the response is",
                "weight": 1.0,
            },
        })

        threshold = self.options.get("score_threshold", 70)
        preview_limit = self.options.get("preview_limit", 3)
        max_concurrency = self.options.get("max_concurrency", 10)
        model = self.config.get("model", "gpt-4")

        criteria = _normalize_rubric(raw_rubric)

        # ── Phase 1: collect (item_idx, criterion, user, assistant) tuples ──────
        calls: list[tuple[int, str, str, str]] = []
        pairs_by_item: dict[int, list[tuple[str, str]]] = {}

        for idx, item in enumerate(data):
            pairs = [
                (item.messages[i - 1].content, item.messages[i].content)
                for i in range(1, len(item.messages))
                if item.messages[i].role == "assistant"
                and item.messages[i - 1].role == "user"
            ]

            if not pairs:
                errors.append(ValidationDetail(
                    index=idx,
                    error="No user-assistant pairs found.",
                    code="no_valid_pairs",
                ))
                continue

            pairs_by_item[idx] = pairs
            for u, a in pairs:
                for crit_name in criteria:
                    calls.append((idx, crit_name, u, a))

        # ── Phase 2: fire all LLM calls concurrently ─────────────────────────────
        async def _call(criterion_name: str, user: str, assistant: str) -> float:
            crit = criteria[criterion_name]
            prompt = _CRITERION_PROMPT.format(
                criterion=criterion_name,
                description=crit["description"],
                user=user,
                assistant=assistant,
            )
            raw = await self.call_llm(prompt, model)
            return self._extract_score_from_output(raw)

        coros = [_call(crit, u, a) for _, crit, u, a in calls]
        raw_results = await gather_with_semaphore(coros, max_concurrency=max_concurrency)

        # ── Phase 3: regroup scores by item → criterion ───────────────────────────
        scores_by_item: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        error_by_item: dict[int, Exception] = {}

        for (item_idx, crit_name, _, _), result in zip(calls, raw_results):
            if isinstance(result, BaseException):
                error_by_item.setdefault(item_idx, result)
            else:
                scores_by_item[item_idx][crit_name].append(result)

        # ── Phase 4: compute weighted composite scores and apply threshold ────────
        all_composite_scores: list[float] = []

        for idx in range(len(data)):
            if idx not in pairs_by_item:
                continue  # already reported as no-pairs error

            if idx in error_by_item:
                errors.append(ValidationDetail(
                    index=idx,
                    error=f"Evaluation failed: {error_by_item[idx]}",
                    code="eval_error",
                ))
                continue

            crit_scores = scores_by_item.get(idx, {})
            if not crit_scores:
                continue

            # Average pair-level scores → per-criterion item score
            per_crit_avg: dict[str, float] = {
                name: (sum(crit_scores[name]) / len(crit_scores[name]) if crit_scores.get(name) else 0.0)
                for name in criteria
            }

            # Weighted composite
            composite = sum(per_crit_avg[name] * criteria[name]["weight"] for name in criteria)
            all_composite_scores.append(composite)

            if composite < threshold:
                breakdown = ", ".join(
                    f"{name}={per_crit_avg[name]:.1f} (w={criteria[name]['weight']:.2f})"
                    for name in criteria
                )
                preview_lines: list[str] = []
                for u, a in pairs_by_item[idx][:preview_limit]:
                    preview_lines.append(f"user: &quot;{html.escape(u)}&quot;")
                    preview_lines.append(f"assistant: &quot;{html.escape(a)}&quot;")
                preview = "\n".join(preview_lines)

                errors.append(ValidationDetail(
                    index=idx,
                    error=(
                        f"Rubric score too low (composite={composite:.2f} < {threshold}). "
                        f"Breakdown: {breakdown}"
                    ),
                    field=f"<pre>{preview}</pre>",
                    code="low_rubric_score",
                ))

            self.report_progress(idx + 1, len(data))

        # ── Phase 5: attach histogram when there are failures ─────────────────────
        if errors and all_composite_scores:
            errors.append(ValidationDetail(
                index=None,
                code="score_distribution",
                error=f"Rubric Score Distribution (n={len(all_composite_scores)})",
                severity="info",
                chart=vega_histogram(
                    all_composite_scores,
                    title="Rubric Composite Score Distribution",
                    threshold=threshold,
                ),
            ))

        return errors


