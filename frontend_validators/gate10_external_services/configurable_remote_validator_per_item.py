"""
---
title: Configurable Remote Validator Per Item
stage: draft
description: Run validation per item using endpoint from config
tags: [remote, gate10]
options:
  endpoint: "https://example.com/api/validate"
---
"""

from validators.base_remote_validator_per_item import BaseRemoteValidatorPerItem

class ConfigurableRemoteValidator(BaseRemoteValidatorPerItem):
    pass