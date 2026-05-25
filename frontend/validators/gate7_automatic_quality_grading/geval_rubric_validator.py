"""
---
title: G-Eval Rubric Scoring Validator
description: Uses LLM-as-judge to score assistant responses against a weighted rubric. Each criterion is evaluated independently and combined into a weighted composite score.
tags: [semantic, quality, geval, rubric, scoring, gate7]
type: dataset_frontend
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

from validators.base_remote_validator import BaseRemoteValidator


class GEvalRubricValidator(BaseRemoteValidator):
    """Delegates rubric scoring to the /rubric-eval backend endpoint."""

    endpoint = "/validators/api/v0/rubric-eval"
