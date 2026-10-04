"""Tests for the frozen RunConfig (FR-10 AC3, FR-11 AC3, NFR-06).

The settings of one interview run must not change once the interview has started, so
that all answers of a run are judged under identical conditions.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from job_interview_coaching_app.interview import snapshot_run_config

SETTINGS = {
    "model": "openai/gpt-5-mini",
    "reasoning_effort": "low",
    "max_tokens": 4000,
    "temperature": 0.7,
    "top_p": 0.9,
    "eval_variant": "p1_zero_shot",
}


def test_run_config_is_immutable() -> None:
    """Assigning to a field of the frozen dataclass raises (FR-10 AC3)."""
    run_config = snapshot_run_config(SETTINGS, frozenset())
    with pytest.raises(FrozenInstanceError):
        run_config.model = "openai/gpt-5"


def test_run_config_is_frozen_at_interview_start() -> None:
    """Changing a widget after the snapshot does not change the RunConfig (FR-10 AC3)."""
    settings = dict(SETTINGS)
    run_config = snapshot_run_config(settings, frozenset())
    settings["model"] = "openai/gpt-5"
    settings["eval_variant"] = "p3_chain_of_thought"
    assert run_config.model == "openai/gpt-5-mini"
    assert run_config.eval_variant == "p1_zero_shot"


def test_unsupported_sampling_parameters_are_not_sent() -> None:
    """Only parameters the model lists in supported_parameters are kept (FR-11 AC3)."""
    run_config = snapshot_run_config(SETTINGS, frozenset({"temperature"}))
    assert run_config.temperature == 0.7
    assert run_config.top_p is None


@pytest.mark.skip(reason="not implemented")
def test_all_evaluations_of_one_run_share_the_same_run_config() -> None:
    """Every stored AnswerEvaluation carries the same RunConfig (FR-10 AC5)."""
    raise NotImplementedError
