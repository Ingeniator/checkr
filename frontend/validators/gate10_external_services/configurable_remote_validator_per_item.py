"""
---
title: Configurable Remote Validator Per Item
enabled: false
stage: draft
description: Run validation per item using endpoint from config
tags: [remote, gate10]
options:
  endpoint: "/api/v0/validate/backend/gate1_structural_validation/chat_struct_validator.py"
---
"""

from validators.base_remote_validator_per_item import BaseRemoteValidatorPerItem

class ConfigurableRemoteValidator(BaseRemoteValidatorPerItem):
    pass
