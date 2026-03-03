"""
---
title: GABRIEL Quality Classification Validator
description: Uses GABRIEL to detect negative quality labels (off-topic, hallucinated, incomplete, repetitive) in assistant responses via consensus classification.
tags: [semantic, quality, gabriel, classification, gate7]
type: dataset_backend
options:
  labels:
    off_topic: "The response does not address the user's question or request"
    hallucinated: "The response contains fabricated facts, citations, or information"
    incomplete: "The response is missing critical information or cuts off prematurely"
    repetitive: "The response contains unnecessary repetition of phrases or ideas"
  min_frequency: 0.6
  n_runs: 1
  use_dummy: false
doc:
  labels: "Quality labels to check. Each key is a label name, value is its description for the LLM. An item is flagged when a label is detected."
  min_frequency: "Consensus threshold (0-1). A label must be triggered in at least this fraction of runs to count. Higher = fewer false positives."
  n_runs: "Number of independent classification passes. Labels are confirmed by consensus across runs."
  use_dummy: "When true, uses synthetic results instead of real LLM calls. For testing only."
---
"""

import pandas as pd

from validators.base_gabriel_validator import BaseGabrielValidator, gabriel
from validators.base_validator import MessagesItem, ValidationDetail


class GabrielClassifyValidator(BaseGabrielValidator):
    """Detect negative quality labels in assistant responses using GABRIEL."""

    async def _run_gabriel(
        self, df: pd.DataFrame, text_column: str, save_dir: str
    ) -> pd.DataFrame:
        labels = self.options.get("labels", {
            "off_topic": "The response does not address the user's question or request",
            "hallucinated": "The response contains fabricated facts, citations, or information",
            "incomplete": "The response is missing critical information or cuts off prematurely",
            "repetitive": "The response contains unnecessary repetition of phrases or ideas",
        })
        n_runs = self.options.get("n_runs", 1)
        min_frequency = self.options.get("min_frequency", 0.6)
        model = self.config.get("model", "gpt-4o-mini")
        use_dummy = self.options.get("use_dummy", False)

        result_df = await gabriel.classify(
            df=df,
            column_name=text_column,
            labels=labels,
            save_dir=save_dir,
            model=model,
            n_runs=n_runs,
            min_frequency=min_frequency,
            use_dummy=use_dummy,
            reset_files=True,
        )
        return result_df

    def _interpret_results(
        self,
        result_df: pd.DataFrame,
        input_df: pd.DataFrame,
        data: list[MessagesItem],
    ) -> list[ValidationDetail]:
        errors = []
        labels = self.options.get("labels", {
            "off_topic": "", "hallucinated": "", "incomplete": "", "repetitive": "",
        })
        label_names = list(labels.keys())

        # Find label columns in result
        available_labels = [lb for lb in label_names if lb in result_df.columns]
        if not available_labels:
            return [
                ValidationDetail(
                    error=f"No label columns found in GABRIEL output. Expected: {label_names}",
                    code="gabriel_no_labels",
                )
            ]

        for row_idx, row in result_df.iterrows():
            item_index = int(row.get("item_index", row_idx))
            triggered = []

            for label in available_labels:
                val = row[label]
                # Gabriel classify returns boolean/binary columns
                if val and val != 0 and str(val).lower() not in ("false", "0", "nan", "none"):
                    triggered.append(label)

            if triggered:
                label_list = ", ".join(triggered)
                errors.append(
                    ValidationDetail(
                        index=item_index,
                        error=f"Quality issues detected: [{label_list}]",
                        code="gabriel_quality_label",
                    )
                )

            self.report_progress(int(row_idx) + 1, len(result_df))

        return errors
