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
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError
