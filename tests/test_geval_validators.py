"""Tests for GEval (LLM-as-a-judge) validators with mocked LLM calls."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

_MOCK_LLM_CONFIG = {
    "geval": {
        "model": "mock-model",
        "api_key": "mock-key",
        "api_base": "http://mock",
        "temperature": 0.0,
    }
}

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
        {"role": "assistant", "content": "4"},
    ]},
]

NO_PAIRS_DATA = [
    {"messages": [
        {"role": "assistant", "content": "Hello!"},
    ]},
    {"messages": [
        {"role": "user", "content": "Hi"},
        {"role": "user", "content": "Anyone there?"},
    ]},
]

# Multi-turn agent traces: system + tool messages alongside user/assistant
AGENT_TRACES = [
    {"messages": [
        {"role": "system",    "content": "You are a travel booking agent."},
        {"role": "user",      "content": "Book me a flight to Paris next Friday."},
        {"role": "assistant", "content": "I'll search for available flights."},
        {"role": "tool",      "content": '{"flights": [{"id": "BA123", "price": 450}]}'},
        {"role": "assistant", "content": "Found one option: BA123 for €450. Shall I book it?"},
        {"role": "user",      "content": "Yes, book it."},
        {"role": "assistant", "content": "Booked! Confirmation: CONF-42."},
    ]},
    {"messages": [
        {"role": "system",    "content": "You are a data analyst agent."},
        {"role": "user",      "content": "Summarise last quarter's sales."},
        {"role": "assistant", "content": "Fetching the sales data now."},
        {"role": "tool",      "content": '{"total": 120000, "units": 340}'},
        {"role": "assistant", "content": "Last quarter: €120k revenue, 340 units sold."},
    ]},
]


@pytest.fixture(autouse=True)
def _patch_geval_init():
    """Suppress real config loading and OpenAI client creation for all tests."""
    with patch("validators.base_geval_validator.load_and_expand_yaml", return_value=_MOCK_LLM_CONFIG), \
         patch("validators.base_geval_validator.AsyncOpenAI"), \
         patch("validators.base_geval_validator.httpx.AsyncClient"), \
         patch("validators.base_geval_validator.httpx.AsyncHTTPTransport"):
        yield


# ── GEvalRelevanceValidator ───────────────────────────────────────────────────

class TestGEvalRelevanceValidator:

    @pytest.mark.asyncio
    async def test_all_pass_above_threshold(self):
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="85")):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "passed"
        assert "errors" not in result

    @pytest.mark.asyncio
    async def test_low_scores_fail_with_code(self):
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="30")):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "failed"
        errors = result["errors"]
        low_score_errors = [e for e in errors if e["code"] == "low_relevance"]
        assert len(low_score_errors) == len(SAMPLE_DATA)

    @pytest.mark.asyncio
    async def test_mixed_scores_partial_failure(self):
        """Items below threshold are flagged; items above are not."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        # First item scores 40 (fail), others score 90 (pass)
        call_count = 0

        async def varying_score(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "40" if call_count == 1 else "90"

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=varying_score):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "failed"
        low_errors = [e for e in result["errors"] if e["code"] == "low_relevance"]
        assert len(low_errors) == 1
        assert low_errors[0]["index"] == 0

    @pytest.mark.asyncio
    async def test_empty_data_passes(self):
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator()
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="80")):
            result = await validator.validate([])

        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_no_user_assistant_pairs(self):
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator()
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="80")):
            result = await validator.validate(NO_PAIRS_DATA)

        assert result["status"] == "failed"
        errors = result["errors"]
        assert all(e["code"] == "no_valid_pairs" for e in errors)
        assert len(errors) == len(NO_PAIRS_DATA)

    @pytest.mark.asyncio
    async def test_llm_error_produces_eval_error_code(self):
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(
            validator,
            "call_llm",
            new=AsyncMock(side_effect=RuntimeError("LLM unavailable")),
        ):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "failed"
        errors = result["errors"]
        eval_errors = [e for e in errors if e["code"] == "eval_error"]
        assert len(eval_errors) == len(SAMPLE_DATA)

    @pytest.mark.asyncio
    async def test_score_distribution_chart_attached(self):
        """When there are failures and at least one score, a Vega histogram is appended."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        async def mixed(*_args, **_kwargs):
            mixed.n = getattr(mixed, "n", 0) + 1
            return "30" if mixed.n == 1 else "90"

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=mixed):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "failed"
        info = result.get("info", [])
        charts = [i for i in info if i["code"] == "score_distribution"]
        assert len(charts) == 1
        assert isinstance(charts[0]["chart"], dict)
        assert charts[0]["chart"]["$schema"].startswith("https://vega.github.io/schema/vega-lite")

    @pytest.mark.asyncio
    async def test_concurrent_calls_all_fired(self):
        """All user-assistant pairs trigger a call_llm coroutine."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        call_count = 0

        async def counting_llm(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0)
            return "80"

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=counting_llm):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "passed"
        assert call_count == len(SAMPLE_DATA)  # one call per item (each has 1 pair)

    @pytest.mark.asyncio
    async def test_multi_turn_dialog_averages_pair_scores(self):
        """Multi-turn items fire one call per user-assistant pair; avg is used for threshold."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        multi_turn = [{"messages": [
            {"role": "user", "content": "Turn 1 question"},
            {"role": "assistant", "content": "Turn 1 answer"},
            {"role": "user", "content": "Turn 2 question"},
            {"role": "assistant", "content": "Turn 2 answer"},
        ]}]

        call_count = 0

        async def pair_score(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "80"

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=pair_score):
            result = await validator.validate(multi_turn)

        assert call_count == 2  # two user-assistant pairs
        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_score_extraction_fallback_to_zero(self):
        """Unparseable LLM output counts as score 0 (below any reasonable threshold)."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator(options={"score_threshold": 1})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="not a number")):
            result = await validator.validate(SAMPLE_DATA[:1])

        assert result["status"] == "failed"
        low_errors = [e for e in result["errors"] if e["code"] == "low_relevance"]
        assert len(low_errors) == 1


# ── GEvalRubricValidator ──────────────────────────────────────────────────────

class TestGEvalRubricValidator:

    @pytest.mark.asyncio
    async def test_all_pass_above_threshold(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        validator = GEvalRubricValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="85")):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "passed"
        assert "errors" not in result

    @pytest.mark.asyncio
    async def test_low_composite_score_fails(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        validator = GEvalRubricValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="25")):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "failed"
        rubric_errors = [e for e in result["errors"] if e["code"] == "low_rubric_score"]
        assert len(rubric_errors) == len(SAMPLE_DATA)

    @pytest.mark.asyncio
    async def test_rubric_error_includes_breakdown(self):
        """Each low-rubric-score error message contains per-criterion breakdown."""
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        rubric = {
            "helpfulness": {"description": "Is it helpful?", "weight": 2.0},
            "accuracy": {"description": "Is it accurate?", "weight": 1.0},
        }
        validator = GEvalRubricValidator(options={"rubric": rubric, "score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="20")):
            result = await validator.validate(SAMPLE_DATA[:1])

        errors = [e for e in result["errors"] if e["code"] == "low_rubric_score"]
        assert errors
        assert "helpfulness" in errors[0]["error"]
        assert "accuracy" in errors[0]["error"]

    @pytest.mark.asyncio
    async def test_calls_fired_per_criterion_per_pair(self):
        """LLM is called once per (criterion × pair), not just once per item."""
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        rubric = {
            "helpfulness": "Is it helpful?",
            "clarity": "Is it clear?",
            "accuracy": "Is it accurate?",
        }
        call_count = 0

        async def counting_llm(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "80"

        # 3 items × 1 pair each × 3 criteria = 9 calls
        validator = GEvalRubricValidator(options={"rubric": rubric, "score_threshold": 70})
        with patch.object(validator, "call_llm", new=counting_llm):
            await validator.validate(SAMPLE_DATA)

        assert call_count == len(SAMPLE_DATA) * len(rubric)

    @pytest.mark.asyncio
    async def test_weighted_composite_score(self):
        """Composite score is the weighted average of per-criterion scores."""
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        rubric = {
            # weight 3:1 ratio — helpfulness dominates
            "helpfulness": {"description": "helpful?", "weight": 3.0},
            "clarity":     {"description": "clear?",   "weight": 1.0},
        }

        call_count = 0

        async def alternating(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            # helpfulness calls (1st criterion alphabetically...but dict order is preserved)
            # helpfulness scores 100, clarity scores 0
            # composite = 0.75*100 + 0.25*0 = 75 → above threshold 70
            return "100" if (call_count % 2) == 1 else "0"

        validator = GEvalRubricValidator(options={"rubric": rubric, "score_threshold": 70})
        with patch.object(validator, "call_llm", new=alternating):
            result = await validator.validate(SAMPLE_DATA[:1])

        # 75 composite ≥ 70 threshold → passed
        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_empty_data_passes(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        validator = GEvalRubricValidator()
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="80")):
            result = await validator.validate([])

        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_no_user_assistant_pairs(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        validator = GEvalRubricValidator()
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="80")):
            result = await validator.validate(NO_PAIRS_DATA)

        assert result["status"] == "failed"
        errors = result["errors"]
        assert all(e["code"] == "no_valid_pairs" for e in errors)

    @pytest.mark.asyncio
    async def test_llm_error_produces_eval_error(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        validator = GEvalRubricValidator(options={"score_threshold": 70})
        with patch.object(
            validator,
            "call_llm",
            new=AsyncMock(side_effect=RuntimeError("timeout")),
        ):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "failed"
        eval_errors = [e for e in result["errors"] if e["code"] == "eval_error"]
        assert len(eval_errors) == len(SAMPLE_DATA)

    @pytest.mark.asyncio
    async def test_score_distribution_chart_attached(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        call_count = 0

        async def mixed(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            # First item (3 criteria) scores 20, rest score 90
            return "20" if call_count <= 3 else "90"

        validator = GEvalRubricValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=mixed):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "failed"
        info = result.get("info", [])
        charts = [i for i in info if i["code"] == "score_distribution"]
        assert len(charts) == 1
        assert isinstance(charts[0]["chart"], dict)

    @pytest.mark.asyncio
    async def test_rubric_shorthand_format(self):
        """Rubric values can be plain strings (weight defaults to 1.0)."""
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        rubric = {
            "helpfulness": "How helpful is the response?",
            "tone":        "Is the tone appropriate?",
        }
        validator = GEvalRubricValidator(options={"rubric": rubric, "score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="85")):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "passed"


# ── DynamicGEvalValidator ─────────────────────────────────────────────────────

class TestDynamicGEvalValidator:

    @pytest.mark.asyncio
    async def test_custom_prompt_and_threshold_from_options(self):
        from validators.base_geval_validator import DynamicGEvalValidator

        validator = DynamicGEvalValidator(options={
            "prompt": "Rate this response from 1-100.\n{content}",
            "score_threshold": 60,
        })
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="75")):
            result = await validator.validate(SAMPLE_DATA)

        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_custom_score_code_from_options(self):
        from validators.base_geval_validator import DynamicGEvalValidator

        validator = DynamicGEvalValidator(options={
            "prompt": "Rate the following:\n{content}",
            "score_code": "my_custom_code",
            "score_threshold": 70,
        })
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="20")):
            result = await validator.validate(SAMPLE_DATA[:1])

        assert result["status"] == "failed"
        errors = [e for e in result["errors"] if e["code"] == "my_custom_code"]
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_custom_score_title_from_options(self):
        from validators.base_geval_validator import DynamicGEvalValidator

        validator = DynamicGEvalValidator(options={
            "prompt": "Rate:\n{content}",
            "score_title": "Fluency Score",
            "score_threshold": 70,
        })
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="20")):
            result = await validator.validate(SAMPLE_DATA[:1])

        assert result["status"] == "failed"
        errors = result["errors"]
        assert any("Fluency Score" in e.get("error", "") for e in errors)

    @pytest.mark.asyncio
    async def test_empty_data_passes(self):
        from validators.base_geval_validator import DynamicGEvalValidator

        validator = DynamicGEvalValidator(options={
            "prompt": "Rate:\n{content}",
        })
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="80")):
            result = await validator.validate([])

        assert result["status"] == "passed"


# ── Auto-detected trace evaluation: GEvalRelevanceValidator ──────────────────
# AGENT_TRACES contain "system" and "tool" roles → auto-detected as traces.
# No trace_mode option needed.

class TestGEvalRelevanceValidatorTraceMode:

    @pytest.mark.asyncio
    async def test_agent_trace_passes_above_threshold(self):
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="88")):
            result = await validator.validate(AGENT_TRACES)

        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_agent_trace_fails_below_threshold(self):
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="40")):
            result = await validator.validate(AGENT_TRACES)

        assert result["status"] == "failed"
        errors = [e for e in result["errors"] if e["code"] == "low_relevance"]
        assert len(errors) == len(AGENT_TRACES)

    @pytest.mark.asyncio
    async def test_one_call_per_trace_not_per_pair(self):
        """Trace items (auto-detected) fire one LLM call per item, not per turn."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        call_count = 0

        async def counting(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "80"

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=counting):
            await validator.validate(AGENT_TRACES)

        # 2 trace items → 2 holistic calls, regardless of how many turns each has
        assert call_count == len(AGENT_TRACES)

    @pytest.mark.asyncio
    async def test_trace_includes_tool_messages(self):
        """The formatted trace passed to call_llm contains all role types."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        received_prompts: list[str] = []

        async def capturing(prompt: str, *_args, **_kwargs):
            received_prompts.append(prompt)
            return "80"

        validator = GEvalRelevanceValidator()
        with patch.object(validator, "call_llm", new=capturing):
            await validator.validate(AGENT_TRACES[:1])

        assert received_prompts
        assert "[TOOL]:" in received_prompts[0]
        assert "[SYSTEM]:" in received_prompts[0]
        assert "[USER]:" in received_prompts[0]
        assert "[ASSISTANT]:" in received_prompts[0]

    @pytest.mark.asyncio
    async def test_empty_item_reports_no_valid_pairs(self):
        """An empty message list has no roles → classified as dialog → no_valid_pairs."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator()
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="80")):
            result = await validator.validate([{"messages": []}])

        assert result["status"] == "failed"
        assert any(e["code"] == "no_valid_pairs" for e in result["errors"])

    @pytest.mark.asyncio
    async def test_llm_error_in_trace(self):
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(
            validator, "call_llm", new=AsyncMock(side_effect=RuntimeError("model down"))
        ):
            result = await validator.validate(AGENT_TRACES)

        assert result["status"] == "failed"
        assert all(e["code"] == "eval_error" for e in result["errors"])

    @pytest.mark.asyncio
    async def test_score_distribution_chart(self):
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        call_count = 0

        async def mixed(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "30" if call_count == 1 else "90"

        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=mixed):
            result = await validator.validate(AGENT_TRACES)

        assert result["status"] == "failed"
        charts = [i for i in result.get("info", []) if i["code"] == "score_distribution"]
        assert len(charts) == 1

    @pytest.mark.asyncio
    async def test_explicit_item_type_overrides_autodetect(self):
        """item_type='trace' on a pure user/assistant item forces holistic evaluation."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        call_count = 0

        async def counting(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "80"

        # SAMPLE_DATA has only user/assistant → normally 1 call per pair.
        # Forcing item_type="trace" → 1 holistic call per item.
        forced_trace = [
            {**item, "item_type": "trace"} for item in SAMPLE_DATA[:2]
        ]
        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=counting):
            await validator.validate(forced_trace)

        assert call_count == 2  # holistic, not per-pair

    @pytest.mark.asyncio
    async def test_mixed_dataset_routes_each_item_correctly(self):
        """Dialog and trace items in the same dataset are each routed correctly."""
        from validators.gate7_automatic_quality_grading.geval_relevance_validator import (
            GEvalRelevanceValidator,
        )

        received_prompts: list[str] = []

        async def capturing(prompt: str, *_args, **_kwargs):
            received_prompts.append(prompt)
            return "80"

        # 2 dialogs (1 pair each) + 1 trace
        mixed = list(SAMPLE_DATA[:2]) + [AGENT_TRACES[0]]
        validator = GEvalRelevanceValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=capturing):
            result = await validator.validate(mixed)

        assert result["status"] == "passed"
        # 2 dialog pairs + 1 trace = 3 calls total
        assert len(received_prompts) == 3
        # The trace prompt contains [TOOL]: marker; dialog prompts do not
        trace_prompts = [p for p in received_prompts if "[TOOL]:" in p]
        dialog_prompts = [p for p in received_prompts if "[TOOL]:" not in p]
        assert len(trace_prompts) == 1
        assert len(dialog_prompts) == 2


# ── Auto-detected trace evaluation: GEvalRubricValidator ─────────────────────

class TestGEvalRubricValidatorTraceMode:

    @pytest.mark.asyncio
    async def test_agent_trace_passes_above_threshold(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        validator = GEvalRubricValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="85")):
            result = await validator.validate(AGENT_TRACES)

        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_agent_trace_fails_below_threshold(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        validator = GEvalRubricValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="20")):
            result = await validator.validate(AGENT_TRACES)

        assert result["status"] == "failed"
        errors = [e for e in result["errors"] if e["code"] == "low_rubric_score"]
        assert len(errors) == len(AGENT_TRACES)

    @pytest.mark.asyncio
    async def test_calls_per_item_equals_num_criteria(self):
        """Trace items fire one LLM call per (item × criterion), not per pair."""
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        rubric = {
            "goal_completion": "Did the agent complete the user goal?",
            "tool_use_quality": "Were tools called correctly?",
            "conciseness": "Was the response concise?",
        }
        call_count = 0

        async def counting(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "80"

        validator = GEvalRubricValidator(options={"rubric": rubric})
        with patch.object(validator, "call_llm", new=counting):
            await validator.validate(AGENT_TRACES)

        # 2 traces × 3 criteria = 6 calls
        assert call_count == len(AGENT_TRACES) * len(rubric)

    @pytest.mark.asyncio
    async def test_error_breakdown_contains_all_criteria(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        rubric = {
            "goal_completion":  {"description": "Completed the goal?", "weight": 2.0},
            "tool_use_quality": {"description": "Good tool use?",      "weight": 1.0},
        }
        validator = GEvalRubricValidator(options={"rubric": rubric, "score_threshold": 70})
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="15")):
            result = await validator.validate(AGENT_TRACES[:1])

        errors = [e for e in result["errors"] if e["code"] == "low_rubric_score"]
        assert errors
        assert "goal_completion" in errors[0]["error"]
        assert "tool_use_quality" in errors[0]["error"]

    @pytest.mark.asyncio
    async def test_weighted_composite_for_trace(self):
        """Weighted composite: heavy criterion dominates regardless of item type."""
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        rubric = {
            "goal_completion": {"description": "done?", "weight": 3.0},
            "conciseness":     {"description": "short?", "weight": 1.0},
        }
        call_count = 0

        async def alternating(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            # goal_completion (call 1) = 100, conciseness (call 2) = 0
            # composite = 0.75*100 + 0.25*0 = 75 → passes at threshold 70
            return "100" if call_count % 2 == 1 else "0"

        validator = GEvalRubricValidator(options={"rubric": rubric, "score_threshold": 70})
        with patch.object(validator, "call_llm", new=alternating):
            result = await validator.validate(AGENT_TRACES[:1])

        assert result["status"] == "passed"

    @pytest.mark.asyncio
    async def test_empty_item_reports_no_valid_pairs(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        validator = GEvalRubricValidator()
        with patch.object(validator, "call_llm", new=AsyncMock(return_value="80")):
            result = await validator.validate([{"messages": []}])

        assert result["status"] == "failed"
        assert any(e["code"] == "no_valid_pairs" for e in result["errors"])

    @pytest.mark.asyncio
    async def test_llm_error_in_trace(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        validator = GEvalRubricValidator(options={"score_threshold": 70})
        with patch.object(
            validator, "call_llm", new=AsyncMock(side_effect=RuntimeError("timeout"))
        ):
            result = await validator.validate(AGENT_TRACES)

        assert result["status"] == "failed"
        eval_errors = [e for e in result["errors"] if e["code"] == "eval_error"]
        assert len(eval_errors) == len(AGENT_TRACES)

    @pytest.mark.asyncio
    async def test_histogram_attached_on_failure(self):
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        call_count = 0

        async def mixed(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            # First trace (3 default criteria, calls 1-3): score 20; second (calls 4-6): score 90
            return "20" if call_count <= 3 else "90"

        validator = GEvalRubricValidator(options={"score_threshold": 70})
        with patch.object(validator, "call_llm", new=mixed):
            result = await validator.validate(AGENT_TRACES)

        assert result["status"] == "failed"
        charts = [i for i in result.get("info", []) if i["code"] == "score_distribution"]
        assert len(charts) == 1
        assert isinstance(charts[0]["chart"], dict)

    @pytest.mark.asyncio
    async def test_mixed_dataset_dialog_and_trace(self):
        """A dataset mixing dialog and trace items is handled correctly per item."""
        from validators.gate7_automatic_quality_grading.geval_rubric_validator import (
            GEvalRubricValidator,
        )

        rubric = {"quality": "Overall quality", "accuracy": "Factual accuracy"}
        call_count = 0

        async def counting(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            return "85"

        # 2 dialogs (1 pair each) + 1 trace → dialog: 2×2=4 calls; trace: 1×2=2 calls → 6 total
        mixed = list(SAMPLE_DATA[:2]) + [AGENT_TRACES[0]]
        validator = GEvalRubricValidator(options={"rubric": rubric, "score_threshold": 70})
        with patch.object(validator, "call_llm", new=counting):
            result = await validator.validate(mixed)

        assert result["status"] == "passed"
        assert call_count == 2 * len(rubric) + 1 * len(rubric)  # (2 dialog pairs + 1 trace) × 2 criteria
