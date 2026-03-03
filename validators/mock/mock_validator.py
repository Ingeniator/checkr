"""
---
name: Mock Validator
description: Pretend to validata data. Return always success.
tags: [mock]
---
"""

from validators.base_validator import BaseValidator, ValidationDetail, MessagesItem

class MockValidator(BaseValidator):
    async def _validate(self, data: list[MessagesItem]) -> list[ValidationDetail]:
        errors: list[ValidationDetail] = []

        return errors
