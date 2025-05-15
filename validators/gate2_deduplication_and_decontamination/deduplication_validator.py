"""
---
title: Deduplication Validator
description: Detects duplicate chat samples by comparing full message arrays.
tags: [decontamination, deduplication, gate2]
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail, MessagesItem
import json

class DeduplicationValidator(BaseValidator):
    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        seen = {}
        errors: list[ValidationErrorDetail] = []

        for i, item in enumerate(data):
            # Convert the "messages" list into a JSON string for hashing
            try:
                key = json.dumps([msg.model_dump() for msg in item.messages], sort_keys=True)
            except (TypeError, ValueError) as e:
                errors.append(ValidationErrorDetail(
                    index=i,
                    error=f"Unable to serialize messages for comparison: {e}",
                    code="serialization_error"
                ))
                continue

            if key in seen:
                errors.append(
                    ValidationErrorDetail(
                        index=i,
                        error=f"Sample {i} is a duplicate of sample {seen[key]}.",
                        code="duplicate_sample"
                    )
                )
            else:
                seen[key] = i
            self.report_progress(i + 1, len(data))

        return errors
