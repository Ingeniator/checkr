"""
---
name: Language & Encoding Consistency Validator
description: Checks that request and response messages are in the same, valid language.
tags: [language, encoding, gate4]
options:
  expected_lang: en
  length_threshold: 20
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail
from langdetect import detect, DetectorFactory
import re

DetectorFactory.seed = 0

# Supported languages (top 10 most-used languages globally)
SUPPORTED_LANGUAGES = {
    "en", "zh-cn", "es", "hi", "ar", "bn", "pt", "ru", "ja", "de"
}

class LanguageConsistencyValidator(BaseValidator):

    def detect_lang(self, text: str) -> str:
        """Return detected language for text, but if text is very short, return 'unknown'."""

        t = text.strip()
        if len(t) < self.options.get("length_threshold", 20):  # if too short, detection is unreliable
            return "unknown"
        try:
            return detect(t)
        except Exception:
            return "unknown"

    async def _validate(self, data: list[dict]) -> list[ValidationErrorDetail]:
        errors: list[ValidationErrorDetail] = []

        # Optionally, use a global expected language (if set)
        try:
            expected_lang = self.options.get("expected_lang", None)
        except Exception:
            expected_lang = None

        for i, item in enumerate(data):
            messages = item.get("messages", [])
            if not messages:
                continue

            try:
                # Normalize roles and get content
                roles = [m.get("role", "").strip().lower() for m in messages]
                contents = [m.get("content", "") for m in messages]

                # Detect languages and store a snippet for verbose output
                detected = []
                for text in contents:
                    lang = self.detect_lang(text) if text.strip() else "unknown"
                    snippet = text.strip()[:30] + ("..." if len(text.strip()) > 30 else "")
                    detected.append((lang, snippet))

                # Report unsupported languages (only if detected language is not 'unknown')
                for j, (lang, snippet) in enumerate(detected):
                    if lang not in SUPPORTED_LANGUAGES and lang != "unknown":
                        errors.append(ValidationErrorDetail(
                            index=i,
                            field=f"messages[{j}].content",
                            error=f"Unsupported language '{lang}' detected: \"{snippet}\"",
                            code="unsupported_language"
                        ))

                # Compare first user and first assistant message languages with verbose examples
                user_examples = [(lang, snippet) for (r, (lang, snippet)) in zip(roles, detected) if r == "user"]
                assistant_examples = [(lang, snippet) for (r, (lang, snippet)) in zip(roles, detected) if r == "assistant"]

                if user_examples and assistant_examples and user_examples[0][0] != assistant_examples[0][0]:
                    errors.append(ValidationErrorDetail(
                        index=i,
                        error=(
                            f"Mismatch between user and assistant message languages: "
                            f"user='{user_examples[0][0]}' (e.g., \"{user_examples[0][1]}\") vs. "
                            f"assistant='{assistant_examples[0][0]}' (e.g., \"{assistant_examples[0][1]}\")"
                        ),
                        code="language_mismatch"
                    ))

                # If expected language is defined, check each detected language (ignoring 'unknown')
                if expected_lang:
                    for lang, snippet in detected:
                        if lang != expected_lang and lang != "unknown":
                            errors.append(ValidationErrorDetail(
                                index=i,
                                field=f"messages[{j}].content",
                                error=(
                                    f"Language mismatch: expected '{expected_lang}', detected '{lang}' in \"{snippet}\""
                                ),
                                code="expected_language_mismatch"
                            ))

                # Check for garbled characters (e.g., Unicode replacement character)
                for j, content in enumerate(contents):
                    if re.search(r"[�\uFFFD]", content):
                        errors.append(ValidationErrorDetail(
                            index=i,
                            field=f"messages[{j}].content",
                            error="Contains garbled or invalid characters (�)",
                            code="garbled_characters"
                        ))

            except Exception as e:
                errors.append(ValidationErrorDetail(
                    index=i,
                    error=f"Language detection error: {str(e)}",
                    code="detection_exception"
                ))
            self.report_progress(i + 1, len(data))

        return errors
