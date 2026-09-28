# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Turing College Sprint 1 submission: the **Gap-Focused Interview Coach**, a single-page
Streamlit app where a user pastes a job description (JD) and a CV, the app finds CV↔JD gaps,
runs a chat mock interview targeting those gaps, LLM-judges each answer, and prints a scored
report.

Two documents govern the work and should be read before non-trivial changes:

- `PRODUCT_SPEC.md` — **the source of truth.** Versioned with a change log (§13, currently
  v0.2.2). Requirements have stable IDs (`FR-07`, `NFR-06`, `AC3`); use them in commit messages
  and PR descriptions. If code and spec disagree, update the spec deliberately rather than
  letting them drift.
- `115.md` — the upstream assignment brief: mandatory requirements, the optional-task list the
  spec claims in §10.2, and the review criteria.

The repo is still mostly unbuilt. Most of the layout in §9 below does not exist yet.

## Commands

The project is **uv-only**. Never invoke bare `pip` or `python`.

```bash
uv sync                               # install/lock deps (build backend: uv_build, src layout)
uv add <pkg>                          # add a dependency
uv run streamlit run app.spike.py     # run the day-1 spike (works today)
uv run streamlit run app.py           # run the real app (NFR-01; app.py not created yet)
uv run pytest                         # tests (NFR-06; no tests or pytest dep yet)
uv run pytest tests/test_guards.py::test_name -v   # single test
uv run python eval/run_eval.py        # prompt-variant evaluation harness (§7.2; not created yet)
```

Python 3.13, pinned by `.python-version` and `requires-python = ">=3.13"`.

`OPENROUTER_API_KEY` must be set in the environment or a `.env` file (gitignored). There is no
`.env.example`. No linter, formatter, type checker, or CI is configured.

## Target architecture (PRODUCT_SPEC.md §9)

```text
app.py                     # Streamlit UI + state machine ONLY — contains no prompt text (NFR-05)
src/<pkg>/llm_client.py    # OpenRouter calls (parse + streaming), settings, usage/cost tracking
src/<pkg>/schemas.py       # Pydantic: InterviewPlan, AnswerEvaluation, GuardVerdict
src/<pkg>/interview.py     # question-mix rule, interviewer message builder, score aggregation
src/<pkg>/evaluation.py    # prompt variants P1–P5 (P4/P5 are two-call variants)
src/<pkg>/guards.py        # security layers L1–L3
src/<pkg>/pricing.py       # OpenRouter /models endpoint: prices + supported_parameters
prompts/{analysis,interviewer,classifier}.md
prompts/evaluation/p1_zero_shot.md … p5_self_refinement.md
data/samples/              # fictional JD + CV
eval/{dataset.json,run_eval.py,results.csv}
docs/{security_tests.md,security_tests.xlsx}
tests/
```

### State machine

All state lives in `st.session_state`:

```text
SETUP ──► BRIEF ──────────────► INTERVIEW ─────────────────────► REPORT
JD + CV   1 LLM call            per question: ask → answer        Python aggregation
or sample (JSON, analysis.md)   → follow-up (streamed)            (no LLM call)
          → InterviewPlan       → evaluation (JSON, hidden)
```

"Start over" returns to `SETUP` and clears all data.

### The four LLM call types

Each demonstrates a different combination of roles and output types (§5.1):

1. **Guard classifier (L3, Should)** — cheap `gpt-5-nano` call, `prompts/classifier.md` →
   `GuardVerdict` JSON.
2. **Analysis + question planning** — one call, `prompts/analysis.md` → `InterviewPlan` JSON
   (role summary, 2–5 strengths, 2–5 `Gap`s with severity, exactly *n* `Question`s typed
   `opener` / `gap` / `reverse`). Question-mix rule: Q1 is the `opener`, middle questions are
   `gap` questions ordered by severity, the last is `reverse` only when n ≥ 4.
3. **Interviewer follow-up** — the **only multi-turn call**. The message builder in
   `interview.py` sends `system` (instructions + role summary + gaps), then alternating
   `assistant` (previous questions) and `user` (previous answers). Output is **free text,
   streamed** via `stream=True` + `st.write_stream`. Fires only after `gap` questions.
4. **Answer evaluation** — per main question, one of five prompt variants → `AnswerEvaluation`
   JSON. `reasoning` is placed **before** `score` in the schema so chain-of-thought actually
   works. Hidden from the user until the report.

### Prompt variants P1–P5

The five variants apply **only** to answer evaluation (FR-08), because only there can "best"
be measured against reference answers. P1 zero-shot · P2 few-shot · P3 chain-of-thought ·
P4 generated knowledge (2 calls) · P5 self-refinement (2 calls). All other prompts are fixed.
`eval/run_eval.py` scores them over 5 variants × 8 reference answers × 2 runs = 80 rows into `results.csv`;
winner by band accuracy, tie-break MAE then cost. P2's few-shot examples must not come from the
evaluation dataset (no leakage).

## Invariants

- **OpenRouter, never OpenAI directly.** Use the OpenAI SDK pointed at
  `base_url="https://openrouter.ai/api/v1"` with `api_key` from `OPENROUTER_API_KEY`.
  Reasoning effort goes through `extra_body={"reasoning": {"effort": ...}}`.
- **Model allow-list is exactly** `openai/gpt-5-mini` (default), `openai/gpt-5-nano`,
  `openai/gpt-5`. Nothing else is permitted by the brief.
- **`max_tokens` defaults to 4,000** because reasoning tokens count against it. Handle
  `finish_reason == "length"` with empty content explicitly (NFR-03).
- **`RunConfig` freeze (FR-10 AC3).** At `BRIEF → INTERVIEW`, model, reasoning effort, max
  tokens, sampling params, and evaluation variant are copied into an immutable frozen dataclass
  in `st.session_state`. Every LLM call reads settings **only** from that `RunConfig`, never from
  widgets. Sidebar controls are `disabled=True` during `INTERVIEW`/`REPORT`, and each stored
  `AnswerEvaluation` carries the `RunConfig` it was produced with.
- **No prompt text in `app.py`** (NFR-05). Prompts are `.md` files under `prompts/`.
- **Security guard, four layers (FR-14).** L1 length/non-empty checks (JD ≤ 8,000, CV ≤ 12,000,
  answers ≤ 3,000 chars) · L2 regex injection heuristics on JD, CV and every answer · L3 optional
  `gpt-5-nano` classifier · L4 prompt hardening — untrusted text wrapped in delimiters such as
  `<job_description>…</job_description>`, system prompts declaring that content is data and never
  instructions, plus schema validation and score range checks.
- **Privacy (FR-15).** JD, CV and answers stay in `st.session_state` only — never written to disk,
  never logged. Development and tests use fictional sample data only.
- **Every non-streamed LLM call runs inside `st.spinner`** with descriptive text (NFR-04). Errors
  never surface a stack trace; 60 s timeout; one automatic retry on invalid JSON (NFR-02).
- **English only** in UI and docs (NFR-08).
- **Tests mock all LLM calls** and cover deterministic logic only: guards, question-mix rule,
  interviewer message-builder roles, score aggregation, state transitions, `RunConfig`
  consistency (NFR-06).

## Scope discipline

Sprint 1 explicitly excludes LangChain, agents, RAG/vector DB, PDF upload, persistence, and
deployment (§2.2). Spec §11 defines a cut rule: anything not working by end of day 4 that is not
a *Must* is dropped and listed under "Ideas for improvement" — except §7 (prompt evaluation) and
FR-07 (adaptive follow-up), which are never cut.

`README.md` is currently empty and must eventually carry all sections listed in §10.2 (NFR-07).
