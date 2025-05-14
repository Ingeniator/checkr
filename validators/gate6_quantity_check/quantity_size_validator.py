"""
---
title: Quantity / Size Check Validator
description: Checks that the dataset has enough dialogs for meaningful training.
tags: [quantity, size, gate6]
options:
  min_samples: 50
  min_turns: 2
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail, MessagesItem

class QuantitySizeValidator(BaseValidator):
    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        errors: list[ValidationErrorDetail] = []
        # Minimum number of dialogs required for training; default is 50.
        min_samples = self.options.get("min_samples", 50)
        if len(data) < min_samples:
            errors.append(ValidationErrorDetail(
                index=None,
                error=f"Dataset has only {len(data)} dialogs; at least {min_samples} are required.",
                code="too_few_dialogs"
            ))
        self.report_progress(0, len(data))
        # Optional: Check that each dialog has at least a minimum number of turns.
        min_turns = self.options.get("min_turns", 2)
        for i, item in enumerate(data):
            # Assuming each dialog is stored under the key "messages"
            dialog = item.messages
            if len(dialog) < min_turns:
                errors.append(ValidationErrorDetail(
                    index=i,
                    field="messages",
                    error=f"Dialog {i} has only {len(dialog)} turn(s); at least {min_turns} are recommended.",
                    code="too_few_turns"
                ))
            self.report_progress(i + 1, len(data))

        return errors
