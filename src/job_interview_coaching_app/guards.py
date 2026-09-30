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

import re
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

#: The message shown when L2 or L3 detects an injection attempt (FR-14 AC1, verbatim).
INJECTION_MESSAGE: str = (
    "Your document contains text that looks like instructions to an AI. Please remove it."
)

#: L2 heuristics, one entry per attack family (FR-14 L2). Kept deliberately narrow: an
#: ordinary CV may well mention prompts or systems, so a bare "system prompt" keyword and a
#: bare "act as a ..." are not patterns here; persona overrides are caught by the more
#: specific phrasings below.
INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Instruction override: "ignore all previous instructions", and phrasings with words in
    # between such as "ignore your rubric and all previous instructions".
    re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\b[^.!?\n]{0,60}?"
        r"\b(?:previous|prior|preceding|earlier|above|all)\b[^.!?\n]{0,20}?"
        r"\b(?:instruction|prompt|rule|direction|guideline|rubric)s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:the|your|these|those|any)\s+"
        r"(?:\w+\s+){0,2}?(?:instruction|prompt|rule|direction|guideline|rubric)s?\b",
        re.IGNORECASE,
    ),
    # System-prompt reveal: "show me your system prompt" (FR-14 AC4).
    re.compile(
        r"\b(?:show|reveal|print|repeat|display|output|reproduce|tell)\b[^.!?\n]{0,40}?"
        r"\b(?:system|initial|original)\s+(?:prompt|message|instruction)s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\byour\s+(?:system|initial|original)\s+(?:prompt|message|instruction)s?\b",
        re.IGNORECASE,
    ),
    # Persona override.
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+now\s+on,?\s+you\b", re.IGNORECASE),
    re.compile(r"\bpretend\s+(?:to\s+be|you\s+are)\b", re.IGNORECASE),
    re.compile(
        r"(?:^|[.!?]\s+)(?:please\s+)?act\s+as\s+(?:an?\s+)?"
        r"(?:ai|assistant|chatbot|language\s+model)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"\b(?:new|updated|revised)\s+(?:instruction|rule|task)s?\s*:", re.IGNORECASE),
    # Text addressed at the model rather than at a human reader.
    re.compile(
        r"\b(?:note|message)s?\s+to\s+(?:the\s+)?"
        r"(?:ai|llm|assistant|model|evaluator|(?:evaluation\s+)?system)\b",
        re.IGNORECASE,
    ),
    # Score manipulation (FR-14 AC3).
    re.compile(
        r"\b(?:give|rate|award|assign|grade)\b[^.!?\n]{0,40}?"
        r"\b(?:maximum|highest|full|perfect|top|best)\b[^.!?\n]{0,20}?"
        r"\b(?:score|rating|grade|mark|point)s?\b",
        re.IGNORECASE,
    ),
    # Chat role tags in template syntax (plain "System:" lines are not flagged: they are
    # indistinguishable from ordinary CV lists; L4 delimiters cover that case).
    re.compile(
        r"<\|?\s*/?\s*(?:system|user|assistant|developer|im_start|im_end)[^>]*\|?>",
        re.IGNORECASE,
    ),
    re.compile(r"\[\s*/?\s*(?:INST|SYS)\s*\]", re.IGNORECASE),
    # Escaping the L4 delimiters this app puts around untrusted text.
    re.compile(r"</?\s*(?:job_description|cv|answer|question)\s*>", re.IGNORECASE),
    # Jailbreak jargon.
    re.compile(
        r"\b(?:jailbreak|dan\s+mode|do\s+anything\s+now)\b",
        re.IGNORECASE,
    ),
)


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
    if not text.strip():
        return GuardResult(
            ok=False,
            message=f"{field_label} must not be empty."
        )
    if len(text) > max_chars:
        return GuardResult(
            ok=False,
            message=f"{field_label} is too long ({len(text)} characters, maximum {max_chars}).")
    return GuardResult(ok=True)


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
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return GuardResult(ok=False, message=INJECTION_MESSAGE)
    return GuardResult(ok=True)


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
    return f"<{tag}>\n{text}\n</{tag}>"
