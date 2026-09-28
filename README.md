# Gap-Focused Interview Coach

> **Status: scaffold.** Every section below is a stub. The authoritative design is
> [`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) (v0.2.2); this README must eventually carry all
> sections listed in §10.2 (NFR-07).

## Purpose

TODO: what the app does — paste a job description and a CV, get the gaps, practise a
mock interview targeting them, receive a scored report.

## Screenshots

TODO: screenshots of the four states SETUP, BRIEF, INTERVIEW and REPORT.

## Setup

Requires Python 3.13, [uv](https://docs.astral.sh/uv/) and an OpenRouter API key.

```bash
uv sync
cp .env.example .env          # then fill in OPENROUTER_API_KEY
uv run streamlit run app.py
```

Other commands:

```bash
uv run pytest                 # unit tests (NFR-06)
uv run python eval/run_eval.py   # prompt-variant evaluation (§7.2)
```

The key is read from `OPENROUTER_API_KEY` in the environment or a gitignored `.env`;
it never appears in the repository or the UI (FR-15 AC3).

## Usage

TODO: the walkthrough — load sample data, set the number of questions, read the
brief, answer the questions, read the report.

## Research and product idea

TODO: why gap-focused rather than a generic question list; the recruiter guideline
behind the question mix; the STAR method (task requirement 1).

## Architecture

TODO: the module map of §9 and the `SETUP → BRIEF → INTERVIEW → REPORT` state machine;
the four LLM call types and their roles and output types (§5.1).

## Design decisions

TODO: the five most important choices and why.

## Prompt comparison results

TODO: the results table for all §7.2 metrics, the winner, **why** the winning
technique performed best, and at least one observed weakness (§7.4 AC2). Plus the
limits of the method: small dataset, one human labeler, one model family (§7.4 AC3).

## Settings experiment

TODO: reasoning effort `minimal` vs `medium` on the winning variant; `temperature`
0.2 vs 1.0 for the follow-ups if the model supports it (§7.3).

## Security tests summary

TODO: summary of [`docs/security_tests.md`](docs/security_tests.md) — the four layers
and what the ≥ 10 adversarial cases showed (FR-14 AC5).

## ChatGPT critique

TODO: the critique of this project by ChatGPT and what was changed because of it
(optional task Easy 1).

## Known limitations

TODO: what the app does not do and where it can be wrong.

## Ideas for improvement

TODO: what was cut by the §11 cut rule and what a next version would add.

## Traceability

TODO: the task requirements and review criteria mapped onto the implementation
(§10.1), and the optional tasks claimed (§10.2).

## Note on tooling

TODO: developed in IntelliJ IDEA rather than VS Code / Cursor, and why.
