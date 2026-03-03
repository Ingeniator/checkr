"""
---
title: GABRIEL Quality Pattern Discovery Validator
description: Uses GABRIEL codify to automatically discover quality patterns and issues in assistant responses without predefined categories.
tags: [semantic, quality, gabriel, discovery, gate7]
type: dataset_backend
options:
  instructions: "Identify quality issues, problematic patterns, and areas of concern in the assistant responses"
  fail_on_discovery: false
  min_frequency_pct: 20
  max_words_per_call: 1000
  n_rounds: 2
  use_dummy: false
---
"""

import pandas as pd

from validators.base_gabriel_validator import BaseGabrielValidator, gabriel
from validators.base_validator import MessagesItem, ValidationErrorDetail


class GabrielDiscoverValidator(BaseGabrielValidator):
    """Auto-discover quality patterns in assistant responses using GABRIEL codify."""

    async def _run_gabriel(
        self, df: pd.DataFrame, text_column: str, save_dir: str
    ) -> pd.DataFrame:
        instructions = self.options.get(
            "instructions",
            "Identify quality issues, problematic patterns, and areas of concern in the assistant responses",
        )
        max_words_per_call = self.options.get("max_words_per_call", 1000)
        n_rounds = self.options.get("n_rounds", 2)
        model = self.config.get("model", "gpt-4o-mini")
        use_dummy = self.options.get("use_dummy", False)

        result_df = await gabriel.codify(
            df=df,
            column_name=text_column,
            categories=None,
            save_dir=save_dir,
            model=model,
            n_rounds=n_rounds,
            use_dummy=use_dummy,
            max_words_per_call=max_words_per_call,
            additional_instructions=instructions,
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
        fail_on_discovery = self.options.get("fail_on_discovery", False)
        min_frequency_pct = self.options.get("min_frequency_pct", 20)

        # Identify discovered category columns (everything not in original df)
        original_cols = set(input_df.columns)
        discovered_cols = [
            c for c in result_df.columns if c not in original_cols
        ]

        if not discovered_cols:
            return []

        # Compute frequency of each discovered pattern
        pattern_summary = {}
        for col in discovered_cols:
            count = 0
            for val in result_df[col]:
                if val and str(val).lower() not in ("false", "0", "nan", "none", ""):
                    count += 1
            if count > 0:
                pattern_summary[col] = count

        if not pattern_summary:
            return []

        # Split patterns by threshold
        n_items = len(result_df)
        above_threshold = {}
        below_threshold = {}
        for pattern, count in pattern_summary.items():
            pct = count / n_items * 100
            if pct >= min_frequency_pct:
                above_threshold[pattern] = count
            else:
                below_threshold[pattern] = count

        # Always include an informational summary of all patterns
        summary_lines = []
        for pattern, count in sorted(
            pattern_summary.items(), key=lambda x: x[1], reverse=True
        ):
            pct = count / n_items * 100
            marker = " **" if pattern in above_threshold else ""
            summary_lines.append(f"  - {pattern}: {count}/{n_items} ({pct:.0f}%){marker}")

        # Only fail if patterns exceed the threshold
        if not above_threshold:
            return []

        errors.append(
            ValidationErrorDetail(
                error=f"Discovered quality patterns above {min_frequency_pct}% threshold:\n"
                + "\n".join(summary_lines),
                code="gabriel_discovered_patterns",
            )
        )

        # Optionally flag individual items (only for above-threshold patterns)
        if fail_on_discovery:
            flagged_cols = list(above_threshold.keys())
            for row_idx, row in result_df.iterrows():
                item_index = int(row.get("item_index", row_idx))
                item_patterns = []

                for col in flagged_cols:
                    val = row[col]
                    if val and str(val).lower() not in (
                        "false", "0", "nan", "none", "",
                    ):
                        item_patterns.append(col)

                if item_patterns:
                    errors.append(
                        ValidationErrorDetail(
                            index=item_index,
                            error=f"Patterns found: [{', '.join(item_patterns)}]",
                            code="gabriel_pattern_flagged",
                        )
                    )

                self.report_progress(int(row_idx) + 1, len(result_df))

        return errors
