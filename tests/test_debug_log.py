"""Tests for the development-only debug log (FR-15 AC5, NFR-06).

The log path is redirected into pytest's temporary directory, so the tests never
touch the real ``logs/`` folder.
"""

from __future__ import annotations

import json

from job_interview_coaching_app import llm_client


def test_debug_log_is_off_by_default(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "logs" / "llm_calls.jsonl"
    monkeypatch.delenv("DEBUG_LOG", raising=False)
    monkeypatch.setattr(llm_client, "DEBUG_LOG_PATH", log_path)

    llm_client.write_debug_log({"kind": "structured"})

    assert not log_path.exists()


def test_debug_log_appends_one_json_line_per_call(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "logs" / "llm_calls.jsonl"
    monkeypatch.setenv("DEBUG_LOG", "1")
    monkeypatch.setattr(llm_client, "DEBUG_LOG_PATH", log_path)

    llm_client.write_debug_log({"kind": "structured"})
    llm_client.write_debug_log({"kind": "stream"})

    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [entry["kind"] for entry in entries] == ["structured", "stream"]
    assert all("timestamp" in entry for entry in entries)
