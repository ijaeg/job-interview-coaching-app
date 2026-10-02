# P2 — Few-shot evaluation prompt

Answer-evaluation variant P2 (FR-08, FR-12; PRODUCT_SPEC §5.2).

> **TODO: write the prompt below this block.**

- **Technique:** few-shot. P1 plus three graded example answers (score 1, 3 and 5)
  with their evaluations.
- **Calls:** 1.
- **Core idea:** anchor the scale with worked examples so the scores drift less.
- **No leakage (§5.2 AC2):** the examples must **not** come from
  `eval/dataset.json`; write fresh ones.
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
