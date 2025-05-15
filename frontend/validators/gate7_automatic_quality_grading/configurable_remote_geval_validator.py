"""
---
title: Configurable G-Eval Validator
description: Uses LLM as a judge to evaluate assistant responses with a customizable prompt.
tags: [semantic, remote, geval, pyodide, dynamic]
options:
  quality_definition: "Evaluate the overall quality of the assistant reply, based on how helpful, clear, relevant, and well-phrased it is."
  score_title: "Custom G-Eval Score"
  score_code: "low_geval_score"
  score_threshold: 70
  preview_limit: 3
---
"""
from validators.base_remote_geval_validator import BaseRemoteGEvalValidator
from validators.base_remote_geval_validator import BaseRemoteGEvalValidator

class ConfigurableRemoteGEvalValidator(BaseRemoteGEvalValidator):
    def __init__(self, *args, **kwargs):
        options = kwargs.get("options", {})

        quality_definition = options.get(
            "quality_definition",
            "Evaluate the assistant’s reply."
        )

        # Dynamically construct prompt and inject into options
        options["prompt"] = (
            f"You are a helpful assistant evaluator.\n\n"
            f"{quality_definition}\n"
            f"Use a score from 1 (poor quality) to 100 (excellent quality).\n\n"
            f"User message:\n{{user}}\n\n"
            f"Assistant reply:\n{{assistant}}\n\n"
            f"Only respond with a number from 1 to 100."
        )

        kwargs["options"] = options

        super().__init__(*args, **kwargs)
