"""Tests for the security guard layers L1 and L2 (FR-14, NFR-06).

Deterministic only: no LLM call is made here. The L3 classifier is covered by a
mocked call once it exists. Fictional sample data only (FR-15 AC4).
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="not implemented")
def test_check_length_rejects_empty_input() -> None:
    """L1 rejects an empty or whitespace-only field (FR-14 L1)."""
    raise NotImplementedError


@pytest.mark.skip(reason="not implemented")
def test_check_length_rejects_input_above_limit() -> None:
    """L1 rejects over-long input and names the limit (FR-01 AC3, FR-06 AC3)."""
    raise NotImplementedError


@pytest.mark.skip(reason="not implemented")
def test_check_length_accepts_input_within_limit() -> None:
    """L1 lets normal input through unchanged."""
    raise NotImplementedError


@pytest.mark.skip(reason="not implemented")
def test_detect_injection_flags_known_patterns() -> None:
    """L2 flags "ignore previous instructions", "system prompt", role tags (FR-14 AC1)."""
    raise NotImplementedError


@pytest.mark.skip(reason="not implemented")
def test_detect_injection_passes_clean_text() -> None:
    """L2 does not flag an ordinary CV sentence (no false positive)."""
    raise NotImplementedError


@pytest.mark.skip(reason="not implemented")
def test_wrap_untrusted_wraps_text_in_delimiters() -> None:
    """L4 wraps untrusted text as ``<tag>...</tag>`` (FR-14 L4)."""
    raise NotImplementedError
