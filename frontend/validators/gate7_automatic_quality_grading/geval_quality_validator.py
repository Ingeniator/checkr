"""
---
title: Assistant Quality Validator (G-Eval Style)
description: Uses a custom OpenAI-compatible LLM to evaluate the overall quality of assistant responses.
tags: [semantic, quality, clarity, helpfulness, geval, gate9]
options:
  score_threshold: 70
  preview_limit: 3
---
"""

from validators.base_remote_geval_validator import BaseRemoteGEvalValidator

class GEvalQualityValidator(BaseRemoteGEvalValidator):
    prompt_template = (
        "You are a helpful assistant evaluator.\n\n"
        "Evaluate the overall quality of the assistant's reply, based on how helpful, clear, relevant, and well-phrased it is.\n"
        "Use a score from 1 (poor quality) to 100 (excellent quality).\n\n"
        "User message:\n{user}\n\n"
        "Assistant reply:\n{assistant}\n\n"
        "Only respond with a number from 1 to 100."
    )
    score_title = "Quality Score"
    score_code = "low_quality"