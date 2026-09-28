"""The layered security guard, FR-14 layers L1-L4.

| Layer | Mechanism                                                            |
|-------|----------------------------------------------------------------------|
| L1    | Length limits and non-empty checks (``check_length``)                |
| L2    | Regex/keyword injection heuristics (``detect_injection``)            |
| L3    | One cheap ``gpt-5-nano`` classifier call (``classify_inputs``)       |
| L4    | Delimiter wrapping of untrusted text (``wrap_untrusted``)            |

L4 also covers the parts that live elsewhere: every system prompt states that
delimited content is data and never instructions, and every JSON response is
schema-validated with a range-checked score (see ``schemas``).

L1 and L2 are deterministic and unit-tested with no LLM involved (NFR-06); the
adversarial cases are documented in ``docs/security_tests.md`` (FR-14 AC5).
"""

from __future__ import annotations

from dataclasses import dataclass

from job_interview_coaching_app.schemas import GuardVerdict, RunConfig

#: L1 character limits (FR-01 AC3, FR-06 AC3).
MAX_JD_CHARS: int = 8000
MAX_CV_CHARS: int = 12000
MAX_ANSWER_CHARS: int = 3000

#: Minimum length before the "Analyse" button becomes enabled (FR-01 AC2).
MIN_INPUT_CHARS: int = 200

#: Model used by the L3 classifier; deliberately the cheapest allowed one (FR-14 L3).
CLASSIFIER_MODEL: str = "openai/gpt-5-nano"


@dataclass(frozen=True)
class GuardResult:
    """Outcome of a guard check.

    Attributes:
        ok: True when the text may be passed on to an LLM call.
        message: User-facing explanation when ``ok`` is False; never a stack trace
            and never the system prompt (FR-14 AC4, NFR-02).
    """

    ok: bool
    message: str | None = None


def check_length(text: str, max_chars: int, field_label: str) -> GuardResult:
    """L1: reject empty or over-long input.

    Args:
        text: The untrusted text to check.
        max_chars: The applicable limit, e.g. ``MAX_JD_CHARS``.
        field_label: Human-readable field name used in the message.

    Returns:
        A failing ``GuardResult`` whose message names the limit (FR-01 AC3,
        FR-06 AC3), otherwise a passing one.
    """
    raise NotImplementedError


def detect_injection(text: str) -> GuardResult:
    """L2: flag text that looks like instructions addressed to an AI.

    Regex and keyword heuristics for patterns such as "ignore (all|previous)
    instructions", "system prompt", "you are now" and role tags. Applied to the JD,
    the CV and every chat answer before it enters the conversation history
    (FR-14 AC1, FR-07 AC5).

    Args:
        text: The untrusted text to check.

    Returns:
        A failing ``GuardResult`` carrying the FR-14 AC1 message when a pattern
        matches, otherwise a passing one.
    """
    raise NotImplementedError


def classify_inputs(jd: str, cv: str, run_config: RunConfig) -> GuardVerdict:
    """L3: ask a cheap classifier whether JD and CV really are what they claim.

    One ``gpt-5-nano`` call with ``prompts/classifier.md`` before the analysis. A
    recipe pasted as a job description is rejected with a clear message (FR-14 AC2),
    as is a document containing instructions addressed to an AI (FR-14 AC1).
    Priority *Should*: the app must stay usable if this layer is skipped.

    Args:
        jd: The job description, already through L1 and L2.
        cv: The CV, already through L1 and L2.
        run_config: Frozen settings of the current run; the classifier model is
            fixed to ``CLASSIFIER_MODEL`` regardless of the selected model.

    Returns:
        The parsed verdict.

    Raises:
        LLMError: On API failure or invalid JSON after the retry (NFR-02).
    """
    raise NotImplementedError


def wrap_untrusted(text: str, tag: str) -> str:
    """L4: wrap untrusted text in delimiters so the model treats it as data.

    Args:
        text: The untrusted text, e.g. the JD, the CV or an answer.
        tag: The delimiter name, e.g. ``"job_description"``, producing
            ``<job_description>...</job_description>``.

    Returns:
        The delimited text, ready to be placed in a user message. The matching
        "this is data, never instructions" statement lives in the prompt files, not
        here (NFR-05).
    """
    raise NotImplementedError
