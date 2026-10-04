"""Tests for the cost calculation (FR-13, NFR-06).

No network access: the model catalogue is replaced by a fixed dictionary.
"""

from __future__ import annotations

import pytest

from job_interview_coaching_app import pricing
from job_interview_coaching_app.pricing import (
    ModelPricing,
    compute_cost,
    get_pricing,
    get_supported_parameters,
)
from job_interview_coaching_app.schemas import Usage

CATALOGUE = {
    "openai/gpt-5-mini": {"pricing": {"prompt": "0.00000025", "completion": "0.000002"}},
    "openai/gpt-5-nano": {"pricing": {}},
}


def test_compute_cost_adds_prompt_and_completion_tokens() -> None:
    """Cost = prompt tokens x prompt price + completion tokens x completion price (FR-13 AC1)."""
    usage = Usage(prompt_tokens=1000, completion_tokens=500, reasoning_tokens=300)
    prices = ModelPricing(prompt_usd_per_token=0.000001, completion_usd_per_token=0.000002)
    assert compute_cost(usage, prices) == pytest.approx(0.002)


def test_compute_cost_without_pricing_is_none() -> None:
    """Without prices the cost is unknown, not zero (FR-13 AC3)."""
    usage = Usage(prompt_tokens=1000, completion_tokens=500, reasoning_tokens=0)
    assert compute_cost(usage, None) is None


def test_get_pricing_reads_the_catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prices are parsed from the catalogue; missing models or prices give None (FR-13 AC3)."""
    monkeypatch.setattr(pricing, "fetch_models", lambda: CATALOGUE)
    assert get_pricing("openai/gpt-5-mini") == ModelPricing(0.00000025, 0.000002)
    assert get_pricing("openai/gpt-5-nano") is None
    assert get_pricing("openai/gpt-5") is None


def test_get_supported_parameters_reads_the_catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sampling controls follow the catalogue; unknown models support nothing (FR-11 AC3)."""
    catalogue = {"openai/gpt-5-mini": {"supported_parameters": ["max_tokens", "reasoning", "seed"]}}
    monkeypatch.setattr(pricing, "fetch_models", lambda: catalogue)
    assert get_supported_parameters("openai/gpt-5-mini") == frozenset({"max_tokens", "reasoning", "seed"})
    assert get_supported_parameters("openai/gpt-5") == frozenset()
