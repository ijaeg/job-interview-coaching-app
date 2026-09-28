"""Streamlit UI and state machine of the Gap-Focused Interview Coach.

This file owns the user interface and the ``SETUP -> BRIEF -> INTERVIEW -> REPORT``
transitions (§3) and nothing else. It contains **no prompt text** (NFR-05): prompts
live in ``prompts/``, LLM access in ``llm_client``, deterministic interview logic in
``interview``, judging in ``evaluation``, security in ``guards`` and prices in
``pricing``.

Nothing here touches the network at import time, so the app starts and renders even
without ``OPENROUTER_API_KEY`` (NFR-01); the key is only needed once an LLM call
runs. Every non-streamed call is wrapped in ``st.spinner`` (NFR-04).

Related: FR-01 ... FR-15, NFR-01, NFR-04, NFR-05, NFR-08.
"""

from __future__ import annotations

import streamlit as st

from job_interview_coaching_app.interview import DEFAULT_QUESTIONS, State

PAGE_TITLE = "Gap-Focused Interview Coach"


def init_session_state() -> None:
    """Create the session-state keys on the first run.

    All user data - JD, CV, answers, plan, evaluations - lives here and only here:
    nothing is written to disk and nothing is logged (FR-15 AC2).

    TODO: initialise state, jd, cv, n_questions, plan, turns, evaluations,
    run_config and the usage totals.
    """
    if "state" not in st.session_state:
        st.session_state["state"] = State.SETUP


def render_sidebar() -> None:
    """Render the collapsible "Developer settings" section.

    Holds every LLM control so that the main page stays free of LLM terminology and
    works on defaults (FR-10 AC1, AC2): model selector (FR-11 AC1), reasoning effort
    and max tokens (FR-11 AC2), sampling parameters enabled only when the model
    lists them in ``supported_parameters`` (FR-11 AC3), the P1-P5 variant selector
    (FR-12) and the read-only token/cost total (FR-13).

    During ``INTERVIEW`` and ``REPORT`` the controls are ``disabled=True`` and the
    lock notice is shown, while the cost display stays active (FR-10 AC4).

    TODO: build the widgets and the disabled/locked behaviour.
    """
    with st.sidebar:
        st.header("Developer settings")
        st.caption("TODO: FR-10 controls, FR-11 model and parameters, FR-12 variant, FR-13 cost.")


def freeze_run_config() -> None:
    """Copy the sidebar settings into an immutable ``RunConfig``.

    Runs exactly once, at the ``BRIEF -> INTERVIEW`` transition. From then on every
    LLM call reads its settings only from this frozen dataclass in
    ``st.session_state``, never from the widgets (FR-10 AC3), and each stored
    ``AnswerEvaluation`` keeps the config it was produced with (FR-10 AC5).

    TODO: build the RunConfig from the widget values and store it.
    """
    raise NotImplementedError


def render_setup() -> None:
    """SETUP: collect the job description and the CV.

    Two text areas (FR-01 AC1), the "Analyse" button disabled below 200 characters
    (FR-01 AC2), length limits enforced by ``guards.check_length`` (FR-01 AC3), the
    "Load sample data" button (FR-02 AC1), the question-count slider 3-8 with the
    English-language note (FR-03), and the privacy notice (FR-15 AC1). L2 injection
    heuristics and the optional L3 classifier run before the analysis
    (FR-14 AC1, AC2).

    TODO: implement the inputs and the transition to BRIEF.
    """
    st.info("TODO - SETUP: FR-01 inputs, FR-02 sample data, FR-03 slider, FR-14 guard, FR-15 notice.")


def render_brief() -> None:
    """BRIEF: show the preparation brief produced by the analysis call.

    One-sentence role summary, 2-5 strengths and 2-5 gaps with severity and the JD
    requirement each relates to (FR-04 AC1, AC2), plus the planned main questions
    (FR-05). "Start interview" freezes the settings and moves to ``INTERVIEW``
    (FR-10 AC3).

    TODO: render the InterviewPlan and the transition to INTERVIEW.
    """
    st.info("TODO - BRIEF: FR-04 gap analysis, FR-05 planned questions, FR-10 AC3 config freeze.")


def render_interview() -> None:
    """INTERVIEW: run the mock interview as a chat.

    One question at a time with ``st.chat_message`` and ``st.chat_input``, history
    surviving reruns (FR-06 AC1), a "Question i of n" progress indicator
    (FR-06 AC2), empty and over-long answers rejected (FR-06 AC3) and an early
    "Finish interview" (FR-06 AC4). After each ``gap`` answer the interviewer LLM
    streams exactly one follow-up (FR-07); ``opener`` and ``reverse`` get none
    (FR-07 AC4). Each main question is evaluated before the next appears, hidden
    until the report (FR-08 AC1).

    TODO: implement the chat loop and the transition to REPORT.
    """
    st.info("TODO - INTERVIEW: FR-06 chat, FR-07 streamed follow-up, FR-08 hidden evaluation.")


def render_report() -> None:
    """REPORT: show the scored feedback report.

    Overall score as the Python-computed mean with one decimal (FR-09 AC1), per
    question the answers, score, STAR breakdown, strengths, improvements and the
    collapsible improved answer (FR-09 AC2), the gaps next to the scores of the
    questions that targeted them (FR-09 AC3), and which variant and model produced
    the evaluations (FR-09 AC4, FR-10 AC5). "Start over" returns to ``SETUP`` and
    clears all data (§3).

    TODO: render the aggregation and the per-question details.
    """
    st.info("TODO - REPORT: FR-09 scores and details, FR-10 AC5 RunConfig provenance.")


#: State machine dispatch table (§3).
RENDERERS = {
    State.SETUP: render_setup,
    State.BRIEF: render_brief,
    State.INTERVIEW: render_interview,
    State.REPORT: render_report,
}


def main() -> None:
    """Configure the page and dispatch to the renderer of the current state."""
    st.set_page_config(page_title=PAGE_TITLE, layout="centered")
    init_session_state()
    st.title(PAGE_TITLE)
    st.caption(f"The interview is conducted in English. Default: {DEFAULT_QUESTIONS} questions.")
    render_sidebar()
    RENDERERS[st.session_state["state"]]()


main()
