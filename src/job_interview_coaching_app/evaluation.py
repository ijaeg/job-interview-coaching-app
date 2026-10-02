"""The five answer-evaluation prompt variants P1-P5 (FR-08, FR-12, §5.2).

The prompt comparison required by the brief happens here and nowhere else: only the
answer evaluation can be measured objectively against reference answers with known
human scores (§7). All other calls use one fixed prompt.

Three variants are a single call (P1 zero-shot, P2 few-shot, P3 chain-of-thought);
two are genuinely two calls (P4 generated knowledge, P5 self-refinement), and both
calls are counted for cost and latency (§5.2 AC3).

Related: FR-08, FR-12, §5.2, §7.
"""

from __future__ import annotations

from enum import Enum

from job_interview_coaching_app.guards import wrap_untrusted
from job_interview_coaching_app.llm_client import LLMError, call_structured, load_prompt
from job_interview_coaching_app.schemas import (
    AnswerEvaluation,
    Gap,
    Question,
    ReferenceKnowledge,
    RunConfig,
    Usage,
)


class EvalVariant(str, Enum):
    """The five evaluation prompt variants, selectable in the sidebar (FR-12 AC1).

    The value of each member is the file name below ``prompts/evaluation/``, so the
    variant maps directly onto its prompt file (§5.2 AC1).
    """

    P1_ZERO_SHOT = "p1_zero_shot"
    P2_FEW_SHOT = "p2_few_shot"
    P3_CHAIN_OF_THOUGHT = "p3_chain_of_thought"
    P4_GENERATED_KNOWLEDGE = "p4_generated_knowledge"
    P5_SELF_REFINEMENT = "p5_self_refinement"


#: Variants that need two separate API calls (§5.2 AC3).
TWO_STEP_VARIANTS: frozenset[EvalVariant] = frozenset(
    {EvalVariant.P4_GENERATED_KNOWLEDGE, EvalVariant.P5_SELF_REFINEMENT}
)

#: Default variant; replaced by the winner of the evaluation run (§7.2, FR-12 AC1).
DEFAULT_VARIANT: EvalVariant = EvalVariant.P1_ZERO_SHOT


def evaluate_answer(
    question: Question,
    answer: str,
    followup: str | None,
    followup_answer: str | None,
    run_config: RunConfig,
    gap: Gap | None = None,
) -> tuple[AnswerEvaluation, list[Usage]]:
    """Evaluate one main question with the variant selected in ``run_config``.

    Dispatches to the one-step path for P1-P3 and to the two-step path for P4/P5.
    The result stays hidden until the report (FR-08). The untrusted answer text is
    wrapped in delimiters before it reaches the prompt (FR-14 L4), and the parsed
    score is range-checked.

    Args:
        question: The main question that was asked.
        answer: The candidate's answer to it.
        followup: The follow-up question, for ``gap`` questions only.
        followup_answer: The answer to the follow-up, if one was asked.
        run_config: Frozen settings, including the variant to use (FR-10 AC3).
        gap: The gap this question targets, passed as evaluation context.

    Returns:
        The validated evaluation (FR-08 AC2, AC3, AC4) and the usage of every API
        call it took - one for P1-P3, two for P4/P5 (§5.2 AC3, FR-13 AC1).

    Raises:
        LLMError: On API failure or invalid JSON after the retry (NFR-02).
    """
    variant = EvalVariant(run_config.eval_variant)
    user_content = build_evaluation_user_message(question, answer, followup, followup_answer, gap)
    if variant in TWO_STEP_VARIANTS:
        evaluation, usages = evaluate_two_step(variant, question, gap, user_content, run_config)
    else:
        evaluation, usages = evaluate_one_step(variant, user_content, run_config)
    if not 1 <= evaluation.score <= 5:
        raise LLMError(f"The evaluation returned an invalid score ({evaluation.score}).")
    return evaluation, usages


def evaluate_one_step(
    variant: EvalVariant,
    user_content: str,
    run_config: RunConfig,
) -> tuple[AnswerEvaluation, list[Usage]]:
    """Evaluate with a single call: P1 zero-shot, P2 few-shot or P3 chain-of-thought.

    P2's few-shot examples live in its prompt file and must not come from the
    evaluation dataset, so the comparison stays free of leakage (§5.2 AC2).

    Args:
        variant: One of P1, P2, P3.
        user_content: The rendered user message with question and answers.
        run_config: Frozen settings of the current run.

    Returns:
        The validated evaluation and the usage of the single call.

    Raises:
        LLMError: On API failure or invalid JSON after the retry.
    """
    messages = [
        {"role": "system", "content": load_prompt(f"evaluation/{variant.value}.md")},
        {"role": "user", "content": user_content},
    ]
    evaluation, usage = call_structured(messages, AnswerEvaluation, run_config)
    return evaluation, [usage]


def evaluate_two_step(
    variant: EvalVariant,
    question: Question,
    gap: Gap | None,
    user_content: str,
    run_config: RunConfig,
) -> tuple[AnswerEvaluation, list[Usage]]:
    """Evaluate with two calls: P4 generated knowledge or P5 self-refinement.

    The first call's system prompt is ``prompts/evaluation/<variant>_step1.md`` for P4
    and the unchanged P1 prompt for P5; the second call uses ``<variant>.md``.

    Args:
        variant: Either P4 or P5.
        question: The main question, for P4's reference request.
        gap: The targeted gap, for P4's reference request.
        user_content: The rendered user message with question and answers.
        run_config: Frozen settings of the current run.

    Returns:
        The validated evaluation from the second call and the usage of both calls.

    Raises:
        LLMError: On API failure or invalid JSON after the retry.
    """
    if variant is EvalVariant.P4_GENERATED_KNOWLEDGE:
        first_messages = [
            {"role": "system", "content": load_prompt(f"evaluation/{variant.value}_step1.md")},
            {"role": "user", "content": build_reference_request(question, gap)},
        ]
        knowledge, first_usage = call_structured(first_messages, ReferenceKnowledge, run_config)
        addition = wrap_untrusted(knowledge.model_dump_json(indent=2), "reference")
    else:
        first_messages = [
            {"role": "system", "content": load_prompt(f"evaluation/{EvalVariant.P1_ZERO_SHOT.value}.md")},
            {"role": "user", "content": user_content},
        ]
        draft, first_usage = call_structured(first_messages, AnswerEvaluation, run_config)
        addition = wrap_untrusted(draft.model_dump_json(indent=2), "draft_evaluation")
    second_messages = [
        {"role": "system", "content": load_prompt(f"evaluation/{variant.value}.md")},
        {"role": "user", "content": f"{user_content}\n\n{addition}"},
    ]
    evaluation, second_usage = call_structured(second_messages, AnswerEvaluation, run_config)
    return evaluation, [first_usage, second_usage]


def build_reference_request(question: Question, gap: Gap | None) -> str:
    """Render the user message for call 1 of variant P4.

    Contains the question and the targeted gap but deliberately **not** the
    candidate's answer, so the generated reference cannot be anchored on it (§5.2).

    Args:
        question: The main question that was asked.
        gap: The gap this question targets, if any.

    Returns:
        The user-message content.
    """
    parts = [f"Question type: {question.type}"]
    if gap is not None:
        parts.append(
            f"Targeted gap ({gap.severity}): {gap.description} "
            f"(JD requirement: {gap.jd_requirement})"
        )
    parts.append(wrap_untrusted(question.text, "question"))
    return "\n\n".join(parts)


def build_evaluation_user_message(
    question: Question,
    answer: str,
    followup: str | None,
    followup_answer: str | None,
    gap: Gap | None,
) -> str:
    """Render the user message for an evaluation call.

    Carries the question, its type, the targeted gap and the answers, each piece of
    untrusted text wrapped in delimiters (FR-14 L4). Contains no instructions, so
    that no prompt text lives in Python (NFR-05).

    Args:
        question: The main question that was asked.
        answer: The candidate's answer.
        followup: The follow-up question, if any.
        followup_answer: The answer to the follow-up, if any.
        gap: The gap this question targets, if any.

    Returns:
        The user-message content.
    """
    parts = [f"Question type: {question.type}"]
    if gap is not None:
        parts.append(
            f"Targeted gap ({gap.severity}): {gap.description} "
            f"(JD requirement: {gap.jd_requirement})"
        )
    parts.append(wrap_untrusted(question.text, "question"))
    parts.append(wrap_untrusted(answer, "answer"))
    if followup is not None and followup_answer is not None:
        parts.append(wrap_untrusted(followup, "question"))
        parts.append(wrap_untrusted(followup_answer, "answer"))
    return "\n\n".join(parts)
