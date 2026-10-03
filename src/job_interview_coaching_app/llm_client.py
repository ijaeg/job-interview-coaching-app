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

import json
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, TypeVar

import openai
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from job_interview_coaching_app.schemas import RunConfig, Usage

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

#: Attempts for a structured call; the second one only after invalid JSON (NFR-02).
MAX_ATTEMPTS: int = 2

#: Environment variable that switches the development-only debug log on when set to "1" (FR-15 AC5).
DEBUG_LOG_ENV: str = "DEBUG_LOG"

#: JSONL file of the debug log; ``logs/`` is listed in ``.gitignore`` (FR-15 AC5).
DEBUG_LOG_PATH: Path = Path(__file__).resolve().parents[2] / "logs" / "llm_calls.jsonl"

TModel = TypeVar("TModel", bound=BaseModel)


class LLMError(Exception):
    """Any failure of an LLM call that the UI must show as a friendly message.

    Raised instead of letting SDK exceptions, timeouts, validation errors or the
    empty-content case of NFR-03 reach Streamlit, so the user never sees a stack
    trace (NFR-02).
    """


@st.cache_resource
def get_client() -> OpenAI:
    """Return the shared OpenRouter client, created once and reused afterwards.

    Reads ``OPENROUTER_API_KEY`` from the environment or a ``.env`` file and points
    the OpenAI SDK at the OpenRouter base URL, with the 60 s timeout of NFR-02.
    Cached with ``st.cache_resource``, so every rerun and session reuses one
    connection pool.

    Returns:
        The configured ``OpenAI`` client.

    Raises:
        LLMError: If no API key is configured (FR-15 AC3).
    """
    # Called here rather than at import time so that ``app.py`` still renders without a
    # key (NFR-01). A real environment variable keeps precedence over the ``.env`` file.
    load_dotenv()

    # ``.strip()`` turns the empty ``OPENROUTER_API_KEY=`` line of ``.env.example`` into a
    # missing key; the SDK would otherwise raise its own error on an empty string.
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        # Names the variable, never its value (FR-15 AC3), and no stack trace (NFR-02).
        raise LLMError(
            "No OpenRouter API key found. Set OPENROUTER_API_KEY in your environment "
            "or in a .env file next to app.py, then reload the page."
        )

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


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
    path = PROMPTS_DIR / relative_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as err:
        raise LLMError(f"Prompt file not found: prompts/{relative_path}") from err


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
    kwargs = {
        "model": run_config.model,
        "messages": messages,
        "response_format": response_model,
        "max_tokens": run_config.max_tokens,
        "extra_body": {"reasoning": {"effort": run_config.reasoning_effort}},
    }
    if run_config.temperature is not None:
        kwargs["temperature"] = run_config.temperature
    if run_config.top_p is not None:
        kwargs["top_p"] = run_config.top_p

    started = time.perf_counter()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = get_client().chat.completions.parse(**kwargs)
            break
        except openai.LengthFinishReasonError as err:
            raise LLMError("The model ran out of tokens – increase max tokens in the developer settings") from err
        except openai.ContentFilterFinishReasonError as err:
            raise LLMError("Response has been filtered by API provider.") from err
        except ValidationError as err:
            if attempt == MAX_ATTEMPTS:             # second failure: give up
                raise LLMError(
                    "The model returned an answer in an unexpected format. Please try again."
                ) from err
        except openai.APITimeoutError as err:
            raise LLMError("The request timed out after 60 seconds. Please try again.") from err
        except openai.APIStatusError as err:
            raise LLMError(f"API responded with status code {err.status_code}") from err
        except openai.APIConnectionError as err:
            raise LLMError("API Connection could not be established.") from err

    message = response.choices[0].message
    if message.parsed is None:
        if message.refusal:
            raise LLMError("The model declined to answer this request.")
        raise LLMError("The model returned no usable answer. Please try again.")

    usage = extract_usage(response)
    write_debug_log(
        {
            "kind": "structured",
            "model": run_config.model,
            "reasoning_effort": run_config.reasoning_effort,
            "eval_variant": run_config.eval_variant,
            "response_model": response_model.__name__,
            "messages": messages,
            "response": message.parsed.model_dump(),
            "usage": asdict(usage),
            "latency_s": round(time.perf_counter() - started, 2),
        }
    )
    return message.parsed, usage

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
    kwargs = {
        "model": run_config.model,
        "messages": messages,
        "max_tokens": run_config.max_tokens,
        "stream": True,
        "extra_body": {"reasoning": {"effort": run_config.reasoning_effort}},
    }
    if run_config.temperature is not None:
        kwargs["temperature"] = run_config.temperature
    if run_config.top_p is not None:
        kwargs["top_p"] = run_config.top_p

    started = time.perf_counter()
    pieces: list[str] = []
    usage: Usage | None = None
    try:
        for chunk in get_client().chat.completions.create(**kwargs):
            # The final chunk may carry the token usage but no choices; read it first.
            if chunk.usage is not None:
                usage = extract_usage(chunk)
            # Chunks without choices and reasoning-only chunks carry no visible text.
            if not chunk.choices:
                continue
            text = chunk.choices[0].delta.content
            if text:
                pieces.append(text)
                yield text
    except openai.APITimeoutError as err:
        raise LLMError("The request timed out after 60 seconds. Please try again.") from err
    except openai.APIStatusError as err:
        raise LLMError(f"API responded with status code {err.status_code}") from err
    except openai.APIConnectionError as err:
        raise LLMError("API Connection could not be established.") from err

    if not pieces:
        # NFR-03: reasoning tokens used up the whole budget before any text arrived.
        raise LLMError("The interviewer returned no text - increase max tokens in the developer settings.")
    write_debug_log(
        {
            "kind": "stream",
            "model": run_config.model,
            "reasoning_effort": run_config.reasoning_effort,
            "messages": messages,
            "response": "".join(pieces),
            "usage": asdict(usage) if usage is not None else None,
            "latency_s": round(time.perf_counter() - started, 2),
        }
    )


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
    usage = response.usage
    if usage is None:
        return Usage(prompt_tokens=0, completion_tokens=0, reasoning_tokens=0)

    details = usage.completion_tokens_details
    return Usage(
        prompt_tokens=usage.prompt_tokens or 0,
        completion_tokens=usage.completion_tokens or 0,
        reasoning_tokens=(details.reasoning_tokens or 0) if details else 0,
    )


def write_debug_log(record: dict[str, Any]) -> None:
    """Append one LLM call to the development-only debug log (FR-15 AC5).

    Does nothing unless the environment variable ``DEBUG_LOG`` is set to ``"1"``. The
    log holds the full messages, i.e. JD, CV and answers, so it is meant for
    development and tests with the fictional sample data only and must never be
    enabled in a deployed app. A failing write never interrupts the app (NFR-02).

    Args:
        record: The call details; a UTC timestamp is added in front.
    """
    if os.getenv(DEBUG_LOG_ENV) != "1":
        return
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # a debug aid must never break the app
