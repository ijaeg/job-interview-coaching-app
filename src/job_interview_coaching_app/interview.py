"""Interview flow: state machine states, question mix, message builder, scoring.

Everything about *running* an interview that is not UI and not a prompt:

* the ``State`` enum backing the ``SETUP -> BRIEF -> INTERVIEW -> REPORT``
  machine kept in ``st.session_state`` (§3),
* the deterministic question-mix rule of FR-05,
* the multi-turn message builder for the interviewer call, the only call with a
  conversation history (FR-07 AC1, §5.1),
* the pure-Python score aggregation of the report (FR-09 AC1).

The deterministic parts (question mix, message roles, aggregation) are exactly what
the unit tests cover with mocked LLM calls (NFR-06).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import streamlit as st

from job_interview_coaching_app.guards import wrap_untrusted
from job_interview_coaching_app.llm_client import (
    LLMError,
    call_structured,
    load_prompt,
    stream_text,
)
from job_interview_coaching_app.schemas import (
    AnswerEvaluation,
    InterviewPlan,
    QuestionType,
    RunConfig,
)


class State(str, Enum):
    """The four states of the app's state machine (§3).

    "Start over" returns to ``SETUP`` and clears all data.
    """

    SETUP = "SETUP"
    BRIEF = "BRIEF"
    INTERVIEW = "INTERVIEW"
    REPORT = "REPORT"


#: Allowed range of main questions (FR-03 AC1).
MIN_QUESTIONS: int = 3
MAX_QUESTIONS: int = 8
DEFAULT_QUESTIONS: int = 3


@dataclass(frozen=True)
class Turn:
    """One answered main question, including its optional follow-up exchange.

    Attributes:
        question_id: Id of the main question from the ``InterviewPlan``.
        question_text: The main question as asked.
        answer: The candidate's answer to the main question.
        followup: The interviewer's follow-up question, if one was asked (FR-07 AC4).
        followup_answer: The candidate's answer to the follow-up, if any.
    """

    question_id: str
    question_text: str
    answer: str
    followup: str | None = None
    followup_answer: str | None = None


@dataclass(frozen=True)
class TurnResult:
    """One answered main question with its hidden evaluation (FR-08 AC1, FR-10 AC5).

    Attributes:
        turn: The question and the candidate's answers.
        evaluation: The judge's verdict, or ``None`` if the evaluation call failed.
        run_config: The frozen settings the evaluation was produced with.
    """

    turn: Turn
    evaluation: AnswerEvaluation | None
    run_config: RunConfig


def expected_question_types(n: int) -> list[QuestionType]:
    """Return the question types the plan must have, in asking order.

    Implements the FR-05 mix: position 1 is the ``opener``, the last position is
    ``reverse`` only when ``n >= 4``, and everything in between is a ``gap``
    question ordered by descending gap severity.

    Args:
        n: Number of main questions, between ``MIN_QUESTIONS`` and ``MAX_QUESTIONS``.

    Returns:
        A list of ``n`` question types used to validate the LLM plan (FR-05 AC2).

    Raises:
        ValueError: If ``n`` is outside the allowed range.
    """
    if not MIN_QUESTIONS <= n <= MAX_QUESTIONS:
        raise ValueError(f"n must be between {MIN_QUESTIONS} and {MAX_QUESTIONS}, got {n}")
    if n < 4:
        return ["opener"] + ["gap"] * (n - 1)
    return ["opener"] + ["gap"] * (n - 2) + ["reverse"]


def plan_interview(jd: str, cv: str, n: int, run_config: RunConfig) -> InterviewPlan:
    """Run the single analysis call that produces gaps and main questions.

    Uses ``prompts/analysis.md`` with the untrusted JD and CV wrapped in delimiters
    (FR-14 L4) and validates the response against ``InterviewPlan``; invalid JSON is
    retried once (FR-05 AC1). The returned plan is checked against
    ``expected_question_types`` and for duplicate question texts (FR-05 AC2, AC4).

    Args:
        jd: The job description as pasted by the user.
        cv: The CV as pasted by the user.
        n: Number of main questions to plan.
        run_config: Frozen settings of the current run (FR-10 AC3).

    Returns:
        The validated interview plan shown as the preparation brief (FR-04).

    Raises:
        LLMError: On API failure or a plan that does not satisfy FR-05.
    """
    user_content = "\n\n".join(
        [
            wrap_untrusted(jd, "job_description"),
            wrap_untrusted(cv, "cv"),
            f"Number of questions: {n}",
        ]
    )
    messages = [
        {"role": "system", "content": load_prompt("analysis.md")},
        {"role": "user", "content": user_content},
    ]
    plan, _usage = call_structured(messages, InterviewPlan, run_config)
    _validate_plan(plan, n)
    return plan


def _validate_plan(plan: InterviewPlan, n: int) -> None:
    """Check the FR-05 rules the JSON schema alone cannot enforce (FR-05 AC2-AC4).

    Raises:
        LLMError: If the plan breaks the question mix, references an unknown gap
            or repeats a question.
    """
    types = [q.type for q in plan.questions]
    if types != expected_question_types(n):
        raise LLMError("The generated interview plan has the wrong question mix. Please try again.")
    gap_ids = {g.id for g in plan.gaps}
    if any(q.type == "gap" and q.gap_id not in gap_ids for q in plan.questions):
        raise LLMError("The generated interview plan references an unknown gap. Please try again.")
    texts = [q.text.strip() for q in plan.questions]
    if len(texts) != len(set(texts)):
        raise LLMError("The generated interview plan contains duplicate questions. Please try again.")


def build_interviewer_messages(plan: InterviewPlan, turns: list[Turn]) -> list[dict[str, str]]:
    """Build the multi-turn message list for the interviewer follow-up call.

    Produces exactly the role order of FR-07: one ``system`` message with the
    interviewer instructions plus role summary and gaps, then the conversation as
    alternating ``assistant`` (questions the interviewer asked) and ``user``
    (answers the candidate gave), ending with the latest answer.

    This is the function FR-07 AC1 requires a unit test for (NFR-06).

    Args:
        plan: The interview plan, for role summary and gaps in the system message.
        turns: The conversation so far, oldest first; the last entry carries the
            answer the follow-up must react to.

    Returns:
        Messages ready for ``llm_client.stream_text``.
    """
    gap_lines = "\n".join(f"- {gap.id} ({gap.severity}): {gap.description}" for gap in plan.gaps)
    system_content = (
        f"{load_prompt('interviewer.md')}\n\n"
        f"Role summary: {plan.role_summary}\n\n"
        f"Gaps:\n{gap_lines}"
    )
    messages = [{"role": "system", "content": system_content}]
    for turn in turns:
        messages.append({"role": "assistant", "content": turn.question_text})
        messages.append({"role": "user", "content": wrap_untrusted(turn.answer, "answer")})
        if turn.followup is not None and turn.followup_answer is not None:
            messages.append({"role": "assistant", "content": turn.followup})
            messages.append(
                {"role": "user", "content": wrap_untrusted(turn.followup_answer, "answer")}
            )
    return messages


def generate_followup(messages: list[dict[str, str]], run_config: RunConfig) -> str:
    """Stream one follow-up question into the chat and return its full text.

    Free-text output, streamed with ``st.write_stream`` (FR-07 AC2, AC3). Fires only
    after ``gap`` questions; ``opener`` and ``reverse`` get no follow-up (FR-07 AC4).

    Args:
        messages: The history from ``build_interviewer_messages``.
        run_config: Frozen settings of the current run.

    Returns:
        The complete follow-up question, to be appended to the conversation.

    Raises:
        LLMError: On API failure or timeout (NFR-02).
    """
    followup = st.write_stream(stream_text(messages, run_config))
    return str(followup).strip()


def aggregate_scores(evaluations: list[AnswerEvaluation]) -> float:
    """Compute the overall interview score.

    Pure Python, no LLM call: the arithmetic mean of the per-question scores,
    displayed with one decimal (FR-09 AC1). Only answered main questions are
    included, which is what makes an early finish work (FR-06 AC4).

    Args:
        evaluations: One evaluation per answered main question.

    Returns:
        The mean score.

    Raises:
        ValueError: If ``evaluations`` is empty.
    """
    if not evaluations:
        raise ValueError("At least one evaluation is needed to compute an overall score.")
    return sum(evaluation.score for evaluation in evaluations) / len(evaluations)
