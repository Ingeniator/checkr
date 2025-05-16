"""
---
title: Configurable Remote Validator
enabled: false
stage: draft
description: Run validation using endpoint from config
tags: [remote, gate10]
options:
  endpoint: "/api/v0/validate/backend/gate1_structural_validation/chat_struct_validator.py"
---
"""
from validators.base_remote_validator import BaseRemoteValidator

class ConfigurableRemoteValidator(BaseRemoteValidator):
    pass
