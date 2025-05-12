"""
---
name: Guardrail Compliance Validator
description: Checks dialogs for toxic/offensive content and potential PII using better-profanity and scrubadub.
tags: [guardrails, toxicity, pii, safety, gate8]
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail
import re

# Attempt to import better_profanity and scrubadub
try:
    from better_profanity import profanity
except ImportError:
    profanity = None

import sys
import types

if "srsly" not in sys.modules:
    dummy_srsly = types.ModuleType("srsly")
    dummy_srsly.__version__ = "0.0.0"
    # Define any functions that scrubadub might call
    dummy_srsly.load = lambda *args, **kwargs: None
    dummy_srsly.save = lambda *args, **kwargs: None
    sys.modules["srsly"] = dummy_srsly
    
import scrubadub
# try:
#     import scrubadub
# except ImportError:
#     scrubadub = None

class GuardrailComplianceValidator(BaseValidator):
    async def _validate(self, data: list[dict]) -> list[ValidationErrorDetail]:
        errors: list[ValidationErrorDetail] = []
        total = sum(len(item.get("messages", [])) for item in data)
        current = 0
        for i, item in enumerate(data):
            messages = item.get("messages", [])
            for j, msg in enumerate(messages):
                content = msg.get("content", "")
                snippet = content[:30] + ("..." if len(content) > 30 else "")
                field_path = f"messages[{j}].content"
                # Toxicity check using better-profanity
                if profanity:
                    if profanity.contains_profanity(content):
                        errors.append(ValidationErrorDetail(
                            index=i,
                            field=field_path,
                            error=f"Toxic content detected: \"{snippet}\"",
                            code="toxic_content"
                        ))
                else:
                    errors.append(ValidationErrorDetail(
                        index=i,
                        field=field_path,
                        error="Profanity check failed: better_profanity not installed.",
                        code="missing_dependency"
                    ))
                
                # PII detection using scrubadub
                if scrubadub:
                    # scrubadub.clean() returns a cleaned version of the text.
                    cleaned = scrubadub.clean(content)
                    if cleaned != content:
                        errors.append(ValidationErrorDetail(
                            index=i,
                            field=field_path,
                            error=f"Potential PII detected. Cleaned version: \"{cleaned[:30]}...\"",
                            code="pii_detected"
                        ))
                else:
                    errors.append(ValidationErrorDetail(
                        index=i,
                        field=field_path,
                        error="PII check failed: scrubadub not installed.",
                        code="missing_dependency"
                    ))
                
                # Example check: basic formatting issue (e.g., excessive markdown)
                if re.search(r"([*_]{3,})", content):
                    errors.append(ValidationErrorDetail(
                        index=i,
                        field=field_path,
                        error="Formatting issue: excessive markdown characters.",
                        code="formatting_issue"
                    ))
                current += 1
                self.report_progress(current, total)
        return errors
