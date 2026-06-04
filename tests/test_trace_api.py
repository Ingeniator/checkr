"""
API tests demonstrating how to call checkr with agent traces.

These tests show the exact JSON payload an Airflow DAG (or any HTTP client)
would POST to evaluate agent execution traces with a custom LLM-as-a-judge rubric.

Endpoints covered:
  POST /api/v0/rubric-eval          — custom rubric, direct (sync) call
  POST /api/v0/g-eval               — single-score relevance, direct (sync) call
  POST /api/v0/validate             — gate-based routing (registered validators)

Airflow DAG pattern (async job queue):
  POST /api/v0/jobs/validate/GEvalRubricValidator  → {job_id}
  GET  /api/v0/jobs/{job_id}                       → poll until completed

LLM calls are mocked so tests run without a real model endpoint.
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.app import lifespan
from core.config import settings
from api.validators import router as validator_router
from api.jobs import router as jobs_router
from validators.base_geval_validator import BaseGEvalValidator


@pytest.fixture(scope="module")
def full_client():
    """TestClient with both validator and jobs routers — mirrors the production app."""
    app = FastAPI(lifespan=lifespan, root_path=settings.root_path)
    app.include_router(validator_router, prefix="/api/v0")
    app.include_router(jobs_router, prefix="/api/v0/jobs")
    with TestClient(app) as c:
        yield c

# ── shared mock config (suppresses real OpenAI client init) ───────────────────

_LLM_CONFIG = {"geval": {"model": "mock", "api_key": "x", "api_base": "http://mock", "temperature": 0.0}}

@contextmanager
def _mock_llm(score: str = "85", *, call_llm_fn=None):
    """Suppress LLM init and stub call_llm.

    Pass score for a fixed return value, or call_llm_fn for a custom async callable.
    """
    llm_mock = call_llm_fn if call_llm_fn is not None else AsyncMock(return_value=score)
    with ExitStack() as stack:
        stack.enter_context(patch("validators.base_geval_validator.load_and_expand_yaml", return_value=_LLM_CONFIG))
        stack.enter_context(patch("validators.base_geval_validator.AsyncOpenAI"))
        stack.enter_context(patch("validators.base_geval_validator.httpx.AsyncClient"))
        stack.enter_context(patch("validators.base_geval_validator.httpx.AsyncHTTPTransport"))
        stack.enter_context(patch.object(BaseGEvalValidator, "call_llm", new=llm_mock))
        yield


# ── sample agent traces (what Airflow would send) ─────────────────────────────

# A realistic two-turn booking agent trace with system + tool messages.
BOOKING_TRACE = {
    "messages": [
        {"role": "system",    "content": "You are a travel booking agent."},
        {"role": "user",      "content": "Book me a flight to Paris next Friday."},
        {"role": "assistant", "content": "I'll search for available flights to Paris."},
        {"role": "tool",      "content": '{"flights": [{"id": "BA123", "price": 450, "dep": "08:00"}]}'},
        {"role": "assistant", "content": "Found flight BA123 departing at 08:00 for €450. Shall I book it?"},
        {"role": "user",      "content": "Yes, please book it."},
        {"role": "assistant", "content": "Done! Your booking is confirmed. Reference: CONF-2024-42."},
    ]
}

# A second trace — data analysis agent.
ANALYSIS_TRACE = {
    "messages": [
        {"role": "system",    "content": "You are a data analyst agent."},
        {"role": "user",      "content": "Summarise last quarter's sales figures."},
        {"role": "assistant", "content": "Fetching the sales data now."},
        {"role": "tool",      "content": '{"total_revenue": 120000, "units_sold": 340, "top_product": "Pro Plan"}'},
        {"role": "assistant", "content": "Last quarter: €120k revenue, 340 units. Top product: Pro Plan."},
    ]
}

# A standard dialog item (no system/tool roles) — auto-detected as "dialog".
DIALOG_ITEM = {
    "messages": [
        {"role": "user",      "content": "What is the capital of France?"},
        {"role": "assistant", "content": "The capital of France is Paris."},
    ]
}

# Agent rubric a team would define for evaluating booking-agent traces.
AGENT_RUBRIC = {
    "goal_completion": {
        "description": "Did the agent fully complete the user's requested task?",
        "weight": 3.0,
    },
    "tool_use_quality": {
        "description": "Were tools called with correct parameters and results used appropriately?",
        "weight": 2.0,
    },
    "communication": {
        "description": "Was the agent's language clear, concise, and professional?",
        "weight": 1.0,
    },
}


# ── /rubric-eval ──────────────────────────────────────────────────────────────

class TestRubricEvalWithTraces:
    """
    Demonstrates the primary Airflow → checkr call pattern:

        POST /api/v0/rubric-eval
        {
            "dataset": [<trace>, ...],
            "options": {
                "rubric": { <criterion>: {"description": "...", "weight": N} },
                "score_threshold": 75,
                "max_concurrency": 20
            }
        }
    """

    def test_agent_traces_pass_above_threshold(self, client):
        payload = {
            "dataset": [BOOKING_TRACE, ANALYSIS_TRACE],
            "options": {
                "rubric": AGENT_RUBRIC,
                "score_threshold": 75,
            },
        }
        with _mock_llm("88"):
            response = client.post("/api/v0/rubric-eval", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "passed"
        assert body.get("errors", []) == []

    def test_agent_traces_fail_below_threshold(self, client):
        payload = {
            "dataset": [BOOKING_TRACE, ANALYSIS_TRACE],
            "options": {
                "rubric": AGENT_RUBRIC,
                "score_threshold": 75,
            },
        }
        with _mock_llm("30"):
            response = client.post("/api/v0/rubric-eval", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        errors = body["errors"]
        assert len(errors) == 2
        assert all(e["code"] == "low_rubric_score" for e in errors)
        # Error message contains per-criterion breakdown
        assert "goal_completion" in errors[0]["error"]
        assert "tool_use_quality" in errors[0]["error"]

    def test_tool_role_accepted_by_schema(self, client):
        """API must not reject traces containing 'tool' role messages."""
        payload = {
            "dataset": [BOOKING_TRACE],
            "options": {"rubric": AGENT_RUBRIC, "score_threshold": 70},
        }
        with _mock_llm("85"):
            response = client.post("/api/v0/rubric-eval", json=payload)

        # Would be 422 if 'tool' is not in the allowed role Literal
        assert response.status_code == 200

    def test_explicit_item_type_field_accepted(self, client):
        """item_type='trace' is accepted by the schema and preserved through the API."""
        payload = {
            "dataset": [{**DIALOG_ITEM, "item_type": "trace"}],
            "options": {"rubric": AGENT_RUBRIC, "score_threshold": 70},
        }
        with _mock_llm("80"):
            response = client.post("/api/v0/rubric-eval", json=payload)

        # Would be 422 if item_type is not a known DataItem field
        assert response.status_code == 200

    def test_mixed_dataset_dialog_and_traces(self, client):
        """A dataset mixing dialog items and trace items is accepted and scored."""
        payload = {
            "dataset": [DIALOG_ITEM, BOOKING_TRACE, ANALYSIS_TRACE],
            "options": {
                "rubric": AGENT_RUBRIC,
                "score_threshold": 70,
            },
        }
        with _mock_llm("85"):
            response = client.post("/api/v0/rubric-eval", json=payload)

        assert response.status_code == 200
        assert response.json()["status"] == "passed"

    def test_score_distribution_chart_in_info(self, client):
        """When some items fail, a Vega-Lite histogram is included in the 'info' field."""
        call_count = 0

        async def mixed(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            # First trace scores low (calls 1-3 = 3 criteria), second scores high
            return "20" if call_count <= len(AGENT_RUBRIC) else "90"

        payload = {
            "dataset": [BOOKING_TRACE, ANALYSIS_TRACE],
            "options": {"rubric": AGENT_RUBRIC, "score_threshold": 70},
        }
        with _mock_llm(call_llm_fn=mixed):
            response = client.post("/api/v0/rubric-eval", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        charts = [i for i in body.get("info", []) if i["code"] == "score_distribution"]
        assert len(charts) == 1
        assert isinstance(charts[0]["chart"], dict)


# ── /g-eval ───────────────────────────────────────────────────────────────────

class TestGEvalWithTraces:
    """
    Single-score holistic relevance evaluation over agent traces.

        POST /api/v0/g-eval
        {
            "dataset": [<trace>, ...],
            "options": {
                "prompt": "Evaluate if the agent completed the goal.\n{content}",
                "score_threshold": 70
            }
        }
    """

    def test_agent_trace_scored_holistically(self, client):
        payload = {
            "dataset": [BOOKING_TRACE],
            "options": {
                "prompt": (
                    "You are an evaluator.\n\n"
                    "Did the agent successfully complete the user's goal?\n"
                    "Score 1 (failed) to 100 (fully achieved).\n\n"
                    "{content}\n\n"
                    "Only respond with a number from 1 to 100."
                ),
                "score_threshold": 70,
            },
        }
        with _mock_llm("92"):
            response = client.post("/api/v0/g-eval", json=payload)

        assert response.status_code == 200
        assert response.json()["status"] == "passed"

    def test_tool_role_accepted_in_g_eval(self, client):
        payload = {
            "dataset": [BOOKING_TRACE, ANALYSIS_TRACE],
            "options": {"prompt": "Rate this:\n{content}", "score_threshold": 70},
        }
        with _mock_llm("80"):
            response = client.post("/api/v0/g-eval", json=payload)

        assert response.status_code == 200


# ── async job queue (Airflow sensor pattern) ──────────────────────────────────

_RUBRIC_GATE = "backend/gate7_automatic_quality_grading/geval_rubric_validator.py"


class TestJobQueueWithTraces:
    """
    Demonstrates two Airflow → checkr call patterns for agent traces.

    Pattern A — direct call (recommended for rubric eval):
        POST /api/v0/rubric-eval          → result inline (no job_id)

    Pattern B — async job queue (for long-running batch validations):
        POST /api/v0/jobs/validate/<gate> → {"job_id": "..."}   (Redis required)
        GET  /api/v0/jobs/<job_id>        → poll until "completed"

        Airflow DAG equivalent:
            submit = HttpOperator(
                endpoint="/api/v0/jobs/validate/" + RUBRIC_GATE,
                method="POST",
                data=json.dumps({"dataset": traces, "options": {"rubric": rubric}}),
                response_filter=lambda r: r.json()["job_id"],
            )
            wait = HttpSensor(
                endpoint="/api/v0/jobs/{{ ti.xcom_pull('submit') }}",
                response_check=lambda r: r.json()["status"] in ("completed", "failed"),
                poke_interval=30,
            )

        Without Redis, the jobs endpoint runs inline and returns the result directly
        (no job_id), making it safe to test without a running Redis instance.
    """

    def test_sync_fallback_returns_result_inline(self, full_client):
        """Without Redis the jobs endpoint runs synchronously and returns the result directly."""
        payload = {
            "dataset": [BOOKING_TRACE, ANALYSIS_TRACE],
            "options": {
                "rubric": AGENT_RUBRIC,
                "score_threshold": 70,
            },
        }
        with _mock_llm("85"):
            response = full_client.post(
                f"/api/v0/jobs/validate/{_RUBRIC_GATE}",
                json=payload,
            )

        assert response.status_code == 200
        body = response.json()
        # Sync fallback: result returned directly, no job_id in response
        assert "job_id" not in body
        assert body["status"] == "ok"
