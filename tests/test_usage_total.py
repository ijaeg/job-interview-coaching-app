"""Tests for the session token and cost total (FR-13 AC1, AC3, NFR-06).

Prices are replaced by fixed values, so the tests never touch the network.
"""

from __future__ import annotations

import pytest
import streamlit as st

from job_interview_coaching_app import llm_client
from job_interview_coaching_app.pricing import ModelPricing
from job_interview_coaching_app.schemas import RunConfig, Usage

RUN_CONFIG = RunConfig(
    model="openai/gpt-5-mini",
    reasoning_effort="low",
    max_tokens=4000,
    temperature=None,
    top_p=None,
    eval_variant="p1_zero_shot",
)


@pytest.fixture(autouse=True)
def empty_session_state():
    """Every test starts and ends with an empty session state."""
    st.session_state.clear()
    yield
    st.session_state.clear()


def test_record_usage_adds_tokens_and_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each call adds its tokens and its cost to the session total (FR-13 AC1)."""
    monkeypatch.setattr(llm_client, "get_pricing", lambda _model: ModelPricing(0.000001, 0.000002))
    llm_client.record_usage(Usage(prompt_tokens=1000, completion_tokens=500, reasoning_tokens=300), RUN_CONFIG)
    llm_client.record_usage(Usage(prompt_tokens=1000, completion_tokens=500, reasoning_tokens=300), RUN_CONFIG)
    total = st.session_state[llm_client.USAGE_TOTAL_KEY]
    assert total["prompt_tokens"] == 2000
    assert total["completion_tokens"] == 1000
    assert total["cost_usd"] == pytest.approx(0.004)


def test_record_usage_without_prices_marks_cost_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without prices the tokens still add up, but the cost is unknown (FR-13 AC3)."""
    monkeypatch.setattr(llm_client, "get_pricing", lambda _model: None)
    llm_client.record_usage(Usage(prompt_tokens=1000, completion_tokens=500, reasoning_tokens=0), RUN_CONFIG)
    total = st.session_state[llm_client.USAGE_TOTAL_KEY]
    assert total["prompt_tokens"] == 1000
    assert total["cost_usd"] is None
