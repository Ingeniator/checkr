"""
---
title: Revizor Remote Validator
enabled: false
stage: draft
description: Run validation using revizor project
tags: [remote, gateX]
---
"""

from validators.base_remote_validator import BaseRemoteValidator

class RevizorRemoteValidator(BaseRemoteValidator):
    endpoint = "https://revizor.somewhere/validate"
