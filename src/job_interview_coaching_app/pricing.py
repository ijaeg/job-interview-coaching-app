"""OpenRouter models endpoint: prices and supported parameters.

Two independent needs are served by the same endpoint:

* ``pricing.prompt`` / ``pricing.completion`` drive the session cost total shown in
  the sidebar (FR-13),
* ``supported_parameters`` decides whether the ``temperature`` and ``top_p``
  controls are enabled, because OpenRouter silently ignores parameters a model does
  not support (FR-11 AC3).

The endpoint is called once per session and cached. If it cannot be reached the app
keeps working and shows "cost unavailable" (FR-13 AC3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from job_interview_coaching_app.llm_client import Usage

#: Public OpenRouter endpoint listing all models with prices and capabilities.
MODELS_ENDPOINT: str = "https://openrouter.ai/api/v1/models"


@dataclass(frozen=True)
class ModelPricing:
    """Per-token prices of one model in USD (FR-13 AC2).

    Attributes:
        prompt_usd_per_token: Price of one prompt token.
        completion_usd_per_token: Price of one completion token, reasoning included.
    """

    prompt_usd_per_token: float
    completion_usd_per_token: float


def fetch_models() -> dict[str, dict[str, Any]]:
    """Fetch the OpenRouter model catalogue once per session.

    Cached so that the sidebar can query prices and capabilities on every rerun
    without another request (FR-13 AC2).

    Returns:
        The model entries keyed by model id; empty when the endpoint is
        unreachable, which is the "cost unavailable" case (FR-13 AC3).
    """
    raise NotImplementedError


def get_pricing(model: str) -> ModelPricing | None:
    """Return the per-token prices of one model.

    Args:
        model: An OpenRouter model id from ``ALLOWED_MODELS``.

    Returns:
        The prices, or ``None`` when the catalogue is unavailable or lists no price
        for this model (FR-13 AC3).
    """
    raise NotImplementedError


def get_supported_parameters(model: str) -> frozenset[str]:
    """Return the sampling parameters a model actually honours.

    Drives FR-11 AC3: ``temperature`` and ``top_p`` are rendered for every model but
    enabled only when they appear here; otherwise they are disabled with the hint
    "Not supported by this model".

    Args:
        model: An OpenRouter model id from ``ALLOWED_MODELS``.

    Returns:
        The supported parameter names; empty when the catalogue is unavailable.
    """
    raise NotImplementedError


def compute_cost(usage: Usage, pricing: ModelPricing | None) -> float | None:
    """Convert token counts into USD.

    Args:
        usage: Token counts of one completed call.
        pricing: Prices of the model used, or ``None`` when unavailable.

    Returns:
        The cost in USD, or ``None`` when no prices are known (FR-13 AC3).
    """
    raise NotImplementedError
