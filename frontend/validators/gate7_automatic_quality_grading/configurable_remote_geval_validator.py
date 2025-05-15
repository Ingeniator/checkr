"""
---
title: Configurable G-Eval Validator
description: Run custom LLM evaluation from config.
tags: [semantic, remote, geval, pyodide, dynamic]
options:
  endpoint: /validators/api/v0/g-eval
  prompt: |
    You are a helpful assistant evaluator.
    Evaluate the overall quality of the assistant\'s reply, based on how helpful, clear, relevant, and well-phrased it is.
    Respond with a number from 1 to 100 only.
    \n\nUser:\n{user}\n\nAssistant:\n{assistant}\n
  score_regex: "\\b(100|[1-9][0-9]?)(?:\\.0)?\\b"
  score_threshold: 70
  score_title: "Custom G-Eval Score"
  score_code: "low_geval_score"
  preview_limit: 3
---
"""
from validators.base_remote_validator import BaseRemoteValidator

class ConfigurableRemoteGEvalValidator(BaseRemoteValidator):
    pass
