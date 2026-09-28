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
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parent / "dataset.json"
RESULTS_PATH = Path(__file__).resolve().parent / "results.csv"

#: Score bands used to compare a prediction with the human label (§7.1).
BANDS: dict[str, tuple[int, int]] = {"weak": (1, 2), "ok": (3, 3), "strong": (4, 5)}


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
    raise NotImplementedError


def main(argv: list[str] | None = None) -> None:
    """Run the evaluation and write ``eval/results.csv``.

    Loads the dataset, runs each selected variant over each reference answer the
    requested number of times, records score, band, cost and latency per run, prints
    the metric table of §7.2 and names the winner.

    Args:
        argv: Argument list; ``None`` uses ``sys.argv``.
    """
    parse_args(argv)
    raise NotImplementedError


if __name__ == "__main__":
    main()
