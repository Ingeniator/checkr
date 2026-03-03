"""
---
title: GABRIEL Multi-Attribute Rating Validator
description: Uses GABRIEL to rate assistant responses on multiple quality attributes (0-100 scale) with multi-run averaging and bias mitigation.
tags: [semantic, quality, gabriel, rating, gate7]
type: dataset_backend
options:
  score_threshold: 70
  attributes:
    helpfulness: "How helpful and useful the response is for addressing the user's needs"
    clarity: "How clear, well-organized, and easy to understand the response is"
    accuracy: "How factually correct and reliable the information in the response is"
  n_runs: 1
  use_dummy: false
---
"""

import base64
import io

import matplotlib.pyplot as plt
import pandas as pd

from validators.base_gabriel_validator import BaseGabrielValidator, gabriel
from validators.base_validator import MessagesItem, ValidationErrorDetail


class GabrielRateValidator(BaseGabrielValidator):
    """Rate assistant responses on multiple quality attributes using GABRIEL."""

    async def _run_gabriel(
        self, df: pd.DataFrame, text_column: str, save_dir: str
    ) -> pd.DataFrame:
        attributes = self.options.get("attributes", {
            "helpfulness": "How helpful and useful the response is for addressing the user's needs",
            "clarity": "How clear, well-organized, and easy to understand the response is",
            "accuracy": "How factually correct and reliable the information in the response is",
        })
        n_runs = self.options.get("n_runs", 1)
        model = self.config.get("model", "gpt-4o-mini")
        use_dummy = self.options.get("use_dummy", False)

        result_df = await gabriel.rate(
            df=df,
            column_name=text_column,
            attributes=attributes,
            save_dir=save_dir,
            model=model,
            n_runs=n_runs,
            use_dummy=use_dummy,
            reset_files=True,
        )
        return result_df

    def _interpret_results(
        self,
        result_df: pd.DataFrame,
        input_df: pd.DataFrame,
        data: list[MessagesItem],
    ) -> list[ValidationErrorDetail]:
        errors = []
        threshold = self.options.get("score_threshold", 70)
        attributes = self.options.get("attributes", {
            "helpfulness": "", "clarity": "", "accuracy": "",
        })
        attr_names = list(attributes.keys())

        # Find attribute columns in result (gabriel adds them as new columns)
        available_attrs = [a for a in attr_names if a in result_df.columns]
        if not available_attrs:
            return [
                ValidationErrorDetail(
                    error=f"No attribute score columns found in GABRIEL output. Expected: {attr_names}",
                    code="gabriel_no_scores",
                )
            ]

        all_avg_scores = []

        for row_idx, row in result_df.iterrows():
            item_index = int(row.get("item_index", row_idx))
            scores = {attr: float(row[attr]) for attr in available_attrs}
            avg_score = sum(scores.values()) / len(scores)
            all_avg_scores.append(avg_score)

            if avg_score < threshold:
                breakdown = ", ".join(f"{a}={scores[a]:.1f}" for a in available_attrs)
                errors.append(
                    ValidationErrorDetail(
                        index=item_index,
                        error=f"Quality score too low (avg={avg_score:.1f} < {threshold}). Breakdown: {breakdown}",
                        code="low_gabriel_score",
                    )
                )

            self.report_progress(int(row_idx) + 1, len(result_df))

        # Attach histogram on failures
        if errors and all_avg_scores:
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.hist(all_avg_scores, bins=10, color="lightgreen", edgecolor="black")
            ax.axvline(x=threshold, color="red", linestyle="--", label=f"Threshold ({threshold})")
            ax.set_title("GABRIEL Quality Score Distribution")
            ax.set_xlabel("Average Score")
            ax.set_ylabel("Frequency")
            ax.legend()
            ax.grid(True)

            buf = io.BytesIO()
            plt.tight_layout()
            fig.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)

            errors.append(
                ValidationErrorDetail(
                    index=None,
                    code="score_distribution_plot",
                    error="Score distribution attached.",
                    field="data:image/png;base64,"
                    + base64.b64encode(buf.read()).decode("utf-8"),
                )
            )

        return errors
