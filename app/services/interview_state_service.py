from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

from app import models
from app.agents import build_graph, new_state
from app.agents.interviewer_graph import ensure_question_language, get_llm, normalize_language
from app.core.config import settings
from app.services.semantic_questions import select_semantic_questions


graph = build_graph()


@dataclass
class InterviewTurnResult:
    current_question_id: str | None
    current_question_text: str | None
    current_question_index: int
    status: str
    is_complete: bool
    last_evaluation: dict[str, Any] | None
    final_report: dict[str, Any] | None
    graph_state: dict[str, Any]
    event_type: str = "question"
    message: str | None = None


def _question_plan(questions: list[models.Question]) -> list[dict[str, str]]:
    return [{"id": question.id, "text": question.text} for question in questions]


def build_semantic_question_plan(
    db: Session,
    session: models.InterviewSession,
    questions: list[models.Question],
) -> list[dict[str, str]]:
    limit = session.template.question_count if session.template and session.template.question_count else len(questions)
    selected = select_semantic_questions(
        db,
        role=session.job_role,
        candidate=session.candidate,
        template=session.template,
        limit=limit,
    )
    if not selected:
        return _question_plan(questions)
    return _question_plan(selected)


def _serialize_state(state: dict[str, Any]) -> dict[str, Any]:
    return dict(state)


def get_interview_language(session: models.InterviewSession) -> str:
    return normalize_language((session.graph_state_json or {}).get("language"))


def set_interview_language(session: models.InterviewSession, language: str | None) -> str:
    normalized = normalize_language(language)
    state = dict(session.graph_state_json or {})
    previous_language = normalize_language(state.get("language"))
    state["language"] = normalized

    if previous_language != normalized:
        current_question = state.get("last_question") or session.current_question_text
        if current_question:
            localized_question = ensure_question_language(current_question, normalized)
            state["last_question"] = localized_question
            asked_questions = list(state.get("asked_questions") or [])
            if asked_questions:
                asked_questions[-1] = localized_question
                state["asked_questions"] = asked_questions
            session.current_question_text = localized_question

    session.graph_state_json = state
    return normalized


def initialize_interview_graph(
    db: Session,
    session: models.InterviewSession,
    questions: list[models.Question],
    language: str = "en",
) -> InterviewTurnResult:
    question_plan = build_semantic_question_plan(db, session, questions)
    state = new_state(
        language=language,
        role=session.job_role.name,
        department=session.job_role.department or "General",
        seniority=session.job_role.seniority or "mid",
        candidate_name=session.candidate.full_name,
        skills_required=session.job_role.skills_required or [],
        question_plan=question_plan,
    )
    state = graph.invoke(state)
    state["model"] = settings.anthropic_model if settings.anthropic_api_key else "fallback"

    session.graph_state_json = _serialize_state(state)
    session.current_question_id = state.get("last_question_id") or None
    session.current_question_text = state.get("last_question") or None
    session.current_question_index = int(state.get("question_index", 0))
    session.status = "in_progress"
    session.started_at = session.started_at or datetime.utcnow()

    return InterviewTurnResult(
        current_question_id=session.current_question_id,
        current_question_text=session.current_question_text,
        current_question_index=session.current_question_index,
        status=session.status,
        is_complete=bool(state.get("is_finished", False)),
        last_evaluation=state.get("last_evaluation"),
        final_report=state.get("final_report"),
        graph_state=state,
    )


def submit_interview_answer(
    session: models.InterviewSession,
    answer_text: str,
) -> InterviewTurnResult:
    if not session.graph_state_json:
        raise ValueError("Interview graph state is missing")

    state = dict(session.graph_state_json)
    state["last_answer"] = answer_text
    state = graph.invoke(state)
    state["model"] = settings.anthropic_model if settings.anthropic_api_key else "fallback"

    session.graph_state_json = _serialize_state(state)
    session.current_question_id = state.get("last_question_id") if not state.get("is_finished") else None
    session.current_question_text = state.get("last_question") if not state.get("is_finished") else None
    session.current_question_index = int(state.get("question_index", session.current_question_index))
    session.status = "completed" if state.get("is_finished") else "in_progress"
    if state.get("is_finished"):
        session.ended_at = datetime.utcnow()

    return InterviewTurnResult(
        current_question_id=session.current_question_id,
        current_question_text=session.current_question_text,
        current_question_index=session.current_question_index,
        status=session.status,
        is_complete=bool(state.get("is_finished", False)),
        last_evaluation=state.get("last_evaluation"),
        final_report=state.get("final_report"),
        graph_state=state,
        event_type="completed" if bool(state.get("is_finished", False)) else "question",
        message=session.current_question_text,
    )


def clarify_current_question(session: models.InterviewSession) -> InterviewTurnResult:
    question_text = session.current_question_text or ""
    language = get_interview_language(session)
    explanation = (
        (
            f"Claro. Esto es lo que quiero decir: {question_text}. "
            "Responde con un ejemplo concreto, tu razonamiento y el impacto de tu decisión."
        )
        if language == "es"
        else f"Sure. Here is what I mean: {question_text}. "
        "Please answer with one concrete example, your reasoning, and the impact of your decision."
    )

    llm = get_llm()
    if llm is not None and question_text:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an AI interviewer. Clarify the current question without changing its intent. "
                    "Be brief, practical, and supportive. Reply in {language_label}.",
                ),
                (
                    "human",
                    "Current question:\n{question}\n\nExplain it more clearly in 2-3 sentences.",
                ),
            ]
        )
        messages = prompt.format_messages(
            question=question_text,
            language_label="Spanish" if language == "es" else "English",
        )
        explanation = str(llm.invoke(messages).content).strip() or explanation

    session.clarification_count += 1
    session.last_intent = "clarify"

    return InterviewTurnResult(
        current_question_id=session.current_question_id,
        current_question_text=session.current_question_text,
        current_question_index=session.current_question_index,
        status=session.status,
        is_complete=False,
        last_evaluation=None,
        final_report=None,
        graph_state=session.graph_state_json or {},
        event_type="clarification",
        message=explanation,
    )


def skip_current_question(
    session: models.InterviewSession,
    question_number: int,
) -> InterviewTurnResult:
    session.skip_count += 1
    session.last_intent = "skip"
    return submit_interview_answer(session, f"[SKIPPED] Candidate skipped question {question_number}.")
