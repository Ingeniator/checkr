"""
---
name: Data Balance & Distribution Validator (Dialogs)
description: Checks if the dialogs dataset is balanced by analyzing dialog length and role distribution.
tags: [data, balance, distribution, gate5]
options:
  min_length: 2
  max_length: 20
  min_user_assistant_ratio: 0.5
  max_user_assistant_ratio: 1.5
---
"""

from validators.base_validator import BaseValidator, ValidationErrorDetail
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64

class DialogBalanceValidator(BaseValidator):
    async def _validate(self, data: list[dict]) -> list[ValidationErrorDetail]:
        errors: list[ValidationErrorDetail] = []

        # Extract configurable options with defaults
        min_length = self.options.get("min_length", 2)
        max_length = self.options.get("max_length", 20)
        min_ratio = self.options.get("min_user_assistant_ratio", 0.5)
        max_ratio = self.options.get("max_user_assistant_ratio", 1.5)
        
        # Assume each item in data is a dialog, e.g.:
        # {
        #   "messages": [
        #       {"role": "user", "content": "Hello"},
        #       {"role": "assistant", "content": "Hi, how can I help?"}
        #   ]
        # }
        stage = 0
        total_stages = 4
        self.report_progress(stage, total_stages)
        # Convert dialogs into a DataFrame with one row per dialog
        dialogs = []
        for i, item in enumerate(data):
            dialog = item.get("messages", [])
            if not dialog:
                continue
            dialogs.append({
                "dialog_index": i,
                "length": len(dialog),
                "user_count": sum(1 for msg in dialog if msg.get("role", "").lower() == "user"),
                "assistant_count": sum(1 for msg in dialog if msg.get("role", "").lower() == "assistant")
            })
        
        if not dialogs:
            errors.append(ValidationErrorDetail(
                index=None,
                error="No dialogs found in the dataset.",
                code="empty_dataset"
            ))
            return errors
        stage+=1
        self.report_progress(stage, total_stages)

        df = pd.DataFrame(dialogs)
        
        # Check 1: Distribution of dialog lengths
        avg_length = df["length"].mean()
        if avg_length < min_length:
            errors.append(ValidationErrorDetail(
                index=None,
                error=f"Dialogs seem too short on average ({avg_length:.1f} turns).",
                code="dialog_too_short"
            ))
        elif avg_length > max_length:
            errors.append(ValidationErrorDetail(
                index=None,
                error=f"Dialogs seem excessively long on average ({avg_length:.1f} turns).",
                code="long_dialogs"
            ))
        stage+=1
        self.report_progress(stage, total_stages)

        # Check 2: Ratio of user to assistant messages
        df["role_ratio"] = df["user_count"] / (df["assistant_count"] + 1e-6)  # avoid division by zero
        avg_ratio = df["role_ratio"].mean()
        if avg_ratio < min_ratio:
            errors.append(ValidationErrorDetail(
                index=None,
                error=f"User messages are underrepresented (user/assistant ratio: {avg_ratio:.2f}).",
                code="user_underrepresented"
            ))
        elif avg_ratio > max_ratio:
            errors.append(ValidationErrorDetail(
                index=None,
                error=f"User messages are overrepresented (user/assistant ratio: {avg_ratio:.2f}).",
                code="user_overrepresented"
            ))
        stage+=1
        self.report_progress(stage, total_stages)

        # Optional: Create a distribution plot and attach it to errors for review
        fig, ax = plt.subplots(figsize=(6, 4))
        df["length"].plot(kind="hist", ax=ax, bins=10)
        ax.set_title("Dialog Length Distribution")
        ax.set_xlabel("Number of turns")
        buf = io.BytesIO()
        plt.tight_layout()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        img_data = base64.b64encode(buf.read()).decode("utf-8")
        errors.append(ValidationErrorDetail(
            index=None,
            error=f"Dialog length distribution plot attached as base64 PNG: data:image/png;base64,{img_data}",
            code="dialog_length_plot",
            field="visualization",
        ))
        stage+=1
        self.report_progress(stage, total_stages)
        
        return errors
