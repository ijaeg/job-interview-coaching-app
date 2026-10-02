"""CLI harness for the prompt-variant evaluation (PRODUCT_SPEC §7.2).

Runs every evaluation variant P1-P5 over every reference answer in
``eval/dataset.json`` twice with fixed settings and writes one row per run to
``eval/results.csv``: 5 variants x 8 answers x 2 runs = 80 rows (§7.4 AC1).

Metrics per variant (§7.2): band accuracy (target >= 75 %), mean absolute error
(<= 1.0), consistency between the two runs (<= 0.5), injection resistance
(case 7 scores <= 2) and mean cost and latency, with both calls counted for the
two-step variants P4 and P5 (§5.2 AC3).

Winner rule: highest band accuracy, ties broken by lower MAE, then lower cost. The
winner becomes the default of the FR-12 selector.

This script is part of the *Must* scope and is never dropped by the §11 cut rule.

Usage:
    uv run python eval/run_eval.py
    uv run python eval/run_eval.py --variants p1_zero_shot p3_chain_of_thought --runs 2
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

from job_interview_coaching_app.evaluation import EvalVariant, evaluate_answer
from job_interview_coaching_app.llm_client import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    LLMError,
)
from job_interview_coaching_app.pricing import ModelPricing, compute_cost, get_pricing
from job_interview_coaching_app.schemas import Gap, Question, RunConfig

DATASET_PATH = Path(__file__).resolve().parent / "dataset.json"
RESULTS_PATH = Path(__file__).resolve().parent / "results.csv"

#: Score bands used to compare a prediction with the human label (§7.1).
BANDS: dict[str, tuple[int, int]] = {"weak": (1, 2), "ok": (3, 3), "strong": (4, 5)}

#: Reference answer containing the prompt injection; must score <= 2 in every run (§7.2).
INJECTION_ANSWER_ID: str = "A7"

#: Columns of ``results.csv``, one row per variant, reference answer and run.
CSV_FIELDS: list[str] = [
    "variant",
    "answer_id",
    "run",
    "expected_score",
    "expected_band",
    "score",
    "band",
    "relevant",
    "prompt_tokens",
    "completion_tokens",
    "cost_usd",
    "latency_s",
    "error",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command-line arguments.

    Args:
        argv: Argument list; ``None`` uses ``sys.argv``.

    Returns:
        The parsed arguments with ``variants`` and ``runs``.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--variants",
        nargs="+",
        default=None,
        help="Variants to run, by prompt file stem (default: all five, P1-P5).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="Runs per variant and reference answer (default: 2, per §7.2).",
    )
    parser.add_argument(
        "--effort",
        default="low",
        choices=["minimal", "low", "medium", "high"],
        help="Reasoning effort for every call (default: low, as in the app; §7.3 varies it).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_PATH,
        help="CSV file to write (default: eval/results.csv).",
    )
    return parser.parse_args(argv)


def band_of(score: int) -> str:
    """Map a 1-5 score onto its band.

    Args:
        score: The predicted or expected score.

    Returns:
        ``"weak"``, ``"ok"`` or ``"strong"`` (§7.1).

    Raises:
        ValueError: If the score is outside 1-5.
    """
    for band, (low, high) in BANDS.items():
        if low <= score <= high:
            return band
    raise ValueError(f"score must be between 1 and 5, got {score}")


def load_dataset(
    path: Path = DATASET_PATH,
) -> tuple[dict[str, Question], dict[str, Gap], list[dict]]:
    """Load questions, gaps and reference answers from ``eval/dataset.json`` (§7.1).

    Args:
        path: Location of the dataset file.

    Returns:
        Questions and gaps keyed by id, and the list of reference answers.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = {item["id"]: Question(**item) for item in data["questions"]}
    gaps = {item["id"]: Gap(**item) for item in data["gaps"]}
    return questions, gaps, data["reference_answers"]


def run_once(
    reference: dict,
    run: int,
    questions: dict[str, Question],
    gaps: dict[str, Gap],
    run_config: RunConfig,
    pricing: ModelPricing | None,
) -> dict:
    """Evaluate one reference answer once and return its ``results.csv`` row.

    An ``LLMError`` does not stop the whole evaluation; it is recorded in the
    ``error`` column and the row is left out of the metrics.

    Args:
        reference: One entry of ``reference_answers`` from the dataset.
        run: Run number, starting at 1.
        questions: Dataset questions keyed by id.
        gaps: Dataset gaps keyed by id.
        run_config: Settings of this evaluation run, including the variant.
        pricing: Prices of the model, or ``None`` when unavailable.

    Returns:
        One row with all ``CSV_FIELDS``.
    """
    question = questions[reference["question_id"]]
    gap = gaps.get(question.gap_id) if question.gap_id else None
    row = dict.fromkeys(CSV_FIELDS, "")
    row.update(
        variant=run_config.eval_variant,
        answer_id=reference["id"],
        run=run,
        expected_score=reference["expected_score"],
        expected_band=band_of(reference["expected_score"]),
    )
    started = time.perf_counter()
    try:
        evaluation, usages = evaluate_answer(
            question, reference["answer"], None, None, run_config, gap
        )
    except LLMError as err:
        row.update(error=str(err), latency_s=round(time.perf_counter() - started, 2))
        return row
    costs = [compute_cost(usage, pricing) for usage in usages]
    row.update(
        score=evaluation.score,
        band=band_of(evaluation.score),
        relevant=evaluation.relevant,
        prompt_tokens=sum(usage.prompt_tokens for usage in usages),
        completion_tokens=sum(usage.completion_tokens for usage in usages),
        cost_usd="" if None in costs else round(sum(costs), 6),
        latency_s=round(time.perf_counter() - started, 2),
    )
    return row


def summarize(rows: list[dict]) -> list[dict]:
    """Compute the §7.2 metrics per variant, best variant first.

    Args:
        rows: All result rows; rows with an error are left out of the metrics.

    Returns:
        One dict per variant with band accuracy, MAE, consistency, injection
        resistance, mean cost and latency and the number of errors, sorted by the
        winner rule: band accuracy, then MAE, then cost.
    """
    by_variant: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_variant[row["variant"]].append(row)
    summary = []
    for variant, variant_rows in by_variant.items():
        scored = [row for row in variant_rows if not row["error"]]
        scores_per_answer: dict[str, list[int]] = defaultdict(list)
        for row in scored:
            scores_per_answer[row["answer_id"]].append(row["score"])
        spreads = [
            max(scores) - min(scores) for scores in scores_per_answer.values() if len(scores) > 1
        ]
        costs = [row["cost_usd"] for row in scored if row["cost_usd"] != ""]
        injection_scores = [
            row["score"] for row in scored if row["answer_id"] == INJECTION_ANSWER_ID
        ]
        summary.append(
            {
                "variant": variant,
                "band_accuracy": mean(row["band"] == row["expected_band"] for row in scored)
                if scored
                else None,
                "mae": mean(abs(row["score"] - row["expected_score"]) for row in scored)
                if scored
                else None,
                "consistency": mean(spreads) if spreads else None,
                "injection_resistant": (
                    all(score <= 2 for score in injection_scores) if injection_scores else None
                ),
                "mean_cost_usd": mean(costs) if costs else None,
                "mean_latency_s": mean(row["latency_s"] for row in scored) if scored else None,
                "errors": len(variant_rows) - len(scored),
            }
        )
    return sorted(
        summary,
        key=lambda item: (
            -(item["band_accuracy"] or 0),
            item["mae"] if item["mae"] is not None else float("inf"),
            item["mean_cost_usd"] if item["mean_cost_usd"] is not None else float("inf"),
        ),
    )


def print_summary(summary: list[dict]) -> None:
    """Print the metric table of §7.2 and name the winner."""

    def fmt(value: float | None, pattern: str) -> str:
        return "n/a" if value is None else format(value, pattern)

    print(
        f"{'variant':<24}{'band acc':>9}{'MAE':>7}{'consist.':>9}{'inject.':>8}{'cost $':>10}{'lat. s':>8}{'errors':>7}"
    )
    for item in summary:
        print(
            f"{item['variant']:<24}{fmt(item['band_accuracy'], '.0%'):>9}{fmt(item['mae'], '.2f'):>7}"
            f"{fmt(item['consistency'], '.2f'):>9}{ {True: 'ok', False: 'FAIL', None: 'n/a'}[item['injection_resistant']]:>8}"
            f"{fmt(item['mean_cost_usd'], '.5f'):>10}{fmt(item['mean_latency_s'], '.1f'):>8}{item['errors']:>7}"
        )
    if summary and summary[0]["band_accuracy"] is not None:
        print(f"\nWinner: {summary[0]['variant']}")


def main(argv: list[str] | None = None) -> None:
    """Run the evaluation and write ``eval/results.csv``.

    Loads the dataset, runs each selected variant over each reference answer the
    requested number of times, records score, band, cost and latency per run, prints
    the metric table of §7.2 and names the winner.

    Args:
        argv: Argument list; ``None`` uses ``sys.argv``.
    """
    args = parse_args(argv)
    variants = [EvalVariant(name) for name in args.variants] if args.variants else list(EvalVariant)
    questions, gaps, references = load_dataset()
    pricing = get_pricing(DEFAULT_MODEL)
    if pricing is None:
        print("Prices unavailable - the cost column stays empty.")
    rows = []
    for variant in variants:
        run_config = RunConfig(
            model=DEFAULT_MODEL,
            reasoning_effort=args.effort,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=None,
            top_p=None,
            eval_variant=variant.value,
        )
        for reference in references:
            for run in range(1, args.runs + 1):
                row = run_once(reference, run, questions, gaps, run_config, pricing)
                rows.append(row)
                print(
                    f"{variant.value} {reference['id']} run {run}: score={row['score'] or '-'} {row['error']}"
                )
    with args.output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} rows written to {args.output}\n")
    print_summary(summarize(rows))


if __name__ == "__main__":
    main()
