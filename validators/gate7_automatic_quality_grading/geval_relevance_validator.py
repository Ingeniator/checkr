"""
---
title: Assistant Relevance Validator (G-Eval Style)
description: Uses LLM as a judge to evaluate relevance of assistant responses.
tags: [semantic, relevance, geval, gate7]
options:
  score_threshold: 70
  preview_limit: 3
---
"""

from validators.base_geval_validator import BaseGEvalValidator

class GEvalRelevanceValidator(BaseGEvalValidator):
    prompt_template = (
        "You are a helpful assistant and fair assistant evaluator.\n\n"
        "Evaluate how relevant the assistant's response is to the user's message.\n"
        "Score from 1 (completely irrelevant) to 100 (highly relevant).\n\n"
        "User:\n{user}\n\n"
        "Assistant:\n{assistant}\n\n"
        "Only respond with a number from 1 to 100."
    )
    score_title = "Relevance Score"
    score_code = "low_relevance"
