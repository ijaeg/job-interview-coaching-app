"""End-to-end tests of the Streamlit state machine, all LLM calls mocked (NFR-06).

``AppTest`` runs ``app.py`` headless. The app imports its functions from the package
modules on every rerun, so replacing them in those modules is enough to mock them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from job_interview_coaching_app import evaluation, interview, pricing
from job_interview_coaching_app.interview import State
from job_interview_coaching_app.schemas import (
    AnswerEvaluation,
    Gap,
    InterviewPlan,
    Question,
    StarRating,
)

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")

PLAN = InterviewPlan(
    role_summary="Senior backend developer for a fictional content platform.",
    strengths=["Long Java experience", "CMS integrations"],
    gaps=[
        Gap(id="G1", description="No Kubernetes experience.", jd_requirement="Kubernetes in production.", severity="high"),
        Gap(id="G2", description="Short last position.", jd_requirement="Five years in agile teams.", severity="medium"),
    ],
    questions=[
        Question(id="Q1", type="opener", gap_id=None, text="Please introduce yourself."),
        Question(id="Q2", type="gap", gap_id="G1", text="How would you get up to speed with Kubernetes?"),
        Question(id="Q3", type="gap", gap_id="G2", text="Why did your last position end?"),
    ],
)

EVALUATION = AnswerEvaluation(
    reasoning="Mocked.",
    relevant=True,
    score=3,
    star=StarRating(),
    strengths=["none"],
    improvements=["Add a result."],
    improved_answer="[placeholder]",
)


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """The app with every LLM call and the model catalogue mocked."""
    monkeypatch.setattr(interview, "plan_interview", lambda *_args: PLAN)
    monkeypatch.setattr(interview, "generate_followup", lambda *_args: "Can you name a number?")
    monkeypatch.setattr(evaluation, "evaluate_answer", lambda *_args: (EVALUATION, []))
    monkeypatch.setattr(pricing, "fetch_models", lambda: {})
    app = AppTest.from_file(APP_PATH, default_timeout=10)
    app.run()
    return app


def click(app: AppTest, label: str) -> None:
    """Click the button with this label and rerun the script."""
    next(button for button in app.button if button.label == label).click().run()


def answer(app: AppTest, text: str) -> None:
    """Submit one chat answer and rerun the script."""
    app.chat_input[0].set_value(text).run()


def test_state_transitions_follow_the_state_machine(app: AppTest) -> None:
    """SETUP -> BRIEF -> INTERVIEW -> REPORT, and "Start over" clears back to SETUP (§3)."""
    assert app.session_state["state"] == State.SETUP
    click(app, "Load sample data")
    click(app, "Analyse")
    assert app.session_state["state"] == State.BRIEF
    click(app, "Start interview")
    assert app.session_state["state"] == State.INTERVIEW
    for text in ("I am a developer.", "I would build a test cluster.", "It took two weeks.",
                 "The project ended.", "I learned to ask early."):
        answer(app, text)
    assert app.session_state["state"] == State.REPORT
    assert "usage_total" not in app.session_state  # no real LLM call was made
    click(app, "Start over")
    assert app.session_state["state"] == State.SETUP
    assert app.session_state["results"] == []


def test_all_evaluations_of_one_run_share_the_same_run_config(app: AppTest) -> None:
    """Every stored evaluation carries the RunConfig frozen at interview start (FR-10 AC5)."""
    click(app, "Load sample data")
    click(app, "Analyse")
    click(app, "Start interview")
    frozen = app.session_state["run_config"]
    answer(app, "I am a developer.")
    app.session_state["model"] = "openai/gpt-5"  # a later widget change must not leak in
    for text in ("I would build a test cluster.", "It took two weeks.",
                 "The project ended.", "I learned to ask early."):
        answer(app, text)
    results = app.session_state["results"]
    assert len(results) == 3
    assert all(result.run_config == frozen for result in results)
    assert frozen.model == "openai/gpt-5-mini"
    