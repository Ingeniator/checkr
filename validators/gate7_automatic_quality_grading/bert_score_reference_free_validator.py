"""
---
title: Assistant Relevance Validator (BERTScore)
enabled: false
description: Computes BERTScore F1 between assistant replies and user prompts (reference-free).
tags: [semantic, relevance, bertscore, gate3, per_item]
options:
  f1_threshold: 0.75
  preview_limit: 3
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail, MessagesItem
from bert_score import score
from textwrap import indent
import html

class BertScoreReferenceFreeValidator(BaseValidator):

    async def _validate(self, data: list[MessagesItem]) -> list[ValidationErrorDetail]:
        errors: list[ValidationErrorDetail] = []

        # Options with defaults
        threshold = self.options.get("f1_threshold", 0.75)
        preview_limit = self.options.get("preview_limit", 3)

        for idx, item in enumerate(data):
            user_inputs = []
            assistant_outputs = []
            preview_pairs = []

            for i in range(1, len(item.messages)):
                current = item.messages[i]
                prev = item.messages[i - 1]

                if current.role == "assistant" and prev.role == "user":
                    user_inputs.append(prev.content)
                    assistant_outputs.append(current.content)

                    u_snippet = prev.content.strip()[:60]
                    if len(prev.content.strip()) > 60:
                        u_snippet += "..."
                    a_snippet = current.content.strip()[:60]
                    if len(current.content.strip()) > 60:
                        a_snippet += "..."
                    preview_pairs.append((u_snippet, a_snippet))

            if not assistant_outputs:
                errors.append(ValidationErrorDetail(
                    index=idx,
                    error="No user-assistant pairs found for BERTScore comparison.",
                    code="no_valid_pairs"
                ))
                continue

            try:
                P, R, F1 = score(assistant_outputs, [f"Expected a response to: {u}" for u in user_inputs], lang="en", rescale_with_baseline=True)
                avg_f1 = F1.mean().item()
                print(f"[Item {idx}] Avg BERTScore F1: {avg_f1:.4f}")

                if avg_f1 < threshold:
                    # Build pretty preview block with indentation
                    # Escape HTML for safe browser rendering
                    preview_lines = []
                    for u, a in preview_pairs[:preview_limit]:
                        preview_lines.append(f"user: \"{html.escape(u)}\"")
                        preview_lines.append(f"assistant: \"{html.escape(a)}\"")
                    preview_block = indent("\n\n".join(preview_lines), "  ")

                    # Summary stays in `error`
                    error_message = f"Low assistant relevance (avg F1={avg_f1:.3f} < {threshold})"
                    errors.append(ValidationErrorDetail(
                        index=idx,
                        field=f"{preview_block}",
                        error=error_message,
                        code="low_relevance"
                    ))

            except Exception as e:
                errors.append(ValidationErrorDetail(
                    index=idx,
                    error=f"BERTScore computation failed: {str(e)}",
                    code="bertscore_error"
                ))

            self.report_progress(idx + 1, len(data))

        return errors
