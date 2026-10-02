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

from dataclasses import replace
from pathlib import Path

import streamlit as st

from job_interview_coaching_app.evaluation import DEFAULT_VARIANT, evaluate_answer
from job_interview_coaching_app.guards import (
    MAX_ANSWER_CHARS,
    MAX_CV_CHARS,
    MAX_JD_CHARS,
    MIN_INPUT_CHARS,
    check_length,
    detect_injection,
)
from job_interview_coaching_app.interview import (
    DEFAULT_QUESTIONS,
    MAX_QUESTIONS,
    MIN_QUESTIONS,
    State,
    Turn,
    TurnResult,
    aggregate_scores,
    build_interviewer_messages,
    generate_followup,
    plan_interview,
)
from job_interview_coaching_app.llm_client import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    LLMError,
)
from job_interview_coaching_app.schemas import InterviewPlan, Question, RunConfig

PAGE_TITLE = "Gap-Focused Interview Coach"

#: Fictional sample data behind the "Load sample data" button (FR-02).
SAMPLES_DIR = Path(__file__).resolve().parent / "data" / "samples"

#: Privacy notice shown above the inputs, verbatim (FR-15 AC1).
PRIVACY_NOTICE = (
    "Your texts are sent to an LLM provider via OpenRouter for processing. "
    "They are not stored by this app."
)


def init_session_state() -> None:
    """Create the session-state keys on the first run.

    All user data - JD, CV, answers, plan, evaluations - lives here and only here:
    nothing is written to disk and nothing is logged (FR-15 AC2).
    """
    defaults = {
        "state": State.SETUP,
        "jd": "",
        "cv": "",
        "n_questions": DEFAULT_QUESTIONS,
        "plan": None,
        "run_config": None,
        "q_index": 0,
        "pending": None,
        "results": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def default_run_config() -> RunConfig:
    """Provisional settings until the developer sidebar exists (FR-10 to FR-12 follow later)."""
    return RunConfig(
        model=DEFAULT_MODEL,
        reasoning_effort="low",
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=None,
        top_p=None,
        eval_variant=DEFAULT_VARIANT.value,
    )


def load_sample_data() -> None:
    """Fill both text areas with the fictional sample files (FR-02 AC1).

    Runs as an ``on_click`` callback, i.e. before the text areas are drawn again;
    setting a widget's value after the widget exists raises a StreamlitAPIException.
    """
    st.session_state["jd"] = (SAMPLES_DIR / "sample_job_description.md").read_text(encoding="utf-8")
    st.session_state["cv"] = (SAMPLES_DIR / "sample_cv.md").read_text(encoding="utf-8")


def start_over() -> None:
    """Clear all session data and return to SETUP (§3)."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def go_to(state: State) -> None:
    """Switch the state machine to ``state`` (used as a button callback)."""
    st.session_state["state"] = state


def run_analysis(jd: str, cv: str) -> None:
    """Run guard L1/L2, then the analysis call, then switch to BRIEF (FR-01, FR-04, FR-05, FR-14)."""
    for text, limit, label in ((jd, MAX_JD_CHARS, "Job description"), (cv, MAX_CV_CHARS, "Your CV")):
        for result in (check_length(text, limit, label), detect_injection(text)):
            if not result.ok:
                st.error(result.message)
                return
    try:
        with st.spinner("Analysing your CV against the job description ..."):
            plan = plan_interview(jd, cv, st.session_state["n_questions"], default_run_config())
    except LLMError as err:
        st.error(str(err))
        return
    st.session_state["plan"] = plan
    st.session_state["state"] = State.BRIEF
    st.rerun()


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
    """
    st.session_state["run_config"] = default_run_config()


def start_interview() -> None:
    """BRIEF -> INTERVIEW: freeze the settings first, then switch state (FR-10 AC3)."""
    freeze_run_config()
    st.session_state["state"] = State.INTERVIEW


def render_setup() -> None:
    """SETUP: collect the job description and the CV.

    Two text areas (FR-01 AC1), the "Analyse" button disabled below 200 characters
    (FR-01 AC2), length limits enforced by ``guards.check_length`` (FR-01 AC3), the
    "Load sample data" button (FR-02 AC1), the question-count slider 3-8 with the
    English-language note (FR-03), and the privacy notice (FR-15 AC1). L2 injection
    heuristics and the optional L3 classifier run before the analysis
    (FR-14 AC1, AC2).
    """
    st.info(PRIVACY_NOTICE)
    st.button("Load sample data", on_click=load_sample_data)
    jd = st.text_area("Job description", key="jd", height=250)
    cv = st.text_area("Your CV", key="cv", height=250)
    st.slider("Number of questions", MIN_QUESTIONS, MAX_QUESTIONS, key="n_questions")
    too_short = len(jd.strip()) < MIN_INPUT_CHARS or len(cv.strip()) < MIN_INPUT_CHARS
    if st.button("Analyse", type="primary", disabled=too_short):
        run_analysis(jd, cv)


def render_brief() -> None:
    """BRIEF: show the preparation brief produced by the analysis call.

    One-sentence role summary, 2-5 strengths and 2-5 gaps with severity and the JD
    requirement each relates to (FR-04 AC1, AC2), plus the planned main questions
    (FR-05). "Start interview" freezes the settings and moves to ``INTERVIEW``
    (FR-10 AC3).
    """
    plan = st.session_state["plan"]
    st.subheader("Your preparation brief")
    st.write(plan.role_summary)
    st.markdown("**Strengths**")
    for strength in plan.strengths:
        st.markdown(f"- {strength}")
    st.markdown("**Gaps a recruiter is likely to ask about**")
    for gap in plan.gaps:
        st.markdown(f"- **{gap.severity.upper()}**: {gap.description}  \n  _Requirement: {gap.jd_requirement}_")
    st.caption(f"Your interview has {len(plan.questions)} questions.")
    left, right = st.columns(2)
    left.button("Start interview", type="primary", on_click=start_interview)
    right.button("Start over", on_click=start_over)


def render_interview() -> None:
    """INTERVIEW: run the mock interview as a chat.

    One question at a time with ``st.chat_message`` and ``st.chat_input``, history
    surviving reruns (FR-06 AC1), a "Question i of n" progress indicator
    (FR-06 AC2), empty and over-long answers rejected (FR-06 AC3) and an early
    "Finish interview" (FR-06 AC4). After each ``gap`` answer the interviewer LLM
    streams exactly one follow-up (FR-07); ``opener`` and ``reverse`` get none
    (FR-07 AC4). Each main question is evaluated before the next appears, hidden
    until the report (FR-08 AC1).
    """
    plan = st.session_state["plan"]
    q_index = st.session_state["q_index"]
    pending = st.session_state["pending"]
    question = plan.questions[q_index]

    st.progress(q_index / len(plan.questions), text=f"Question {q_index + 1} of {len(plan.questions)}")
    st.caption("Feedback will be shown at the end.")
    st.button(
        "Finish interview",
        on_click=go_to,
        args=(State.REPORT,),
        disabled=not st.session_state["results"] or pending is not None,
    )
    notice = st.session_state.pop("notice", None)
    if notice:
        st.warning(notice)

    for result in st.session_state["results"]:
        render_turn(result.turn)
    with st.chat_message("assistant"):
        st.write(question.text)
    if pending is not None:
        with st.chat_message("user"):
            st.write(pending.answer)
        with st.chat_message("assistant"):
            st.write(pending.followup)

    answer = st.chat_input("Your answer")
    if answer is not None:
        handle_answer(answer, question)


def render_turn(turn: Turn) -> None:
    """Show one answered main question and its optional follow-up (FR-06 AC1)."""
    with st.chat_message("assistant"):
        st.write(turn.question_text)
    with st.chat_message("user"):
        st.write(turn.answer)
    if turn.followup is not None:
        with st.chat_message("assistant"):
            st.write(turn.followup)
        with st.chat_message("user"):
            st.write(turn.followup_answer)


def handle_answer(answer: str, question: Question) -> None:
    """Guard the answer, then ask the follow-up or finish the question (FR-06 AC3, FR-07 AC5)."""
    for result in (check_length(answer, MAX_ANSWER_CHARS, "Your answer"), detect_injection(answer)):
        if not result.ok:
            st.error(result.message)
            return
    pending = st.session_state["pending"]
    if pending is not None:
        finish_turn(replace(pending, followup_answer=answer), question)
    elif question.type == "gap":
        ask_followup(Turn(question.id, question.text, answer), question)
    else:
        finish_turn(Turn(question.id, question.text, answer), question)


def ask_followup(turn: Turn, question: Question) -> None:
    """Stream exactly one follow-up after a ``gap`` answer (FR-07 AC1-AC4)."""
    history = [result.turn for result in st.session_state["results"]]
    messages = build_interviewer_messages(st.session_state["plan"], [*history, turn])
    with st.chat_message("user"):
        st.write(turn.answer)
    try:
        with st.chat_message("assistant"):
            followup = generate_followup(messages, st.session_state["run_config"])
    except LLMError as err:
        st.session_state["notice"] = f"{err} The interview continues without a follow-up."
        finish_turn(turn, question)
        return
    st.session_state["pending"] = replace(turn, followup=followup)
    st.rerun()


def finish_turn(turn: Turn, question: Question) -> None:
    """Evaluate the finished main question, store it and move on (FR-08 AC1)."""
    plan = st.session_state["plan"]
    run_config = st.session_state["run_config"]
    gap = next((g for g in plan.gaps if g.id == question.gap_id), None)
    try:
        with st.spinner("Saving your answer - feedback follows at the end ..."):
            evaluation, _usages = evaluate_answer(
                question, turn.answer, turn.followup, turn.followup_answer, run_config, gap
            )
    except LLMError as err:
        evaluation = None
        st.session_state["notice"] = f"{err} This answer will not be scored."
    st.session_state["results"].append(TurnResult(turn, evaluation, run_config))
    st.session_state["pending"] = None
    st.session_state["q_index"] += 1
    if st.session_state["q_index"] >= len(plan.questions):
        st.session_state["state"] = State.REPORT
    st.rerun()


def render_report() -> None:
    """REPORT: show the scored feedback report.

    Overall score as the Python-computed mean with one decimal (FR-09 AC1), per
    question the answers, score, STAR breakdown, strengths, improvements and the
    collapsible improved answer (FR-09 AC2), the gaps next to the scores of the
    questions that targeted them (FR-09 AC3), and which variant and model produced
    the evaluations (FR-09 AC4, FR-10 AC5). "Start over" returns to ``SETUP`` and
    clears all data (§3).
    """
    plan = st.session_state["plan"]
    results = st.session_state["results"]
    scored = [result.evaluation for result in results if result.evaluation is not None]
    st.subheader("Your interview report")
    if scored:
        st.metric("Overall score", f"{aggregate_scores(scored):.1f} / 5")
        run_config = results[0].run_config
        st.caption(f"Evaluated with variant {run_config.eval_variant} and model {run_config.model}.")
    else:
        st.warning("None of your answers could be scored.")
    render_gap_scores(plan, results)
    for result in results:
        render_result(result)
    st.button("Start over", type="primary", on_click=start_over)


def render_gap_scores(plan: InterviewPlan, results: list[TurnResult]) -> None:
    """List each gap next to the scores of the questions that targeted it (FR-09 AC3)."""
    gap_of_question = {question.id: question.gap_id for question in plan.questions}
    st.markdown("**Your gaps and how you handled them**")
    for gap in plan.gaps:
        scores = [
            str(result.evaluation.score)
            for result in results
            if result.evaluation is not None and gap_of_question[result.turn.question_id] == gap.id
        ]
        handled = f"score {', '.join(scores)} / 5" if scores else "not asked"
        st.markdown(f"- **{gap.severity.upper()}**: {gap.description} - {handled}")


def render_result(result: TurnResult) -> None:
    """Show one main question with answers and evaluation (FR-09 AC2)."""
    turn, evaluation = result.turn, result.evaluation
    st.divider()
    st.markdown(f"**{turn.question_text}**")
    st.markdown(f"_Your answer:_ {turn.answer}")
    if turn.followup is not None:
        st.markdown(f"**Follow-up:** {turn.followup}")
        st.markdown(f"_Your answer:_ {turn.followup_answer}")
    if evaluation is None:
        st.info("This answer could not be scored.")
        return
    off_topic = "" if evaluation.relevant else " (off-topic)"
    st.markdown(f"**Score: {evaluation.score} / 5**{off_topic}")
    star = evaluation.star
    if any(element is not None for element in (star.situation, star.task, star.action, star.result)):
        st.markdown(
            f"STAR - Situation: {star.situation or '-'} · Task: {star.task or '-'} · "
            f"Action: {star.action or '-'} · Result: {star.result or '-'}"
        )
    st.markdown("**Strengths**\n\n" + "\n".join(f"- {item}" for item in evaluation.strengths))
    st.markdown("**Improvements**\n\n" + "\n".join(f"- {item}" for item in evaluation.improvements))
    with st.expander("Improved example answer"):
        st.write(evaluation.improved_answer)


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
