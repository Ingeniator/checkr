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
from validators.base_geval_validator import BaseGEvalValidator, _format_trace
from validators.base_validator import MessagesItem, ValidationDetail, _resolve_item_type

_CRITERION_PROMPT = (
    "You are an objective evaluator.\n\n"
    "Evaluate the following on this criterion:\n"
    "Criterion: {criterion}\n"
    "{description}\n\n"
    "Score from 1 (very poor) to 100 (excellent).\n\n"
    "{content}\n\n"
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

    Auto-detects item type from message roles:
      - "dialog" items: one LLM call per (criterion × user→assistant pair); scores averaged per criterion.
      - "trace" items (contain system/tool/function messages): one LLM call per criterion over the full trace.

    Both paths feed the same weighted composite scoring and threshold check.
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
        info_mode = self.options.get("info_mode", False)
        model = self.config.get("model", "gpt-4")

        criteria = _normalize_rubric(raw_rubric)

        # ── Phase 1: collect (item_idx, crit_name, prompt) ───────────────────
        # dialog: one call per (criterion × pair); trace: one call per criterion.
        calls: list[tuple[int, str, str]] = []
        # item_idx → ("dialog", pairs) | ("trace", trace_str)
        item_meta: dict[int, tuple[str, Any]] = {}

        for idx, item in enumerate(data):
            itype = _resolve_item_type(item)

            if itype == "trace":
                trace_str = _format_trace(item.messages)
                item_meta[idx] = ("trace", trace_str)
                content = f"Trace:\n{trace_str}"
                for crit_name, crit in criteria.items():
                    prompt = _CRITERION_PROMPT.format(
                        criterion=crit_name, description=crit["description"], content=content,
                    )
                    calls.append((idx, crit_name, prompt))
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
                item_meta[idx] = ("dialog", pairs)
                for u, a in pairs:
                    content = f"User:\n{u}\n\nAssistant:\n{a}"
                    for crit_name, crit in criteria.items():
                        prompt = _CRITERION_PROMPT.format(
                            criterion=crit_name, description=crit["description"], content=content,
                        )
                        calls.append((idx, crit_name, prompt))

        # ── Phase 2: fire all LLM calls concurrently ─────────────────────────
        async def _call(prompt: str) -> float:
            raw = await self.call_llm(prompt, model)
            return self._extract_score_from_output(raw)

        coros = [_call(prompt) for _, _, prompt in calls]
        raw_results = await gather_with_semaphore(coros, max_concurrency=max_concurrency)

        # ── Phase 3: regroup scores by item → criterion (as list for averaging) ─
        scores_by_item: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        error_by_item: dict[int, Exception] = {}

        for (item_idx, crit_name, _), result in zip(calls, raw_results):
            if isinstance(result, BaseException):
                error_by_item.setdefault(item_idx, result)
            else:
                scores_by_item[item_idx][crit_name].append(result)

        # ── Phase 4: weighted composite + threshold ───────────────────────────
        all_composite_scores: list[float] = []

        for idx in range(len(data)):
            if idx not in item_meta:
                continue

            if idx in error_by_item:
                errors.append(ValidationDetail(
                    index=idx, error=f"Evaluation failed: {error_by_item[idx]}", code="eval_error",
                ))
                continue

            crit_scores = scores_by_item.get(idx, {})
            if not crit_scores:
                continue

            per_crit_avg: dict[str, float] = {
                name: (sum(crit_scores[name]) / len(crit_scores[name]) if crit_scores.get(name) else 0.0)
                for name in criteria
            }
            composite = sum(per_crit_avg[name] * criteria[name]["weight"] for name in criteria)
            all_composite_scores.append(composite)

            breakdown = ", ".join(
                f"{name}={per_crit_avg[name]:.1f} (w={criteria[name]['weight']:.2f})"
                for name in criteria
            )

            if info_mode:
                errors.append(ValidationDetail(
                    index=idx,
                    severity="info",
                    code="item_score",
                    error=f"Rubric composite: {composite:.1f}. Breakdown: {breakdown}",
                ))
            elif composite < threshold:
                ptype, pdata = item_meta[idx]
                if ptype == "trace":
                    clipped = pdata[:500] + "…" if len(pdata) > 500 else pdata
                    field = f"<pre>{html.escape(clipped)}</pre>"
                else:
                    lines = [
                        f"user: &quot;{html.escape(u)}&quot;\nassistant: &quot;{html.escape(a)}&quot;"
                        for u, a in pdata[:preview_limit]
                    ]
                    field = f"<pre>{chr(10).join(lines)}</pre>"
                errors.append(ValidationDetail(
                    index=idx,
                    error=f"Rubric score too low (composite={composite:.2f} < {threshold}). Breakdown: {breakdown}",
                    field=field,
                    code="low_rubric_score",
                ))

            self.report_progress(idx + 1, len(data))

        # ── Phase 5: attach histogram ─────────────────────────────────────────
        if all_composite_scores and (errors or info_mode):
            errors.append(ValidationDetail(
                index=None,
                code="score_distribution",
                error=f"Rubric Score Distribution (n={len(all_composite_scores)})",
                severity="info",
                chart=vega_histogram(
                    all_composite_scores, title="Rubric Composite Score Distribution", threshold=threshold,
                ),
            ))

        return errors


