"""Tests for the frozen RunConfig (FR-10 AC3-AC5, NFR-06).

The settings of one interview run must not change once the interview has started, so
that all answers of a run are judged under identical conditions.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="not implemented")
def test_run_config_is_immutable() -> None:
    """Assigning to a field of the frozen dataclass raises (FR-10 AC3)."""
    raise NotImplementedError


@pytest.mark.skip(reason="not implemented")
def test_run_config_is_frozen_at_interview_start() -> None:
    """Changing a widget after BRIEF -> INTERVIEW does not change the RunConfig (FR-10 AC3)."""
    raise NotImplementedError


@pytest.mark.skip(reason="not implemented")
def test_all_evaluations_of_one_run_share_the_same_run_config() -> None:
    """Every stored AnswerEvaluation carries the same RunConfig (FR-10 AC5)."""
    raise NotImplementedError
