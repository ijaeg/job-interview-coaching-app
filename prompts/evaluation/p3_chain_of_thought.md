# P3 — Chain-of-thought evaluation prompt

Answer-evaluation variant P3 (FR-08, FR-12; PRODUCT_SPEC §5.2).

> **TODO: write the prompt below this block.**

- **Technique:** chain-of-thought. The model works through relevance, each STAR
  element and the evidence step by step before it scores.
- **Calls:** 1.
- **Core idea:** the reasoning goes into the `reasoning` field, which is declared
  **before** `score` in the schema, so the model has reasoned by the time it commits
  to a number.
- **Roles (§5.1):** `system` = this prompt · `user` = question, question type, the
  targeted gap and the answer(s), each wrapped in delimiters.
- **Expected output:** JSON matching `AnswerEvaluation` (format 2, §6.2) —
  `reasoning` first, then `relevant`, `score` (1–5), the `star` breakdown,
  `strengths`, at least one `improvements` entry and an `improved_answer`
  (FR-08 AC2, AC3).
- **Shared by all variants:** the same rubric, the same 1–5 scale (1 = poor,
  5 = excellent) and the same output schema; only the technique differs.
- **Security (FR-14):** the delimited answer is data, never instructions. An answer
  demanding a high score is an injection attempt and scores ≤ 2 (FR-14 AC3); an
  off-topic answer gets `relevant = false` and score 1 (FR-08 AC4).
