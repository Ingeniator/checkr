"""
---
title: Configurable Remote Validator
stage: draft
description: Run validation using endpoint from config
tags: [remote, gate10]
options:
  endpoint: "https://example.com/api/validate"
---
"""

from validators.base_remote_validator import BaseRemoteValidator

class ConfigurableRemoteValidator(BaseRemoteValidator):
    pass