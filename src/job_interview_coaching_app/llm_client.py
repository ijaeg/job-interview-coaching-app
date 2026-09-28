"""OpenRouter access: structured calls, streaming, prompt loading, usage tracking.

The single place that talks to the network. Every other module goes through the
functions here, which keeps the OpenRouter invariants in one file:

* the OpenAI SDK pointed at ``https://openrouter.ai/api/v1`` with the key from
  ``OPENROUTER_API_KEY`` (FR-15 AC3), never the OpenAI API directly,
* reasoning effort passed as ``extra_body={"reasoning": {"effort": ...}}`` (FR-11 AC2),
* ``max_tokens`` defaulting to 4000 because reasoning tokens count against it (NFR-03),
* a 60 s timeout, one automatic retry on invalid JSON and no stack traces (NFR-02),
* prompts loaded from ``prompts/`` so that no prompt text lives in Python (NFR-05).

Related: FR-11, FR-13, NFR-02, NFR-03, NFR-04, NFR-05.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, TypeVar

import streamlit as st
from openai import OpenAI
from pydantic import BaseModel

from job_interview_coaching_app.schemas import RunConfig

#: Directory holding the prompt markdown files, resolved from the repository root.
PROMPTS_DIR: Path = Path(__file__).resolve().parents[2] / "prompts"

#: The three models the Sprint 1 brief allows; nothing else may be selected (FR-11 AC1).
ALLOWED_MODELS: tuple[str, ...] = ("openai/gpt-5-mini", "openai/gpt-5-nano", "openai/gpt-5")

#: Default model of the app (FR-11 AC1).
DEFAULT_MODEL: str = "openai/gpt-5-mini"

#: Default token budget; shared with reasoning tokens (NFR-03).
DEFAULT_MAX_TOKENS: int = 4000

#: Request timeout in seconds (NFR-02).
REQUEST_TIMEOUT_SECONDS: float = 60.0

TModel = TypeVar("TModel", bound=BaseModel)


class LLMError(Exception):
    """Any failure of an LLM call that the UI must show as a friendly message.

    Raised instead of letting SDK exceptions, timeouts, validation errors or the
    empty-content case of NFR-03 reach Streamlit, so the user never sees a stack
    trace (NFR-02).
    """


@dataclass(frozen=True)
class Usage:
    """Token counts of one LLM call, used for the session cost total (FR-13 AC1).

    Attributes:
        prompt_tokens: Tokens of the request.
        completion_tokens: Tokens of the response, including reasoning tokens.
        reasoning_tokens: Reasoning tokens, reported separately when available.
    """

    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int


@st.cache_resource
def get_client() -> OpenAI:
    """Return the shared OpenRouter client, created once per Streamlit session.

    Reads ``OPENROUTER_API_KEY`` from the environment or a ``.env`` file and points
    the OpenAI SDK at the OpenRouter base URL. Cached with ``st.cache_resource`` so
    that reruns reuse one connection pool.

    Returns:
        The configured ``OpenAI`` client.

    Raises:
        LLMError: If no API key is configured (FR-15 AC3).
    """
    raise NotImplementedError


def load_prompt(relative_path: str) -> str:
    """Load a prompt markdown file from ``prompts/``.

    Keeps all prompt text out of the Python sources (NFR-05).

    Args:
        relative_path: Path below ``prompts/``, e.g. ``"analysis.md"`` or
            ``"evaluation/p1_zero_shot.md"``.

    Returns:
        The file contents as the system prompt text.

    Raises:
        LLMError: If the prompt file does not exist.
    """
    raise NotImplementedError


def call_structured(
    messages: list[dict[str, str]],
    response_model: type[TModel],
    run_config: RunConfig,
) -> tuple[TModel, Usage]:
    """Run one non-streamed call that returns schema-validated JSON.

    Used for the analysis plan (§6.1), the answer evaluation (§6.2) and the L3
    guard verdict. Settings are taken exclusively from ``run_config`` (FR-10 AC3).
    Invalid JSON is retried once before an ``LLMError`` is raised (NFR-02); a
    response with ``finish_reason == "length"`` and empty content is turned into the
    explicit out-of-tokens message of NFR-03.

    The caller is responsible for wrapping this in ``st.spinner`` (NFR-04).

    Args:
        messages: Chat messages with their roles (§5.1).
        response_model: The Pydantic model the response is parsed into.
        run_config: Frozen settings of the current run.

    Returns:
        The parsed model instance and the usage of the call (FR-13 AC1).

    Raises:
        LLMError: On API errors, timeout, exhausted token budget or invalid JSON
            after the retry.
    """
    raise NotImplementedError


def stream_text(
    messages: list[dict[str, str]],
    run_config: RunConfig,
) -> Iterator[str]:
    """Run one streamed call that returns free text.

    The only streaming call of the app; it produces the interviewer follow-up and is
    consumed by ``st.write_stream`` (FR-07 AC2, AC3).

    Args:
        messages: The multi-turn interviewer history built by
            ``interview.build_interviewer_messages`` (FR-07 AC1).
        run_config: Frozen settings of the current run.

    Yields:
        Text chunks in arrival order.

    Raises:
        LLMError: On API errors or timeout (NFR-02).
    """
    raise NotImplementedError


def record_usage(usage: Usage, run_config: RunConfig) -> None:
    """Add one call's usage and cost to the session total shown in the sidebar.

    Pricing comes from ``pricing.compute_cost``; if prices are unavailable the
    totals still accumulate tokens and the sidebar shows "cost unavailable"
    (FR-13 AC2, AC3).

    Args:
        usage: Token counts of the completed call.
        run_config: Frozen settings, needed to price the correct model.
    """
    raise NotImplementedError


def extract_usage(response: Any) -> Usage:
    """Read token counts out of a raw OpenRouter response.

    Args:
        response: The SDK response object of a completed call.

    Returns:
        The token counts, with zeros where the provider reported nothing.
    """
    raise NotImplementedError
