"""Tests for the deterministic interview logic (NFR-06).

Covers the question-mix rule (FR-05), the interviewer message builder and its roles
(FR-07 AC1), the score aggregation (FR-09 AC1) and the state transitions (§3). All
LLM calls are mocked.
"""

from __future__ import annotations

import pytest

from job_interview_coaching_app import interview
from job_interview_coaching_app.interview import (
    Turn,
    aggregate_scores,
    build_interviewer_messages,
    expected_question_types,
)
from job_interview_coaching_app.schemas import (
    AnswerEvaluation,
    Gap,
    InterviewPlan,
    Question,
    StarRating,
)


def make_plan() -> InterviewPlan:
    """A small fictional plan with one gap question (FR-15 AC4)."""
    return InterviewPlan(
        role_summary="Senior Java backend developer for a content platform.",
        strengths=["12 years of Magnolia CMS", "Kafka integration"],
        gaps=[
            Gap(id="G1", description="No Kubernetes experience.", jd_requirement="Kubernetes", severity="high"),
            Gap(id="G2", description="Seven-month tenure.", jd_requirement="Stability", severity="medium"),
        ],
        questions=[
            Question(id="Q1", type="opener", text="Tell me about yourself."),
            Question(id="Q2", type="gap", gap_id="G1", text="How have you deployed services?"),
            Question(id="Q3", type="gap", gap_id="G2", text="Why did you leave after seven months?"),
        ],
    )


def make_evaluation(score: int) -> AnswerEvaluation:
    """An evaluation where only the score matters."""
    return AnswerEvaluation(
        reasoning="-",
        relevant=True,
        score=score,
        star=StarRating(),
        strengths=["none"],
        improvements=["Add a measurable result."],
        improved_answer="-",
    )


def test_question_mix_for_three_questions_has_no_reverse() -> None:
    """With n = 3 the mix is opener + gap + gap; ``reverse`` needs n >= 4 (FR-05)."""
    assert expected_question_types(3) == ["opener", "gap", "gap"]


@pytest.mark.parametrize("n", [4, 5, 8])
def test_question_mix_for_four_or_more_ends_with_reverse(n: int) -> None:
    """With n >= 4 the last question is the ``reverse`` question (FR-05, FR-05 AC2)."""
    types = expected_question_types(n)
    assert len(types) == n
    assert types[0] == "opener"
    assert types[-1] == "reverse"
    assert types[1:-1] == ["gap"] * (n - 2)


@pytest.mark.parametrize("n", [2, 9])
def test_question_mix_rejects_out_of_range_n(n: int) -> None:
    """n outside 3-8 is rejected (FR-03 AC1)."""
    with pytest.raises(ValueError):
        expected_question_types(n)


def test_interviewer_messages_have_expected_roles_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """system, then alternating assistant/user, ending with the latest answer (FR-07 AC1)."""
    monkeypatch.setattr(interview, "load_prompt", lambda _path: "INSTRUCTIONS")
    turns = [
        Turn("Q1", "Tell me about yourself.", "I build CMS platforms."),
        Turn("Q2", "How have you deployed services?", "With Docker.", "Which registry?", "GitLab."),
        Turn("Q3", "Why did you leave after seven months?", "The project ended."),
    ]
    messages = build_interviewer_messages(make_plan(), turns)
    roles = [message["role"] for message in messages]
    assert roles == ["system"] + ["assistant", "user"] * 4
    assert messages[3]["content"] == "How have you deployed services?"
    assert messages[5]["content"] == "Which registry?"
    assert messages[-1]["content"] == "<answer>\nThe project ended.\n</answer>"


def test_interviewer_system_message_contains_role_summary_and_gaps(monkeypatch: pytest.MonkeyPatch) -> None:
    """The system message carries role summary and gaps from the plan (FR-07 AC1)."""
    monkeypatch.setattr(interview, "load_prompt", lambda _path: "INSTRUCTIONS")
    plan = make_plan()
    system = build_interviewer_messages(plan, [Turn("Q1", "Tell me about yourself.", "Hi.")])[0]
    assert system["content"].startswith("INSTRUCTIONS")
    assert plan.role_summary in system["content"]
    assert all(gap.description in system["content"] for gap in plan.gaps)


def test_aggregate_scores_returns_arithmetic_mean() -> None:
    """The overall score is the mean of the per-question scores (FR-09 AC1)."""
    evaluations = [make_evaluation(score) for score in (2, 3, 5)]
    assert aggregate_scores(evaluations) == pytest.approx(10 / 3)


def test_aggregate_scores_uses_answered_questions_only() -> None:
    """An interview finished early scores only the answered questions (FR-06 AC4)."""
    assert aggregate_scores([make_evaluation(4), make_evaluation(2)]) == 3.0
    with pytest.raises(ValueError):
        aggregate_scores([])
