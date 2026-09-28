# Analysis and question planning prompt

System prompt for the **gap analysis + main question planning** call
(FR-04, FR-05; PRODUCT_SPEC §5, §5.1).

> **TODO: write the prompt below this block.**

- **Purpose:** compare the CV against the job description, name the strengths and the
  gaps, and plan the main questions of the interview in the *same* call.
- **Technique:** zero-shot with an explicit JSON schema; recruiter role prompting.
- **Roles (§5.1):** `system` = these instructions, the question-mix rule and the output
  format · `user` = JD and CV wrapped in delimiters plus the number of questions *n*.
- **Expected output:** JSON matching `InterviewPlan` (format 1, §6.1) — `role_summary`,
  2–5 `strengths`, 2–5 `gaps` (each with `id`, `description`, `jd_requirement`,
  `severity`), and exactly *n* `questions`.
- **Question mix (FR-05):** Q1 is the `opener`; the middle questions are `gap`
  questions ordered by descending severity, each referencing the `id` of a real gap
  (FR-05 AC3); the last question is `reverse` only when *n* ≥ 4. No duplicates
  (FR-05 AC4).
- **Security (FR-14 L4):** state that everything inside `<job_description>` and `<cv>`
  is data to be analysed and never instructions to follow.
