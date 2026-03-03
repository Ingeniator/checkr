"""
---
title: GABRIEL Pairwise Ranking Validator
description: Uses GABRIEL pairwise ranking to compare assistant responses. Auto-groups by prompt when duplicates detected. Always reports rankings, optionally fails on outliers.
tags: [semantic, quality, gabriel, ranking, gate7]
type: dataset_backend
options:
  attributes:
    overall_quality: "Overall quality, helpfulness, and correctness of the response"
  n_rounds: 5
  min_items: 5
  min_group_size: 3
  outlier_std_threshold: 1.5
  fail_on_outliers: true
  use_dummy: false
doc:
  attributes: "Quality dimensions to rank on. Each key is an attribute name, value is its description for the LLM."
  n_rounds: "Number of pairwise comparison rounds. More rounds = more confident rankings but more LLM calls. Automatically capped at group_size - 1 for small groups."
  min_items: "Minimum dataset size for flat mode (no grouping). Raises an error if fewer items are provided."
  min_group_size: "Minimum items per prompt group in grouped mode. Groups smaller than this are skipped."
  outlier_std_threshold: "Standard deviations below the leave-one-out mean to flag as outlier. Lower = more sensitive (1.5 = moderate, 3.0 = strict, 5.0 = extreme only)."
  fail_on_outliers: "When true, items ranked significantly below their group are reported as validation errors. When false, only ranking reports are emitted."
  use_dummy: "When true, uses synthetic scores instead of real LLM calls. For testing only."
---
"""

"""
Always outputs a ranking report per group (or whole dataset):                                                                                                     
  Ranking for "Explain photosynthesis"                                                                                                                              
    #1 item[0] score=0.85 (overall_quality=0.85)
    #2 item[1] score=0.62 (overall_quality=0.62)                                                                                                                    
    #3 item[2] score=-1.20 (overall_quality=-1.20)          

  Optionally flags outliers (fail_on_outliers: true, default) using leave-one-out z-score detection:
  - For each item, computes the mean/std of all other items
  - Flags if the item is more than outlier_std_threshold (default 1.5) SDs below that leave-one-out mean
  - Ignores gaps smaller than 0.1 (z-score units) to avoid false positives from negligible differences
  - Robust to small groups since the outlier doesn't contaminate its own reference stats

  What the threshold means in plain language:

  - outlier_std_threshold: 1.5 — "flag if noticeably worse than the rest" (catches moderate outliers)
  - outlier_std_threshold: 3.0 — "flag only if clearly bad" (stricter, fewer flags)
  - outlier_std_threshold: 5.0 — "flag only extreme cases"
"""

import os

import numpy as np
import pandas as pd

from validators.base_gabriel_validator import BaseGabrielValidator, gabriel
from validators.base_validator import MessagesItem, ValidationDetail


class GabrielRankValidator(BaseGabrielValidator):
    """Compare assistant responses via GABRIEL pairwise ranking.

    Always produces a ranking report. When fail_on_outliers is true,
    items whose score is more than outlier_std_threshold standard
    deviations below the group mean are flagged as failures.

    Auto-detects grouped datasets (same prompt, multiple responses)
    and ranks within each group independently.
    """

    async def _run_gabriel(
        self, df: pd.DataFrame, text_column: str, save_dir: str
    ) -> pd.DataFrame:
        min_items = self.options.get("min_items", 5)
        min_group_size = self.options.get("min_group_size", 3)
        attributes = self.options.get("attributes", {
            "overall_quality": "Overall quality, helpfulness, and correctness of the response",
        })
        n_rounds = self.options.get("n_rounds", 5)
        model = self.config.get("model", "gpt-4o-mini")
        use_dummy = self.options.get("use_dummy", False)

        # Detect grouped mode: same user prompt with different responses
        prompt_counts = df["user_text"].value_counts()
        groups = prompt_counts[prompt_counts >= min_group_size]

        if not groups.empty:
            return await self._run_grouped(
                df, text_column, save_dir, groups.index.tolist(),
                attributes, n_rounds, model, use_dummy, min_group_size,
            )

        # Flat mode: rank across entire dataset
        if len(df) < min_items:
            raise ValueError(
                f"Pairwise ranking requires at least {min_items} items, got {len(df)}"
            )

        # Cap rounds: with N items there are only N*(N-1)/2 unique pairs,
        # so extra rounds just re-compare the same matchups.
        effective_rounds = min(n_rounds, max(1, len(df) - 1))

        result_df = await gabriel.rank(
            df=df,
            column_name=text_column,
            attributes=attributes,
            save_dir=save_dir,
            model=model,
            n_rounds=effective_rounds,
            use_dummy=use_dummy,
            reset_files=True,
        )
        return result_df

    async def _run_grouped(
        self,
        df: pd.DataFrame,
        text_column: str,
        save_dir: str,
        group_prompts: list[str],
        attributes: dict,
        n_rounds: int,
        model: str,
        use_dummy: bool,
        min_group_size: int,
    ) -> pd.DataFrame:
        """Rank within each prompt group, then reassemble."""
        all_results = []

        for group_idx, prompt in enumerate(group_prompts):
            group_df = df[df["user_text"] == prompt].copy()

            if len(group_df) < min_group_size:
                continue

            group_save_dir = os.path.join(save_dir, f"group_{group_idx}")
            os.makedirs(group_save_dir, exist_ok=True)

            # Cap rounds per group size — extra rounds just re-compare
            # the same pairs when the group is small.
            effective_rounds = min(n_rounds, max(1, len(group_df) - 1))

            group_result = await gabriel.rank(
                df=group_df.reset_index(drop=True),
                column_name=text_column,
                attributes=attributes,
                save_dir=group_save_dir,
                model=model,
                n_rounds=effective_rounds,
                use_dummy=use_dummy,
                reset_files=True,
            )

            # Restore original item_index
            group_result["item_index"] = group_df["item_index"].values[:len(group_result)]
            group_result["_rank_group"] = prompt
            all_results.append(group_result)

            self.report_progress(group_idx + 1, len(group_prompts))

        if not all_results:
            raise ValueError(
                f"No prompt groups have at least {min_group_size} responses to rank"
            )

        return pd.concat(all_results, ignore_index=True)

    def _interpret_results(
        self,
        result_df: pd.DataFrame,
        input_df: pd.DataFrame,
        data: list[MessagesItem],
    ) -> list[ValidationDetail]:
        errors = []
        fail_on_outliers = self.options.get("fail_on_outliers", True)
        outlier_threshold = self.options.get("outlier_std_threshold", 1.5)
        attributes = self.options.get("attributes", {"overall_quality": ""})
        attr_names = list(attributes.keys())

        available_attrs = [a for a in attr_names if a in result_df.columns]
        if not available_attrs:
            return [
                ValidationDetail(
                    error=f"No ranking columns found in GABRIEL output. Expected: {attr_names}",
                    code="gabriel_no_rankings",
                )
            ]

        is_grouped = "_rank_group" in result_df.columns

        if is_grouped:
            errors.extend(
                self._interpret_grouped(result_df, available_attrs, fail_on_outliers, outlier_threshold)
            )
        else:
            errors.extend(
                self._interpret_flat(result_df, available_attrs, fail_on_outliers, outlier_threshold)
            )

        return errors

    def _build_ranking_report(
        self,
        df: pd.DataFrame,
        available_attrs: list[str],
        group_label: str | None = None,
    ) -> str:
        """Build a human-readable ranking table for a set of items."""
        df = df.copy()
        df["_avg_score"] = df[available_attrs].mean(axis=1)
        ranked = df.sort_values("_avg_score", ascending=False)

        header = "Ranking"
        if group_label:
            snippet = group_label[:80]
            header = f"Ranking for \"{snippet}\""

        lines = [header]
        for rank_pos, (_, row) in enumerate(ranked.iterrows(), 1):
            idx = int(row["item_index"])
            score = row["_avg_score"]
            detail = ", ".join(f"{a}={float(row[a]):.2f}" for a in available_attrs)
            lines.append(f"  #{rank_pos} item[{idx}] score={score:.2f} ({detail})")

        return "\n".join(lines)

    def _find_outliers(
        self,
        df: pd.DataFrame,
        available_attrs: list[str],
        threshold: float,
    ) -> list[tuple[int, float, float, float, str]]:
        """Find items whose avg score is significantly below the rest.

        Uses leave-one-out comparison: for each item, compute the mean
        and std of all OTHER items. Flag if the item is more than
        `threshold` std devs below that leave-one-out mean.

        This is robust to small groups where a single outlier would
        otherwise inflate the overall std and mask itself.

        Returns list of (item_index, score, loo_mean, loo_std, score_detail).
        """
        scores = df[available_attrs].mean(axis=1)
        score_values = scores.values
        n = len(score_values)

        if n < 3:
            return []

        # Minimum absolute gap to consider meaningful (z-scores are ~[-3, 3])
        min_gap = 0.1

        outliers = []
        for i, (row_idx, row) in enumerate(df.iterrows()):
            item_score = float(score_values[i])
            others = np.concatenate([score_values[:i], score_values[i + 1:]])
            loo_mean = others.mean()
            loo_std = others.std()

            gap = loo_mean - item_score
            if gap <= min_gap:
                continue

            if loo_std == 0 or np.isnan(loo_std):
                # All other items have identical scores — any meaningful gap is an outlier
                detail = ", ".join(f"{a}={float(row[a]):.2f}" for a in available_attrs)
                outliers.append((int(row["item_index"]), item_score, loo_mean, 0.0, detail))
                continue

            if item_score < loo_mean - threshold * loo_std:
                detail = ", ".join(f"{a}={float(row[a]):.2f}" for a in available_attrs)
                outliers.append((int(row["item_index"]), item_score, loo_mean, loo_std, detail))

        return outliers

    def _interpret_grouped(
        self,
        result_df: pd.DataFrame,
        available_attrs: list[str],
        fail_on_outliers: bool,
        outlier_threshold: float,
    ) -> list[ValidationDetail]:
        results = []

        for group_name, group_df in result_df.groupby("_rank_group"):
            report = self._build_ranking_report(group_df, available_attrs, group_label=str(group_name))

            # Always emit ranking report as info
            results.append(
                ValidationDetail(
                    error=report,
                    code="gabriel_ranking_report",
                    severity="info",
                )
            )

            if not fail_on_outliers:
                continue

            prompt_snippet = str(group_name)[:60]
            for item_index, score, mean, std, detail in self._find_outliers(
                group_df, available_attrs, outlier_threshold
            ):
                results.append(
                    ValidationDetail(
                        index=item_index,
                        error=f"Outlier for \"{prompt_snippet}\": score={score:.2f} "
                              f"(mean={mean:.2f}, std={std:.2f}, "
                              f"threshold={outlier_threshold} SD below mean). {detail}",
                        code="gabriel_rank_outlier",
                    )
                )

        return results

    def _interpret_flat(
        self,
        result_df: pd.DataFrame,
        available_attrs: list[str],
        fail_on_outliers: bool,
        outlier_threshold: float,
    ) -> list[ValidationDetail]:
        results = []

        report = self._build_ranking_report(result_df, available_attrs)

        # Always emit ranking report as info
        results.append(
            ValidationDetail(
                error=report,
                code="gabriel_ranking_report",
                severity="info",
            )
        )

        if fail_on_outliers:
            for item_index, score, mean, std, detail in self._find_outliers(
                result_df, available_attrs, outlier_threshold
            ):
                results.append(
                    ValidationDetail(
                        index=item_index,
                        error=f"Outlier: score={score:.2f} "
                              f"(mean={mean:.2f}, std={std:.2f}, "
                              f"threshold={outlier_threshold} SD below mean). {detail}",
                        code="gabriel_rank_outlier",
                    )
                )

        return results
