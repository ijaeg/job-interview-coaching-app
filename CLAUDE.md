# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Turing College Sprint 1 submission: the **Gap-Focused Interview Coach**, a single-page
Streamlit app where a user pastes a job description (JD) and a CV, the app finds CV↔JD gaps,
runs a chat mock interview targeting those gaps, LLM-judges each answer, and prints a scored
report.

Two documents govern the work and should be read before non-trivial changes:

- `PRODUCT_SPEC.md` — **the source of truth.** Versioned with a change log (§13, currently
  v0.2.6). Requirements have stable IDs (`FR-07`, `NFR-06`, `AC3`); use them in commit messages
  and PR descriptions. If code and spec disagree, update the spec deliberately rather than
  letting them drift.
- `115.md` — the upstream assignment brief: mandatory requirements, the optional-task list the
  spec claims in §10.2, and the review criteria.

Every module docstring ends with a `Related: FR-…, §…` line and most functions name the
requirement they implement. Keep that convention: it is how the spec and the code stay joined,
and the review is scored on that traceability.

## Commands

The project is **uv-only**. Never invoke bare `pip` or `python`.

```bash
uv sync                               # install/lock deps (build backend: uv_build, src layout)
uv add <pkg>                          # add a dependency
uv run streamlit run app.py           # run the app
uv run pytest                         # tests (NFR-06) — currently 50 pass, none skipped
uv run pytest tests/test_guards.py::test_name -v   # single test
uv run python eval/run_eval.py        # full evaluation run (§7.2): 5 variants x 8 answers x 2 runs -> eval/results.csv
uv run python eval/run_eval.py --variants p1_zero_shot p3_chain_of_thought --runs 2
uv run python eval/run_eval.py --variants p1_zero_shot --effort minimal --output eval/effort_minimal.csv
DEBUG_LOG=1 uv run streamlit run app.py   # opt-in debug log -> logs/llm_calls.jsonl (FR-15 AC5)
```

Python 3.13, pinned by `.python-version` and `requires-python = ">=3.13"`.

`OPENROUTER_API_KEY` must be set in the environment or a `.env` file (gitignored);
`cp .env.example .env` and fill it in. No linter, formatter, type checker, or CI is configured
(ruff is run ad hoc via `uvx ruff check`, which is why a `.ruff_cache/` exists).

`app.spike.py` is the throwaway day-1 chatbot spike. It is kept as a record, is not part of the
app, and should not be updated or linted into shape.

## Architecture

```text
app.py                                 # Streamlit UI + state machine ONLY — no prompt text (NFR-05)
src/job_interview_coaching_app/
    llm_client.py   # OpenRouter client, call_structured / stream_text, prompt loading, usage + session total, debug log
    schemas.py      # Pydantic: InterviewPlan, AnswerEvaluation, GuardVerdict; frozen RunConfig, Usage
    interview.py    # State enum, Turn/TurnResult, question-mix rule, message builder, RunConfig snapshot, aggregation
    evaluation.py   # EvalVariant P1–P5 dispatch (P4/P5 are two-call variants)
    guards.py       # security layers L1–L4
    pricing.py      # OpenRouter /models endpoint: prices, cost, supported_parameters
prompts/{analysis,interviewer,classifier}.md
prompts/evaluation/p1_zero_shot.md … p5_self_refinement.md, p4_generated_knowledge_step1.md (P4 call 1)
data/samples/                          # fictional JD + CV
eval/{dataset.json,run_eval.py}        # results.csv (main run), effort_minimal/medium.csv (§7.3)
docs/security_tests.md                 # security_tests.xlsx still to be produced
tests/
```

The dependency direction is one-way: `app.py` → `interview`/`evaluation`/`guards` →
`llm_client` → `pricing`/`schemas`. `app.py` never calls `llm_client` directly (it imports
constants only) and reads `pricing.get_supported_parameters` for the sidebar. Nothing below
`app.py` touches Streamlit state, with three deliberate exceptions: `llm_client.get_client` uses
`@st.cache_resource`, `interview.generate_followup` wraps `st.write_stream`, and
`llm_client.record_usage` adds every call to `st.session_state["usage_total"]` (it also works in
bare mode, so `eval/run_eval.py` is unaffected apart from a Streamlit warning).

### State machine

All state lives in `st.session_state`, keyed as in `app.py:init_session_state`
(`state`, `jd`, `cv`, `n_questions`, `plan`, `run_config`, `q_index`, `pending`, `results`, and
the sidebar widget keys `model`, `reasoning_effort`, `max_tokens`, `temperature`, `top_p`,
`eval_variant`; `usage_total` is created by `llm_client.record_usage` on the first call):

```text
SETUP ──► BRIEF ──────────────► INTERVIEW ─────────────────────► REPORT
JD + CV   1 LLM call            per question: ask → answer        Python aggregation
or sample (JSON, analysis.md)   → follow-up (streamed)            (no LLM call)
          → InterviewPlan       → evaluation (JSON, hidden)
```

Within `INTERVIEW` each question is a two-step rerun cycle: an answer to a `gap` question is
stashed in `pending` with its streamed follow-up, and the *next* `st.chat_input` submission is
read as the follow-up answer before the turn is evaluated and appended to `results`.
"Start over" deletes every session-state key and returns to `SETUP`.

### The four LLM call types

Each demonstrates a different combination of roles and output types (§5.1):

1. **Guard classifier (L3, Should)** — cheap `gpt-5-nano` call, `prompts/classifier.md` →
   `GuardVerdict` JSON. Pinned to `CLASSIFIER_MODEL` regardless of the selected model.
2. **Analysis + question planning** — one call, `prompts/analysis.md` → `InterviewPlan` JSON
   (role summary, 2–5 strengths, 2–5 `Gap`s with severity, exactly *n* `Question`s typed
   `opener` / `gap` / `reverse`). Question-mix rule: Q1 is the `opener`, middle questions are
   `gap` questions ordered by severity, the last is `reverse` only when n ≥ 4. The JSON schema
   cannot express this, so `interview._validate_plan` re-checks the mix, unknown `gap_id`s and
   duplicate question texts and raises `LLMError` on violation.
3. **Interviewer follow-up** — the **only multi-turn and only streamed call**. The message
   builder in `interview.py` sends `system` (instructions + role summary + gaps), then
   alternating `assistant` (previous questions) and `user` (previous answers). Fires only after
   `gap` questions. A failure here is non-fatal: the turn continues without a follow-up.
4. **Answer evaluation** — per main question, one of five prompt variants → `AnswerEvaluation`
   JSON. `reasoning` is placed **before** `score` in the schema so chain-of-thought actually
   works. Hidden from the user until the report; a failure stores `evaluation=None` and that
   turn is simply left out of the mean.

### Prompt variants P1–P5

The five variants apply **only** to answer evaluation (FR-08), because only there can "best"
be measured against reference answers. P1 zero-shot · P2 few-shot · P3 chain-of-thought ·
P4 generated knowledge (2 calls) · P5 self-refinement (2 calls). All other prompts are fixed.
`EvalVariant`'s member values *are* the prompt file stems below `prompts/evaluation/`, so adding
a variant means adding a file and a member. `eval/run_eval.py` scores them over 5 variants ×
8 reference answers × 2 runs = 80 rows into `results.csv`; winner by band accuracy, tie-break MAE
then cost. P2's few-shot examples must not come from the evaluation dataset (no leakage).

## Invariants

- **OpenRouter, never OpenAI directly.** Use the OpenAI SDK pointed at
  `base_url="https://openrouter.ai/api/v1"` with `api_key` from `OPENROUTER_API_KEY`.
  Reasoning effort goes through `extra_body={"reasoning": {"effort": ...}}`.
- **Model allow-list is exactly** `openai/gpt-5-mini` (default), `openai/gpt-5-nano`,
  `openai/gpt-5`. Nothing else is permitted by the brief.
- **No sampling parameters.** Day-1 check against the models endpoint confirmed that none of the
  three allowed models supports `temperature` or `top_p` (spec §12). `RunConfig` still carries
  both fields and the call paths still forward them when non-`None`, but they stay `None`, the
  sidebar controls stay disabled (FR-11 AC3), and §7.3 compares reasoning effort only. Don't
  "fix" this by setting a temperature.
- **`max_tokens` defaults to 4,000** because reasoning tokens count against it. Handle
  `finish_reason == "length"` with empty content explicitly (NFR-03) — including in the stream,
  where a chunk loop that yields no text at all means the budget went to reasoning.
- **`RunConfig` freeze (FR-10 AC3).** At `BRIEF → INTERVIEW`, model, reasoning effort, max
  tokens, sampling params, and evaluation variant are copied into an immutable frozen dataclass
  in `st.session_state`. Every LLM call reads settings **only** from that `RunConfig`, never from
  widgets. Sidebar controls are `disabled=True` during `INTERVIEW`/`REPORT`, and each stored
  `TurnResult` carries the `RunConfig` its evaluation was produced with.
- **No prompt text in `app.py`** (NFR-05) — and none in any other `.py` either. Prompts are `.md`
  files under `prompts/`, loaded by `llm_client.load_prompt`. The user-message builders in
  `interview.py`/`evaluation.py` assemble labels and delimiters only, never instructions.
- **Security guard, four layers (FR-14).** L1 length/non-empty checks (JD ≤ 8,000, CV ≤ 12,000,
  answers ≤ 3,000 chars) · L2 regex injection heuristics on JD, CV and every answer · L3 optional
  `gpt-5-nano` classifier · L4 prompt hardening — untrusted text wrapped by `wrap_untrusted` in
  delimiters such as `<job_description>…</job_description>`, system prompts declaring that
  content is data and never instructions, plus schema validation and score range checks. L2
  patterns are deliberately narrow (a real CV may say "system prompt"); widen them only with a
  test case in `tests/test_guards.py`.
- **Privacy (FR-15).** JD, CV and answers stay in `st.session_state` only — never written to disk,
  never logged, with one exception: the opt-in debug log (`DEBUG_LOG=1` → `logs/llm_calls.jsonl`,
  gitignored, FR-15 AC5) for development with the fictional sample data. Development and tests
  use fictional sample data only. Error messages name the `OPENROUTER_API_KEY` variable, never
  its value.
- **Every non-streamed LLM call runs inside `st.spinner`** with descriptive text (NFR-04), and
  the `st.spinner` belongs in `app.py`, not in the module making the call. Errors never surface a
  stack trace: `llm_client` converts every `openai` exception into an `LLMError` with a
  user-facing sentence, 60 s timeout, one automatic retry on invalid JSON (NFR-02). `app.py`
  catches `LLMError` and nothing else.
- **English only** in UI and docs (NFR-08).
- **Tests mock all LLM calls** and cover deterministic logic only: guards, question-mix rule,
  interviewer message-builder roles, score aggregation, state transitions, `RunConfig`
  consistency (NFR-06).

## Current state

The happy path runs end to end. All five evaluation variants P1–P5 work (P4/P5 with two calls
each), the full evaluation run is in `eval/results.csv`, and P1 zero-shot won and is
`evaluation.DEFAULT_VARIANT`. The developer sidebar (FR-10 to FR-13) is built: model, reasoning
effort, max tokens, sampling sliders (disabled unless `pricing.get_supported_parameters` lists
them), the P1–P5 selector and the session token/cost total from `llm_client.record_usage`.
`app.current_run_config` snapshots the widgets via `interview.snapshot_run_config`; the analysis
uses the current snapshot, `freeze_run_config` stores it at `BRIEF → INTERVIEW`. The opt-in debug
log (`DEBUG_LOG=1`) is in `llm_client`. All tests pass, none are skipped;
`tests/test_app_flow.py` drives the whole app through `streamlit.testing.v1.AppTest` with every
LLM call mocked.

Still open, each raising `NotImplementedError` or marked TODO — check these before assuming a
feature works:

- `guards.classify_inputs` + `prompts/classifier.md` → L3 is not wired up.
- `docs/security_tests.md` has no rows and `docs/security_tests.xlsx` does not exist (FR-14 AC5).
- `README.md`: the evaluation results and the settings experiment are written; screenshots,
  design decisions, security test summary, ChatGPT critique, parts of the known limitations,
  ideas for improvement and the traceability table are still TBD.

## Conventions

Commit messages are lowercase imperative with the requirement IDs in parentheses, e.g.
`implement follow-up streaming, P1 evaluation and score aggregation (FR-07, FR-08, FR-09 AC1)`.
Work happens on one topic branch per feature area (`feature/…`, e.g. `feature/prompt-evaluation`);
`main` holds the reviewed state and is updated only through pull requests with merge commits
(no squash, so the per-requirement commits stay visible).

Docstrings are Google-style (`Args:` / `Returns:` / `Raises:`) and cite requirement IDs. Module
constants carry `#:` comments. `from __future__ import annotations` at the top of every module.

## Scope discipline

Sprint 1 explicitly excludes LangChain, agents, RAG/vector DB, PDF upload, persistence, and
deployment (§2.2). Anything that is not working by the feature freeze on **Tue 2026-10-06** is
dropped, marked as not implemented, and listed under "Ideas for improvement" in the README — except
§7 (prompt evaluation) and FR-07 (adaptive follow-up), which are never cut. Hard deadline is
Mon 2026-10-12; no new features after the freeze.

`README.md` contains all sections listed in §10.2 (NFR-07); see *Current state* for the ones that
are still TBD. The README must always match the actual state of the code.
