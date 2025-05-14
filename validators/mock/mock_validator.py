"""
---
name: Mock Validator
description: Pretend to validata data. Return always success.
tags: [mock]
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail, MessagesItem

class MockValidator(BaseValidator):
    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        errors: list[ValidationErrorDetail] = []

        return errors
