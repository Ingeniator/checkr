"""Tests for GABRIEL validators with mocked gabriel calls."""

import sys
import types
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

# Create a mock gabriel module before importing validators
mock_gabriel = types.ModuleType("gabriel")


async def _mock_rate(df, column_name, attributes, save_dir, **kwargs):
    result = df.copy()
    for attr in attributes:
        result[attr] = 85.0
    return result


async def _mock_classify(df, column_name, labels, save_dir, **kwargs):
    result = df.copy()
    for label in labels:
        result[label] = False
    return result


async def _mock_rank(df, column_name, attributes, save_dir, **kwargs):
    result = df.copy()
    n = len(df)
    for attr in attributes:
        # Linearly spaced z-scores
        result[attr] = [(i / max(n - 1, 1)) * 2 - 1 for i in range(n)]
    return result


async def _mock_codify(df, column_name, categories, save_dir, **kwargs):
    result = df.copy()
    result["verbose_response"] = [True, False, True] + [False] * (len(df) - 3) if len(df) >= 3 else [True] * len(df)
    result["unclear_reasoning"] = [False, True, False] + [False] * (len(df) - 3) if len(df) >= 3 else [False] * len(df)
    return result


mock_gabriel.rate = _mock_rate
mock_gabriel.classify = _mock_classify
mock_gabriel.rank = _mock_rank
mock_gabriel.codify = _mock_codify

# Patch gabriel into sys.modules before importing validators
sys.modules["gabriel"] = mock_gabriel

SAMPLE_DATA = [
    {"messages": [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a high-level programming language."},
    ]},
    {"messages": [
        {"role": "user", "content": "Explain recursion"},
        {"role": "assistant", "content": "Recursion is when a function calls itself."},
    ]},
    {"messages": [
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "The answer is 4."},
    ]},
    {"messages": [
        {"role": "user", "content": "Tell me about AI"},
        {"role": "assistant", "content": "AI is artificial intelligence, a branch of computer science."},
    ]},
    {"messages": [
        {"role": "user", "content": "What is a database?"},
        {"role": "assistant", "content": "A database is an organized collection of structured data."},
    ]},
]


# --- GabrielRateValidator ---

class TestGabrielRateValidator:

    @pytest.mark.asyncio
    async def test_rate_all_pass(self):
        from validators.gate7_automatic_quality_grading.gabriel_rate_validator import (
            GabrielRateValidator,
        )

        validator = GabrielRateValidator(options={"score_threshold": 70})
        result = await validator.validate(SAMPLE_DATA)
        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_rate_below_threshold(self):
        from validators.gate7_automatic_quality_grading.gabriel_rate_validator import (
            GabrielRateValidator,
        )

        async def low_rate(df, column_name, attributes, save_dir, **kwargs):
            result = df.copy()
            for attr in attributes:
                result[attr] = 30.0
            return result

        with patch.object(mock_gabriel, "rate", low_rate):
            validator = GabrielRateValidator(options={"score_threshold": 70})
            result = await validator.validate(SAMPLE_DATA)
            assert result["status"] == "failed"
            errors = result["errors"]
            # 5 items + 1 histogram
            score_errors = [e for e in errors if e.get("code") == "low_gabriel_score"]
            assert len(score_errors) == 5

    @pytest.mark.asyncio
    async def test_rate_empty_data(self):
        from validators.gate7_automatic_quality_grading.gabriel_rate_validator import (
            GabrielRateValidator,
        )

        validator = GabrielRateValidator()
        result = await validator.validate([])
        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_rate_custom_attributes(self):
        from validators.gate7_automatic_quality_grading.gabriel_rate_validator import (
            GabrielRateValidator,
        )

        validator = GabrielRateValidator(options={
            "attributes": {"tone": "Professional and polite tone"},
            "score_threshold": 50,
        })
        result = await validator.validate(SAMPLE_DATA)
        assert result["status"] == "passed"


# --- GabrielClassifyValidator ---

class TestGabrielClassifyValidator:

    @pytest.mark.asyncio
    async def test_classify_no_issues(self):
        from validators.gate7_automatic_quality_grading.gabriel_classify_validator import (
            GabrielClassifyValidator,
        )

        validator = GabrielClassifyValidator()
        result = await validator.validate(SAMPLE_DATA)
        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_classify_with_issues(self):
        from validators.gate7_automatic_quality_grading.gabriel_classify_validator import (
            GabrielClassifyValidator,
        )

        async def flagged_classify(df, column_name, labels, save_dir, **kwargs):
            result = df.copy()
            label_names = list(labels.keys())
            for label in label_names:
                result[label] = False
            # Flag first item as off_topic
            if label_names:
                result.loc[0, label_names[0]] = True
            return result

        with patch.object(mock_gabriel, "classify", flagged_classify):
            validator = GabrielClassifyValidator()
            result = await validator.validate(SAMPLE_DATA)
            assert result["status"] == "failed"
            errors = result["errors"]
            label_errors = [e for e in errors if e.get("code") == "gabriel_quality_label"]
            assert len(label_errors) == 1

    @pytest.mark.asyncio
    async def test_classify_empty_data(self):
        from validators.gate7_automatic_quality_grading.gabriel_classify_validator import (
            GabrielClassifyValidator,
        )

        validator = GabrielClassifyValidator()
        result = await validator.validate([])
        assert result["status"] == "passed"


# --- GabrielRankValidator ---

GROUPED_SAMPLE_DATA = [
    # 3 responses to same prompt
    {"messages": [
        {"role": "user", "content": "Explain photosynthesis"},
        {"role": "assistant", "content": "Photosynthesis is the process by which plants convert sunlight into chemical energy."},
    ]},
    {"messages": [
        {"role": "user", "content": "Explain photosynthesis"},
        {"role": "assistant", "content": "Plants use light to make food. It happens in leaves."},
    ]},
    {"messages": [
        {"role": "user", "content": "Explain photosynthesis"},
        {"role": "assistant", "content": "idk something with plants and sun lol"},
    ]},
    # 3 responses to another prompt
    {"messages": [
        {"role": "user", "content": "What is gravity?"},
        {"role": "assistant", "content": "Gravity is a fundamental force of attraction between objects with mass."},
    ]},
    {"messages": [
        {"role": "user", "content": "What is gravity?"},
        {"role": "assistant", "content": "Gravity makes things fall down. It keeps planets in orbit."},
    ]},
    {"messages": [
        {"role": "user", "content": "What is gravity?"},
        {"role": "assistant", "content": "stuff falls"},
    ]},
]


class TestGabrielRankValidator:

    @pytest.mark.asyncio
    async def test_rank_flat_no_outliers_passes_with_info(self):
        """Flat mode with fail_on_outliers=False passes but includes ranking info."""
        from validators.gate7_automatic_quality_grading.gabriel_rank_validator import (
            GabrielRankValidator,
        )

        validator = GabrielRankValidator(options={"min_items": 3, "fail_on_outliers": False})
        result = await validator.validate(SAMPLE_DATA)
        assert result["status"] == "passed"
        # Ranking report in info channel
        assert "info" in result
        info = result["info"]
        reports = [i for i in info if i.get("code") == "gabriel_ranking_report"]
        assert len(reports) == 1
        assert "#1" in reports[0]["error"]

    @pytest.mark.asyncio
    async def test_rank_flat_detects_outlier(self):
        """Flat mode flags items far below the mean, ranking in info."""
        from validators.gate7_automatic_quality_grading.gabriel_rank_validator import (
            GabrielRankValidator,
        )

        async def outlier_rank(df, column_name, attributes, save_dir, **kwargs):
            result = df.copy()
            for attr in attributes:
                scores = [0.5] * len(df)
                scores[-1] = -3.0  # clear outlier
                result[attr] = scores
            return result

        with patch.object(mock_gabriel, "rank", outlier_rank):
            validator = GabrielRankValidator(options={
                "min_items": 3,
                "fail_on_outliers": True,
                "outlier_std_threshold": 1.5,
            })
            result = await validator.validate(SAMPLE_DATA)
            assert result["status"] == "failed"
            # Outlier in errors
            errors = result["errors"]
            outliers = [e for e in errors if e.get("code") == "gabriel_rank_outlier"]
            assert len(outliers) == 1
            assert outliers[0]["index"] == 4
            # Ranking report in info
            assert "info" in result
            reports = [i for i in result["info"] if i.get("code") == "gabriel_ranking_report"]
            assert len(reports) == 1

    @pytest.mark.asyncio
    async def test_rank_flat_no_outliers_when_close(self):
        """No outliers flagged when all scores are similar — passes with info."""
        from validators.gate7_automatic_quality_grading.gabriel_rank_validator import (
            GabrielRankValidator,
        )

        async def tight_rank(df, column_name, attributes, save_dir, **kwargs):
            result = df.copy()
            for attr in attributes:
                result[attr] = [0.50, 0.49, 0.51, 0.50, 0.50]
            return result

        with patch.object(mock_gabriel, "rank", tight_rank):
            validator = GabrielRankValidator(options={
                "min_items": 3,
                "fail_on_outliers": True,
                "outlier_std_threshold": 1.5,
            })
            result = await validator.validate(SAMPLE_DATA)
            assert result["status"] == "passed"
            assert "info" in result

    @pytest.mark.asyncio
    async def test_rank_too_few_items(self):
        from validators.gate7_automatic_quality_grading.gabriel_rank_validator import (
            GabrielRankValidator,
        )

        validator = GabrielRankValidator(options={"min_items": 10})
        result = await validator.validate(SAMPLE_DATA[:3])
        assert result["status"] == "failed"
        errors = result["errors"]
        assert any("requires at least" in e.get("error", "") for e in errors)

    @pytest.mark.asyncio
    async def test_rank_grouped_no_outliers_passes_with_info(self):
        """Grouped mode with fail_on_outliers=False passes with ranking info."""
        from validators.gate7_automatic_quality_grading.gabriel_rank_validator import (
            GabrielRankValidator,
        )

        validator = GabrielRankValidator(options={
            "min_group_size": 3,
            "fail_on_outliers": False,
        })
        result = await validator.validate(GROUPED_SAMPLE_DATA)
        assert result["status"] == "passed"
        # Ranking reports for each group in info
        assert "info" in result
        reports = [i for i in result["info"] if i.get("code") == "gabriel_ranking_report"]
        assert len(reports) == 2

    @pytest.mark.asyncio
    async def test_rank_grouped_detects_outlier(self):
        """Grouped mode flags outliers within each group."""
        from validators.gate7_automatic_quality_grading.gabriel_rank_validator import (
            GabrielRankValidator,
        )

        async def group_outlier_rank(df, column_name, attributes, save_dir, **kwargs):
            result = df.copy()
            for attr in attributes:
                scores = [0.5] * len(df)
                scores[-1] = -10.0  # extreme outlier in each group
                result[attr] = scores
            return result

        with patch.object(mock_gabriel, "rank", group_outlier_rank):
            validator = GabrielRankValidator(options={
                "min_group_size": 3,
                "fail_on_outliers": True,
                "outlier_std_threshold": 1.5,
            })
            result = await validator.validate(GROUPED_SAMPLE_DATA)
            assert result["status"] == "failed"
            errors = result["errors"]
            outliers = [e for e in errors if e.get("code") == "gabriel_rank_outlier"]
            assert len(outliers) == 2  # one outlier per group
            # Ranking reports in info channel
            assert "info" in result
            reports = [i for i in result["info"] if i.get("code") == "gabriel_ranking_report"]
            assert len(reports) == 2

    @pytest.mark.asyncio
    async def test_rank_grouped_too_small_groups_skipped(self):
        """Groups smaller than min_group_size are skipped."""
        from validators.gate7_automatic_quality_grading.gabriel_rank_validator import (
            GabrielRankValidator,
        )

        small_grouped = GROUPED_SAMPLE_DATA[:2] + GROUPED_SAMPLE_DATA[3:5]
        validator = GabrielRankValidator(options={"min_group_size": 3})
        result = await validator.validate(small_grouped)
        assert result["status"] == "failed"
        errors = result["errors"]
        assert any("at least" in e.get("error", "") for e in errors)

    @pytest.mark.asyncio
    async def test_rank_equal_scores_passes_with_info(self):
        """When all scores are identical, no outliers — passes with ranking info."""
        from validators.gate7_automatic_quality_grading.gabriel_rank_validator import (
            GabrielRankValidator,
        )

        async def equal_rank(df, column_name, attributes, save_dir, **kwargs):
            result = df.copy()
            for attr in attributes:
                result[attr] = 0.5
            return result

        with patch.object(mock_gabriel, "rank", equal_rank):
            validator = GabrielRankValidator(options={"min_items": 3, "fail_on_outliers": True})
            result = await validator.validate(SAMPLE_DATA)
            assert result["status"] == "passed"
            assert "info" in result


# --- GabrielDiscoverValidator ---

class TestGabrielDiscoverValidator:

    @pytest.mark.asyncio
    async def test_discover_above_threshold(self):
        """Patterns appearing in >=20% of items trigger failure."""
        from validators.gate7_automatic_quality_grading.gabriel_discover_validator import (
            GabrielDiscoverValidator,
        )

        # Default mock: verbose_response hits 3/5 = 60%, well above 20%
        validator = GabrielDiscoverValidator(options={"fail_on_discovery": False, "min_frequency_pct": 20})
        result = await validator.validate(SAMPLE_DATA)
        assert result["status"] == "failed"
        errors = result["errors"]
        pattern_errors = [e for e in errors if e.get("code") == "gabriel_discovered_patterns"]
        assert len(pattern_errors) == 1
        assert "verbose_response" in pattern_errors[0]["error"]

    @pytest.mark.asyncio
    async def test_discover_below_threshold_passes(self):
        """Patterns below the frequency threshold don't trigger failure."""
        from validators.gate7_automatic_quality_grading.gabriel_discover_validator import (
            GabrielDiscoverValidator,
        )

        # Default mock: verbose_response=60%, unclear_reasoning=20%
        # Set threshold to 80% so neither qualifies
        validator = GabrielDiscoverValidator(options={"min_frequency_pct": 80})
        result = await validator.validate(SAMPLE_DATA)
        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_discover_flags_individual_items(self):
        from validators.gate7_automatic_quality_grading.gabriel_discover_validator import (
            GabrielDiscoverValidator,
        )

        # min_frequency_pct=20 so verbose_response (60%) qualifies
        validator = GabrielDiscoverValidator(options={"fail_on_discovery": True, "min_frequency_pct": 20})
        result = await validator.validate(SAMPLE_DATA)
        assert result["status"] == "failed"
        errors = result["errors"]
        flagged = [e for e in errors if e.get("code") == "gabriel_pattern_flagged"]
        assert len(flagged) >= 1

    @pytest.mark.asyncio
    async def test_discover_no_patterns(self):
        from validators.gate7_automatic_quality_grading.gabriel_discover_validator import (
            GabrielDiscoverValidator,
        )

        async def empty_codify(df, column_name, categories, save_dir, **kwargs):
            return df.copy()

        with patch.object(mock_gabriel, "codify", empty_codify):
            validator = GabrielDiscoverValidator()
            result = await validator.validate(SAMPLE_DATA)
            assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_discover_empty_data(self):
        from validators.gate7_automatic_quality_grading.gabriel_discover_validator import (
            GabrielDiscoverValidator,
        )

        validator = GabrielDiscoverValidator()
        result = await validator.validate([])
        assert result["status"] == "passed"


# --- BaseGabrielValidator ---

class TestBaseGabrielValidator:

    @pytest.mark.asyncio
    async def test_messages_to_dataframe(self):
        from validators.base_gabriel_validator import BaseGabrielValidator

        df = BaseGabrielValidator.messages_to_dataframe(
            [
                type(
                    "MI",
                    (),
                    {
                        "messages": [
                            type("M", (), {"role": "user", "content": "Hello"})(),
                            type("M", (), {"role": "assistant", "content": "Hi there"})(),
                        ]
                    },
                )()
            ]
        )
        assert len(df) == 1
        assert df.iloc[0]["text"] == "Hi there"
        assert df.iloc[0]["user_text"] == "Hello"
        assert "item_index" in df.columns

    @pytest.mark.asyncio
    async def test_missing_gabriel_returns_error(self):
        """Test graceful degradation when gabriel is not installed."""
        from validators.base_gabriel_validator import BaseGabrielValidator
        import validators.base_gabriel_validator as bgv

        original_gabriel = bgv.gabriel
        bgv.gabriel = None
        try:
            # Need a concrete subclass to test
            from validators.gate7_automatic_quality_grading.gabriel_rate_validator import (
                GabrielRateValidator,
            )

            validator = GabrielRateValidator()
            result = await validator.validate(SAMPLE_DATA)
            assert result["status"] == "failed"
            errors = result["errors"]
            assert any("not installed" in e.get("error", "") for e in errors)
        finally:
            bgv.gabriel = original_gabriel
