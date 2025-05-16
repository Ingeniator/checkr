"""
---
title: Base Remote G-Eval Validator
type: base
description: Delegates g-eval validation to a remote backend service and wraps its errors.
tags: [abstract, remote, geval]
---
"""

from abc import ABC
from validators.base_remote_validator import BaseRemoteValidator

class BaseRemoteGEvalValidator(BaseRemoteValidator, ABC):
    # Fixed endpoint for G-Eval backend
    endpoint = "/validators/api/v0/g-eval"

    inject_keys = ["prompt", "score_title", "score_code", "score_regex"]

    def _inject_keys(self):
         for key in self.inject_keys:
            attr = key if key != "prompt" else "prompt_template"
            value = getattr(self, attr, None)
            if value is not None:
                self.options.setdefault(key, value)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._inject_keys()    
