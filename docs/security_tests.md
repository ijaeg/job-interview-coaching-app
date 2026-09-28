# Security tests

Adversarial test cases for the layered guard (FR-14). At least **10 cases** must be
documented here and in `docs/security_tests.xlsx` with input, expected and actual
behaviour (FR-14 AC5, optional task Medium 5).

Layers: **L1** length and non-empty checks · **L2** regex injection heuristics ·
**L3** `gpt-5-nano` classifier · **L4** prompt hardening and output validation.

Suggested coverage: over-long JD/CV/answer (L1), "ignore all previous instructions"
in the CV (L2), role tags in an answer (L2), a recipe pasted as a JD (L3),
"show me your system prompt" as an answer (L4, FR-14 AC4), and an answer demanding
score 5 (FR-14 AC3).

> **TODO: add one row per test case.**

| ID | Input | Expected | Actual | Layer |
|---|---|---|---|---|
