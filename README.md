# Gap-Focused Interview Coach

A Streamlit app that prepares a candidate for one specific job interview. Turing College,
AI Engineering, Sprint 1. The authoritative design document is
[`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) (v0.2.6).

## Purpose

The user pastes a **job description** (JD) and their **CV**. The app then

1. analyses where the CV matches the job and where it has **gaps** — missing skills, short
   tenures or unexplained career steps, weak evidence,
2. runs a short **mock interview as a chat**: the planned questions target those gaps, and an LLM
   interviewer that sees the whole conversation asks **follow-up questions**,
3. evaluates **each answer** with an LLM acting as judge against an explicit rubric, using the
   STAR method for behavioural questions, and
4. shows a **feedback report** with scores, strengths, concrete improvements and an improved
   example answer.

The engineering focus is not the feature count but a measurable comparison of five prompting
techniques for the answer-evaluation task, a documented model-settings experiment, and a layered
security guard.

**Current state.** The path `SETUP → BRIEF → INTERVIEW → REPORT` runs end to end. All five
evaluation variants P1–P5 are implemented and were compared in a full evaluation run; P1
(zero-shot) won and is the default. Prices come from the OpenRouter models endpoint, and the
evaluation harness reports the cost per evaluation. The developer sidebar (including the variant
selector and the cost display) and the L3 classifier are not built yet. The table below is derived from the code, not from the spec;
"partly" means that some acceptance criteria are met and others are still open.

| ID | Requirement | Status | Notes |
|---|---|---|---|
| FR-01 | Text input for JD and CV | implemented | Limits enforced: JD 8,000, CV 12,000 characters |
| FR-02 | Sample data | implemented | Fictional JD and CV in `data/samples/` |
| FR-03 | Number of questions | implemented | Slider 3–8, default 3 |
| FR-04 | Gap analysis | implemented | Role summary, strengths and gaps with severity |
| FR-05 | Main question planning | implemented | Question mix, gap references and duplicate texts re-checked in `interview._validate_plan` |
| FR-06 | Chat-based interview | implemented | Includes early "Finish interview" |
| FR-07 | Adaptive follow-up | implemented | Multi-turn, streamed, after `gap` questions only |
| FR-08 | Per-answer evaluation | implemented | All five variants P1–P5; P4 and P5 make two calls each. Default is P1, the winner of the evaluation run |
| FR-09 | Report | implemented | Overall score computed in Python, no extra LLM call |
| FR-10 | Separated developer settings | partly | The frozen `RunConfig` and the `BRIEF → INTERVIEW` freeze exist; `app.render_sidebar` renders a TODO placeholder, so no control is shown |
| FR-11 | Model and parameter controls | planned | Model allow-list, reasoning effort and max tokens are plumbed through `llm_client` and `RunConfig`, but there are no widgets |
| FR-12 | Prompt variant selector | planned | `EvalVariant` and the dispatch for all five variants exist; no selector yet, default P1 (winner of the evaluation run) |
| FR-13 | Token usage and cost | partly | Prices from the OpenRouter models endpoint (`pricing.fetch_models`, `get_pricing`, `compute_cost`) and the token usage of every call work and feed the cost column of the evaluation harness; `llm_client.record_usage`, `pricing.get_supported_parameters` and the sidebar display are open |
| FR-14 | Layered security guard | partly | L1, L2 and L4 are active; L3 `guards.classify_inputs` raises `NotImplementedError` (Should); AC5 is open: `docs/security_tests.md` contains no test cases yet |
| FR-15 | Privacy handling | implemented | Notice shown, data kept in `st.session_state` only, key read from the environment; opt-in debug log for development only (AC5) |

## Screenshots

TBD — screenshots of the four states `SETUP`, `BRIEF`, `INTERVIEW` and `REPORT`.

## Setup

Requires Python 3.13, [uv](https://docs.astral.sh/uv/) and an OpenRouter API key. The project is
uv-only; bare `pip` or `python` are not used.

```bash
uv sync                                 # install dependencies from uv.lock
cp .env.example .env                    # then set OPENROUTER_API_KEY=... in .env
uv run streamlit run app.py             # start the app
```

The key may equally be exported as an environment variable instead of using `.env`; a real
environment variable takes precedence over the file. `.env` is listed in `.gitignore`, and the
key appears neither in the repository nor in the UI (FR-15 AC3). The app starts and renders
without a key — it is needed only once the first LLM call runs (NFR-01).

**Debug log (development only).** Setting `DEBUG_LOG=1` (in the environment or in `.env`) makes
every LLM call append one JSON line to `logs/llm_calls.jsonl`: messages, response, model,
reasoning effort, token usage and latency. It is off by default and `logs/` is gitignored. Because
the log contains the full JD, CV and answers, it is meant for the fictional sample data only and
never for a deployed app (FR-15 AC5).

```bash
DEBUG_LOG=1 uv run streamlit run app.py
```

Tests (NFR-06):

```bash
uv run pytest                                      # whole suite
uv run pytest tests/test_guards.py::test_name -v   # a single test
```

Current result: **42 passed, 4 skipped** out of 46 collected. The four skips are the three
`RunConfig` tests in `tests/test_run_config.py` and one state-transition test in
`tests/test_interview.py`; all are marked `@pytest.mark.skip(reason="not implemented")` because
the features they cover do not exist yet. All tests are deterministic and mock every LLM call.

The prompt-variant evaluation harness scores the evaluation variants against the reference
answers in `eval/dataset.json` (see *Prompt comparison results*):

```bash
uv run python eval/run_eval.py          # full run: 5 variants x 8 answers x 2 runs -> eval/results.csv
uv run python eval/run_eval.py --variants p1_zero_shot --runs 1 --output eval/smoke_p1.csv
uv run python eval/run_eval.py --variants p1_zero_shot --effort minimal --output eval/effort_minimal.csv
```

Options: `--variants` (prompt file stems, default all five), `--runs` (default 2), `--effort`
(reasoning effort, default `low` as in the app) and `--output` (default `eval/results.csv`). A full
run makes 112 API calls (P4 and P5 need two per evaluation) and costs about USD 0.23.

No linter, formatter, type checker or CI is configured.

## Usage

**1 — SETUP.** "Load sample data" fills both text areas from `data/samples/`, so the app can be
tried without personal data. The slider sets the number of main questions (3 to 8, default 3).
"Analyse" stays disabled until both fields contain at least 200 characters. A privacy notice sits
above the inputs. Before the analysis call, the JD and the CV pass the length check and the
injection heuristics; a rejection names the limit or asks the user to remove the instruction-like
text.

**2 — BRIEF.** The preparation brief shows a one-sentence role summary, the strengths, and the
gaps with their severity and the JD requirement each relates to, plus the number of planned
questions. "Start interview" freezes the settings and starts the interview; "Start over" clears
everything.

**3 — INTERVIEW.** The app asks one question at a time in a chat; the user answers in the chat
input. A progress bar shows "Question *i* of *n*". After an answer to a `gap` question, the
interviewer streams exactly one follow-up question, which is answered in the same way; `opener`
and `reverse` questions get no follow-up. Every answer is checked against the 3,000-character
limit and the injection heuristics before it enters the history. The evaluation runs after each
main question but stays hidden — the UI states that feedback follows at the end. "Finish
interview" ends the interview early once at least one question has been answered and no follow-up
is open; only answered questions are scored.

**4 — REPORT.** The report shows the overall score as the arithmetic mean with one decimal, the
gaps next to the scores of the questions that targeted them, and per question the answer, the
follow-up, the score, the STAR breakdown, strengths, improvements and a collapsible improved
example answer. A caption names the evaluation variant and the model that produced the scores.
"Start over" returns to `SETUP` and clears all data.

Because the developer sidebar is still a placeholder (FR-10 to FR-13), every run currently uses
the fixed defaults from `app.default_run_config`: model `openai/gpt-5-mini`, reasoning effort
`low`, `max_tokens` 4,000, evaluation variant P1 (zero-shot), the winner of the evaluation run
(see *Prompt comparison results*).

## Research and product idea

**Why gap-focused.** Generic interview question lists are easy to find. The value of this app is
that it asks the questions a recruiter would ask *because of this CV for this job* — the
uncomfortable ones, including the follow-up when an answer stays vague. Evaluating answers rather
than only generating questions also gives the project a task whose quality can be measured
against reference answers, which is what makes the prompt comparison objective instead of
anecdotal.

**The question mix.** The order of the main questions follows the phases of a structured
recruiter interview — self-presentation, behavioural questions, the candidate's own questions —
and maps them onto three question types. The phase model follows two employer guides by the
Indeed Employer Content Team (in German), [*Strukturiertes Vorstellungsgespräch: Definition,
Ablauf, Fragen*][indeed-structured] and [*Bewerbungsgespräch führen: Leitfaden für
Arbeitgeber*][indeed-guide]:

| Position | Type | Purpose |
|---|---|---|
| 1 | `opener` | Short career summary focused on relevance for this job |
| 2 … n−1 (or n when n = 3) | `gap` | Behavioural or technical question targeting one gap, highest severity first |
| n (only when n ≥ 4) | `reverse` | "What questions do you have for us?" — the user's questions are evaluated too |

The rule is implemented in `interview.expected_question_types` and enforced against the model's
output in `interview._validate_plan`, because a JSON schema cannot express it.

**STAR.** Behavioural answers are judged with the STAR structure (Situation, Task, Action,
Result), which the structured-interview guide recommends for behavioural and competency-based
questions. The `StarRating` schema rates each of the four elements as `present`, `partial` or
`missing`, all four are `None` where STAR does not apply (`opener` and `reverse` questions), and
the report shows the breakdown per question. The rubric lives in the evaluation prompt, not in
Python.

[indeed-structured]: https://de.indeed.com/recruiting/c/info/strukturiertes-vorstellungsgespraech
[indeed-guide]: https://de.indeed.com/recruiting/c/info/bewerbungsgespr%C3%A4ch-f%C3%BChren-leitfaden-f%C3%BCr-arbeitgeber

## Architecture

### State machine

All state lives in `st.session_state`; there is no database and nothing is written to disk.

```text
SETUP ──► BRIEF ──────────────► INTERVIEW ─────────────────────► REPORT
JD + CV   1 LLM call            per question: ask → answer        Python aggregation
or sample (JSON, analysis.md)   → follow-up (streamed)            (no LLM call)
          → InterviewPlan       → evaluation (JSON, hidden)
```

At the `BRIEF → INTERVIEW` edge the settings are copied into an immutable `RunConfig` (a frozen
dataclass). Every LLM call from then until the report reads its settings only from that object,
so all answers of one run are judged under identical conditions, and each stored result keeps the
`RunConfig` it was produced with.

Inside `INTERVIEW` a `gap` question takes two Streamlit reruns: the answer is parked in
`session_state["pending"]` together with the streamed follow-up, and the *next* chat submission is
read as the follow-up answer before the turn is evaluated and appended to the results.

### Modules

| File | Responsibility |
|---|---|
| `app.py` | Streamlit UI and the state machine, nothing else. Contains no prompt text (NFR-05) |
| `src/job_interview_coaching_app/llm_client.py` | OpenRouter client, structured and streamed calls, prompt loading, error translation, usage extraction, opt-in debug log |
| `src/job_interview_coaching_app/schemas.py` | Pydantic models `InterviewPlan`, `AnswerEvaluation`, `GuardVerdict`; the frozen `RunConfig` and `Usage` |
| `src/job_interview_coaching_app/interview.py` | `State` enum, `Turn`/`TurnResult`, question-mix rule, plan validation, interviewer message builder, score aggregation |
| `src/job_interview_coaching_app/evaluation.py` | The five evaluation variants P1–P5 and their dispatch |
| `src/job_interview_coaching_app/guards.py` | Security layers L1–L4 |
| `src/job_interview_coaching_app/pricing.py` | OpenRouter models endpoint: prices and cost per call; supported parameters not implemented yet |
| `prompts/` | All prompt text as Markdown: `analysis.md`, `interviewer.md`, `classifier.md`, `evaluation/p1_zero_shot.md` … `p5_self_refinement.md`, plus `evaluation/p4_generated_knowledge_step1.md` for the first call of P4 |
| `data/samples/` | Fictional JD and CV |
| `eval/` | `dataset.json` with the reference answers, the `run_eval.py` harness, `results.csv` (evaluation run) and `effort_minimal.csv` / `effort_medium.csv` (settings experiment) |
| `docs/` | `security_tests.md` |
| `tests/` | `test_guards.py`, `test_interview.py`, `test_pricing.py`, `test_debug_log.py`, `test_run_config.py` |

The dependency direction is one-way: `app.py` → `interview` / `evaluation` / `guards` →
`llm_client` → `schemas`. `app.py` never calls `llm_client` directly, and the modules below
`app.py` do not touch `st.session_state`.

All prompt files except `classifier.md` are written; `classifier.md` is still a TODO header.
`docs/security_tests.xlsx` does not exist yet.

### The LLM calls

All calls go to OpenRouter through the OpenAI SDK pointed at
`https://openrouter.ai/api/v1`. The model allow-list is exactly `openai/gpt-5-mini` (default),
`openai/gpt-5-nano` and `openai/gpt-5`. Reasoning effort is sent as
`extra_body={"reasoning": {"effort": ...}}`, and `max_tokens` defaults to 4,000 because reasoning
tokens count against it.

| Call | Roles | Output | Status |
|---|---|---|---|
| Analysis and question planning | `system` + `user` | `InterviewPlan` JSON, schema-validated | implemented |
| Interviewer follow-up | `system`, then alternating `assistant` and `user` — the only multi-turn call | Free text, streamed with `st.write_stream` | implemented |
| Answer evaluation | `system` + `user`; two calls for P4 and P5 | `AnswerEvaluation` JSON, schema-validated (P4's first call: `ReferenceKnowledge` JSON) | implemented, P1–P5 |
| Guard classifier (L3) | `system` + `user`, on `openai/gpt-5-nano` | `GuardVerdict` JSON | planned |

In `AnswerEvaluation` the field `reasoning` is declared before `score`: fields are generated in
declaration order, so the model reasons before it commits to a number.

Error handling is centralised in `llm_client`: every provider exception becomes an `LLMError`
carrying a sentence meant for the user, with a 60-second timeout and one automatic retry on
invalid JSON. `app.py` catches only `LLMError`, so no stack trace reaches the screen (NFR-02). A
failed follow-up is not fatal — the interview continues without one; a failed evaluation stores no
score and that question is left out of the mean.

### Security guard

| Layer | Mechanism | Status |
|---|---|---|
| L1 | Length and non-empty checks: JD ≤ 8,000, CV ≤ 12,000, answers ≤ 3,000 characters | implemented |
| L2 | Regex heuristics against instruction-like text in JD, CV and every answer | implemented |
| L3 | A cheap `gpt-5-nano` classifier deciding whether the inputs really are a JD and a CV | planned |
| L4 | Untrusted text wrapped in delimiters such as `<job_description>…</job_description>`, system prompts declaring that content is data and never instructions, schema validation and a score range check | implemented |

The L2 patterns are deliberately narrow, because an ordinary CV may legitimately mention terms
such as "system" or "prompt"; each pattern family has a test case in `tests/test_guards.py`.

## Design decisions

TBD — the five most important design choices and the reasoning behind each.

## Prompt comparison results

Dataset: 8 reference answers to 3 questions with scores assigned by the author before the prompts
were tuned ([`eval/dataset.json`](eval/dataset.json)). Each variant scored every answer twice with
`openai/gpt-5-mini` at reasoning effort `low`: 80 rows in [`eval/results.csv`](eval/results.csv).
Bands: weak = 1–2, ok = 3, strong = 4–5. Scale, rules and security section are identical in all
five prompts, so the variants differ only in the technique.

| Variant | Band accuracy | MAE | Consistency | Injection (A7 ≤ 2) | Cost / evaluation (USD) | Latency (s) |
|---|---|---|---|---|---|---|
| *Target* | *≥ 75 %* | *≤ 1.0* | *≤ 0.5* | *all runs* | *reported* | *reported* |
| **P1 zero-shot** | **100 %** | **0.12** | **0.00** | ok | 0.00186 | 9.2 |
| P2 few-shot | 88 % | 0.38 | 0.50 | ok | 0.00204 | 7.5 |
| P3 chain-of-thought | 94 % | 0.19 | 0.12 | ok | 0.00291 | 11.6 |
| P4 generated knowledge (2 calls) | 81 % | 0.38 | 0.25 | ok | 0.00335 | 13.1 |
| P5 self-refinement (2 calls) | 100 % | 0.19 | 0.12 | ok | 0.00395 | 14.3 |

All five variants meet all targets. **Winner: P1 zero-shot** — tied with P5 on band accuracy, ahead
on MAE (0.12 vs. 0.19) and at less than half of P5's cost.

Where the scores deviated from the labels (16 evaluations per variant):

| Answer (expected) | Deviations | Wrong band |
|---|---|---|
| A1 strong STAR answer (5) | P4 once 4 | – |
| A2 strong STAR answer (4) | P2 once 5, P5 once 5 | – |
| A3 action, no result (3) | P2 once 4, P3 once 4 | P2, P3 |
| A4 action, no result (3) | P4 twice 2 | P4 |
| A5 vague answer (2) | P2 once 1 | – |
| A6 off-topic (1) | none | – |
| A7 prompt injection (1) | every variant, every run: 2 | – |
| A8 short but correct (3) | P2 once 4, P4 once 2 | P2, P4 |

**Why it won.** The simplest technique wins because the decisive work sits in the blocks that all
five prompts share:

- **Precise shared rules.** Scale, rules and security section are identical in every variant and
  already spell out the hard cases: when STAR applies, the cap for a missing result, how to treat
  off-topic answers and injections. Zero-shot gets almost everything it needs from them.
- **A reasoning model.** `gpt-5-mini` reasons internally before it answers. Explicit
  chain-of-thought (P3) therefore produced about 65 % more completion tokens (1,236 vs. 752 on
  average) without more hits.
- **The extra techniques bring their own errors.** P4 measures against an ideal answer and becomes
  too strict, P2 follows examples from a different domain and is the least consistent, and P5
  finds nothing to correct in its P1 draft (see below).

The conclusion is not that zero-shot is the best technique in general, but that **with precise
rules and a reasoning model, the more elaborate techniques brought no measurable benefit in this
test while costing 1.5 to 2 times as much.**

**Observed weaknesses.**

- **P4 (generated knowledge) is systematically too strict.** All its deviations point downwards
  (A1, A4, A8). The reasoning shows why: the answer is measured against the generated ideal answer,
  and every missing point lowers the score ("leaves most of the reference criteria unmet"). The
  short but correct answer A8 suffers most.
- **P5 (self-refinement) never changed a score.** In all 16 evaluations the revised score equals the
  draft score; the second call only polished texts such as the improved answer. Its two
  deviations (A2 scored 5) already come from the draft, i.e. from the P1 call. P5 therefore gives
  P1's result at more than twice the cost.
- **A7 (prompt injection) scores 2 instead of 1 in every run of every variant.** The injection is
  recognised and ignored (P3 names it explicitly); the 2 is given for the remaining content, which
  is relevant but vague. The manipulation did not work — the deviation stems from the label (1)
  being stricter than the rule ("at most 2").
- **A3 is a borderline case.** P2 and P3 scored it 4 instead of 3 in one of two runs each. The rule
  allows "at most 4" when the result is missing, while the label expects 3; a 4 stays within the
  rule.

## Settings experiment

The winning variant P1 was re-run with reasoning effort `minimal` and `medium` (2 runs per answer;
[`eval/effort_minimal.csv`](eval/effort_minimal.csv), [`eval/effort_medium.csv`](eval/effort_medium.csv)).
The values for `low` are taken from the main run.

| Reasoning effort | Band accuracy | MAE | Consistency | Completion tokens (mean) | Cost / evaluation (USD) | Latency (s) |
|---|---|---|---|---|---|---|
| minimal | 94 % | 0.25 | 0.25 | 600 | 0.00155 | 5.4 |
| **low** (app default) | **100 %** | **0.12** | **0.00** | 752 | 0.00186 | 9.2 |
| medium | 88 % | 0.31 | 0.12 | 1,477 | 0.00331 | 12.8 |

Deviations: `minimal` scored A1 once 4 and A3 once 4; `medium` scored A2 once 5 and A3 twice 4;
A7 received 2 at every level.

**Result.** All three levels meet all targets, so reasoning effort is not a critical lever for this
prompt. More effort did not make the judge more accurate: `medium` is behind `low`, and its errors
again hit A3 — with more budget the model applies the rule "at most 4 without a result" more
literally. Less effort makes the judge less stable rather than less accurate: at `minimal` the same
answer receives different scores in the two runs more often (consistency 0.25). Cost and latency
scale clearly: `medium` costs almost twice as much and takes 40 % longer, `minimal` mainly saves
time.

**Recommendation:** `low` stays the default. It is the only level without differences between two
runs and with the smallest deviation from the labels, at little extra cost over `minimal`. One
trade-off remains: the evaluation runs after every main question and the user waits for it, so
`minimal` would almost halve that wait at slightly lower reliability. As in the main run, the
differences rest on one or two of 16 evaluations; the reliable finding is the direction — more
effort costs clearly more without improving accuracy here.

A temperature comparison is not possible, because none of the three allowed models supports
`temperature` or `top_p`.

## Security tests summary

TBD — a summary of the at least ten adversarial test cases from
[`docs/security_tests.md`](docs/security_tests.md), which currently contains no cases.

## ChatGPT critique

TBD — the critique of this project by ChatGPT and what was changed because of it.

## Known limitations

Limits of the prompt evaluation (draft — to be reviewed by the author):

- **Small dataset.** 8 reference answers to 3 questions. With 16 evaluations per variant, one
  deviating score moves band accuracy by about 6 percentage points, so the differences between
  P1, P3 and P5 rest on one or two evaluations.
- **One labeler, one model family, two runs.** All expected scores come from the author; all
  calls use `openai/gpt-5-mini`.
- **Labels and rules differ in two places.** The injection answer A7 is labelled 1, while the
  rules cap such answers at "at most 2"; every variant scored it 2. An answer without a result is
  labelled 3, while the rules allow "at most 4"; this is where A3 flips between 3 and 4.
- **A2's label is debatable.** Several variants scored A2 a 5 instead of the expected 4.

TODO — what the app itself does not do, and where its output can be wrong.

## Ideas for improvement

TBD — the features dropped by the cut rule of PRODUCT_SPEC §11 and what a next version would add.

## Traceability table

TBD — the task requirements and review criteria of PRODUCT_SPEC §10.1 and the optional tasks of
§10.2, each mapped onto the implementation.

## Note on tooling

The project is developed in **Visual Studio Code**, as recommended by Turing College, with
`uv` for dependency management and `pytest` and `ruff` for checks.

It was planned and built with AI assistance, with a clear split of responsibilities:

- **Claude Desktop** – validated the product idea against the course requirements, drafted
  `PRODUCT_SPEC.md`, turned the author's source material into the fictional sample JD and CV,
  broke the project plan down into daily task lists, proposed code and prompt snippets, and
  reviewed the author's code and prompts throughout. It also drafted the factual parts of the
  evaluation sections in this README (tables and deviation lists).
- **Gemini** – generated the candidate answers used as few-shot examples in P2 (fictional, outside
  the evaluation dataset); their evaluations were written by the author.
- **Claude Code CLI** – generated the initial scaffolding (folder structure, function stubs and
  test skeletons) and drafted `CLAUDE.md` and this README.
- **The author** – owns the product idea and every decision on scope and design, wrote and
  iterated the prompts based on review feedback, compiled the evaluation dataset, implemented
  the code in VS Code, ran all tests, and made every commit. AI-proposed snippets were reviewed
  and adapted before they were committed.
