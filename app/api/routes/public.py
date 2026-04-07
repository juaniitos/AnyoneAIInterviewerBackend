from __future__ import annotations

from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.api.deps import get_db
from app.services.intent_classifier import normalize_intent
from app.services.interview_state_service import (
    build_semantic_question_plan,
    clarify_current_question,
    get_interview_language,
    initialize_interview_graph,
    set_interview_language,
    skip_current_question,
    submit_interview_answer,
)

router = APIRouter(prefix="/public", tags=["public"])


def _resolve_candidate_session(
    db: Session,
    interview_id: str,
    token: str,
) -> models.InterviewSession:
    session = (
        db.query(models.InterviewSession)
        .options(
            selectinload(models.InterviewSession.candidate),
            selectinload(models.InterviewSession.job_role),
            selectinload(models.InterviewSession.template),
            selectinload(models.InterviewSession.answers),
        )
        .filter(models.InterviewSession.id == interview_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")
    if session.candidate.access_token != token:
        raise HTTPException(status_code=403, detail="Invalid interview token")
    if session.candidate.token_expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Interview token expired")
    return session


def _role_to_public_job(db: Session, role: models.JobRole) -> schemas.PublicJobDetail:
    questions = (
        db.query(models.Question)
        .filter(models.Question.job_role_id == role.id, models.Question.is_active.is_(True))
        .order_by(models.Question.id)
        .all()
    )
    description = role.description or f"Join the {role.department or 'AI'} team and help build the next iteration of our interview platform."
    skills = role.skills_required or []
    first_three_skills = ", ".join(skills[:3]) if skills else "communication, structured thinking, and ownership"
    return schemas.PublicJobDetail(
        id=role.id,
        title=role.name,
        department=role.department,
        description=description,
        seniority=role.seniority,
        location="Remote / Hybrid",
        employment_type="Full-time",
        salary_range="Competitive package",
        skills_required=skills,
        posted_time="Recently added",
        ai_insight="High match potential" if skills else None,
        question_count=len(questions),
        mission_highlight=description,
        responsibilities=[
            f"Deliver high-quality outcomes as a {role.name}.",
            f"Collaborate across {role.department or 'cross-functional'} stakeholders with strong written and verbal communication.",
            "Turn ambiguity into clear execution plans with measurable impact.",
        ],
        technical_core=first_three_skills,
        design_literacy="Clear, structured communication and thoughtful tradeoff analysis are strongly valued.",
        benefits=[
            {"category": "Flexibility", "value": "Remote-friendly collaboration"},
            {"category": "Growth", "value": "Hands-on work with AI-driven systems"},
            {"category": "Impact", "value": "Direct influence on product quality"},
        ],
    )


def _get_session_questions(db: Session, session: models.InterviewSession) -> list[models.Question]:
    query = (
        db.query(models.Question)
        .filter(models.Question.job_role_id == session.job_role_id)
        .filter(models.Question.is_active.is_(True))
        .order_by(models.Question.id)
    )
    if session.template and session.template.question_count:
        query = query.limit(session.template.question_count)
    return query.all()


def _question_plan_from_state(
    db: Session,
    session: models.InterviewSession,
    fallback_questions: list[models.Question],
) -> list[models.Question]:
    plan = list((session.graph_state_json or {}).get("question_plan") or [])
    if not plan:
        plan = build_semantic_question_plan(db, session, fallback_questions)

    if not plan:
        return fallback_questions

    question_map = {question.id: question for question in fallback_questions}
    resolved: list[models.Question] = []
    for item in plan:
        existing = question_map.get(item["id"])
        if existing:
            resolved.append(existing)
            continue
        resolved.append(
            models.Question(
                id=item["id"],
                job_role_id=session.job_role_id,
                text=item["text"],
                category="dynamic",
                difficulty="adaptive",
                is_active=True,
            )
        )
    return resolved


def _build_public_state(db: Session, session: models.InterviewSession) -> schemas.PublicInterviewState:
    base_questions = _get_session_questions(db, session)
    questions = _question_plan_from_state(db, session, base_questions)
    answered_ids = {answer.question_id for answer in session.answers}
    current_question = None
    if session.current_question_text:
        current_question = models.Question(
            id=session.current_question_id or "",
            job_role_id=session.job_role_id,
            text=session.current_question_text,
            category="dynamic",
            difficulty="adaptive",
            is_active=True,
        )
    elif session.current_question_id:
        current_question = next((question for question in questions if question.id == session.current_question_id), None)
    if current_question is None:
        current_question = next((question for question in questions if question.id not in answered_ids), None)
    return schemas.PublicInterviewState(
        interview_id=session.id,
        candidate_name=session.candidate.full_name,
        job_title=session.job_role.name,
        status=session.status,
        interview_language=get_interview_language(session),
        current_question=schemas.SessionQuestion.model_validate(current_question) if current_question else None,
        total_questions=len(questions),
        answered_questions=len(answered_ids),
        clarification_count=session.clarification_count,
        skip_count=session.skip_count,
        is_complete=current_question is None,
    )


def _build_transcript(session: models.InterviewSession, questions: list[models.Question]) -> schemas.InterviewTranscript:
    question_map = {question.id: question for question in questions}
    ordered_answers = sorted(session.answers, key=lambda answer: (answer.question_number, answer.created_at))
    return schemas.InterviewTranscript(
        id=session.id,
        candidate=session.candidate,
        job_role=session.job_role,
        template=session.template,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        transcripts=[
            schemas.TranscriptItem(
                question_id=answer.question_id,
                question_text=question_map[answer.question_id].text if answer.question_id in question_map else "",
                question_number=answer.question_number,
                transcript=answer.transcript,
                audio_url=answer.audio_url,
                audio_duration_sec=float(answer.audio_duration_sec) if answer.audio_duration_sec is not None else None,
                stt_confidence=float(answer.stt_confidence) if answer.stt_confidence is not None else None,
                created_at=answer.created_at,
            )
            for answer in ordered_answers
        ],
    )


@router.get("/jobs", response_model=list[schemas.PublicJobSummary])
def list_public_jobs(db: Session = Depends(get_db)):
    roles = db.query(models.JobRole).order_by(models.JobRole.created_at.desc()).all()
    return [_role_to_public_job(db, role) for role in roles]


@router.get("/jobs/{job_role_id}", response_model=schemas.PublicJobDetail)
def get_public_job(job_role_id: str, db: Session = Depends(get_db)):
    role = db.query(models.JobRole).filter(models.JobRole.id == job_role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Job not found")
    return _role_to_public_job(db, role)


@router.post(
    "/applications",
    response_model=schemas.PublicApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_public_application(payload: schemas.PublicApplicationCreate, db: Session = Depends(get_db)):
    role = db.query(models.JobRole).filter(models.JobRole.id == payload.job_role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Job not found")

    template = (
        db.query(models.InterviewTemplate)
        .filter(models.InterviewTemplate.job_role_id == payload.job_role_id)
        .order_by(models.InterviewTemplate.name)
        .first()
    )
    if not template:
        raise HTTPException(status_code=400, detail="No interview template configured for this job")

    candidate = db.query(models.Candidate).filter(models.Candidate.email == payload.email).first()
    access_token = secrets.token_urlsafe(48)[:64]
    token_expires_at = datetime.utcnow() + timedelta(days=7)

    if candidate:
        candidate.full_name = payload.full_name
        candidate.phone = payload.phone
        candidate.cv_summary = payload.cv_summary
        candidate.skills = payload.skills
        candidate.years_experience = payload.years_experience
        candidate.access_token = access_token
        candidate.token_expires_at = token_expires_at
    else:
        candidate = models.Candidate(
            full_name=payload.full_name,
            email=payload.email,
            phone=payload.phone,
            cv_summary=payload.cv_summary,
            skills=payload.skills,
            years_experience=payload.years_experience,
            access_token=access_token,
            token_expires_at=token_expires_at,
        )
        db.add(candidate)
        db.flush()

    interview = models.InterviewSession(
        candidate_id=candidate.id,
        job_role_id=role.id,
        template_id=template.id,
        status="pending",
        graph_state_json={"language": "es" if (payload.interview_language or "en").lower().startswith("es") else "en"},
    )
    db.add(interview)
    db.commit()
    db.refresh(candidate)
    db.refresh(interview)

    return schemas.PublicApplicationResponse(
        candidate=candidate,
        interview=interview,
        interview_token=candidate.access_token,
    )


@router.get("/interviews/{interview_id}", response_model=schemas.PublicInterviewState)
def get_public_interview_state(
    interview_id: str,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    session = _resolve_candidate_session(db, interview_id, token)
    return _build_public_state(db, session)


@router.post("/interviews/{interview_id}/start", response_model=schemas.PublicInterviewState)
def start_public_interview(
    interview_id: str,
    token: str = Query(...),
    language: str = Query("en"),
    db: Session = Depends(get_db),
):
    session = _resolve_candidate_session(db, interview_id, token)
    questions = _get_session_questions(db, session)
    if not questions:
        raise HTTPException(status_code=400, detail="No questions configured for this interview")

    selected_language = set_interview_language(session, language)
    if session.status != "completed" and not (session.graph_state_json or {}).get("last_question"):
        initialize_interview_graph(db, session, questions, language=selected_language)
    elif session.started_at is None:
        session.started_at = datetime.utcnow()
        session.status = "in_progress"
    db.commit()
    db.refresh(session)
    return _build_public_state(db, session)


@router.post("/interviews/{interview_id}/turn", response_model=schemas.InterviewTurnResponse)
def handle_public_interview_turn(
    interview_id: str,
    payload: schemas.InterviewTurnRequest,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    session = _resolve_candidate_session(db, interview_id, token)
    if session.status == "completed":
        raise HTTPException(status_code=409, detail="Interview already completed")

    if payload.interview_language:
        set_interview_language(session, payload.interview_language)

    questions = _get_session_questions(db, session)
    question_map = {question.id: index + 1 for index, question in enumerate(questions)}
    if session.current_question_id and payload.question_id != session.current_question_id:
        raise HTTPException(status_code=409, detail="Answer does not match the current interview question")
    if payload.question_id not in question_map and payload.question_id != session.current_question_id:
        raise HTTPException(status_code=404, detail="Question not found for this interview")

    current_state = _build_public_state(db, session)
    normalized_intent = normalize_intent(payload.intent, payload.utterance)

    if normalized_intent == "clarify":
        turn_result = clarify_current_question(session)
        db.commit()
        db.refresh(session)
        return schemas.InterviewTurnResponse(
            event_type="clarification",
            message=turn_result.message or "",
            status=session.status,
            interview_language=get_interview_language(session),
            current_question=current_state.current_question,
            answered_questions=current_state.answered_questions,
            total_questions=current_state.total_questions,
            candidate_answer_saved=False,
            evaluation=None,
            is_complete=False,
        )

    if normalized_intent == "skip":
        existing = (
            db.query(models.Answer)
            .filter(
                models.Answer.session_id == interview_id,
                models.Answer.question_id == payload.question_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="Answer already submitted")

        answer = models.Answer(
            session_id=interview_id,
            question_id=payload.question_id,
            question_number=payload.question_number or question_map[payload.question_id],
            transcript="[SKIPPED]",
            audio_url=payload.audio_url,
            audio_duration_sec=payload.audio_duration_sec,
            stt_confidence=payload.stt_confidence,
        )
        db.add(answer)
        db.flush()
        turn_result = skip_current_question(
            session,
            question_number=payload.question_number or question_map[payload.question_id],
        )
        db.commit()
        db.refresh(session)
        refreshed_state = _build_public_state(db, session)
        return schemas.InterviewTurnResponse(
            event_type="question" if not turn_result.is_complete else "completed",
            message=turn_result.current_question_text or "Question skipped.",
            status=turn_result.status,
            interview_language=get_interview_language(session),
            current_question=refreshed_state.current_question,
            answered_questions=refreshed_state.answered_questions,
            total_questions=refreshed_state.total_questions,
            candidate_answer_saved=True,
            evaluation=turn_result.last_evaluation,
            is_complete=turn_result.is_complete,
        )

    if not (payload.utterance or "").strip():
        raise HTTPException(status_code=400, detail="Answer text is required for intent 'answer'")

    existing = (
        db.query(models.Answer)
        .filter(
            models.Answer.session_id == interview_id,
            models.Answer.question_id == payload.question_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Answer already submitted")

    answer = models.Answer(
        session_id=interview_id,
        question_id=payload.question_id,
        question_number=payload.question_number or question_map[payload.question_id],
        transcript=payload.utterance,
        audio_url=payload.audio_url,
        audio_duration_sec=payload.audio_duration_sec,
        stt_confidence=payload.stt_confidence,
    )
    db.add(answer)
    db.flush()
    turn_result = submit_interview_answer(session, payload.utterance)
    db.commit()
    db.refresh(session)
    refreshed_state = _build_public_state(db, session)

    return schemas.InterviewTurnResponse(
        event_type="question" if not turn_result.is_complete else "completed",
        message=turn_result.current_question_text or "Interview completed.",
        status=turn_result.status,
        interview_language=get_interview_language(session),
        current_question=refreshed_state.current_question,
        answered_questions=refreshed_state.answered_questions,
        total_questions=refreshed_state.total_questions,
        candidate_answer_saved=True,
        evaluation=turn_result.last_evaluation,
        is_complete=turn_result.is_complete,
    )


@router.post("/interviews/{interview_id}/finish", response_model=schemas.PublicInterviewResult)
def finish_public_interview(
    interview_id: str,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    session = _resolve_candidate_session(db, interview_id, token)
    questions = _get_session_questions(db, session)
    answers = sorted(session.answers, key=lambda answer: (answer.question_number, answer.created_at))

    if not answers:
        raise HTTPException(status_code=400, detail="Cannot finish an interview without answers")

    evaluation = session.evaluation
    graph_state = session.graph_state_json or {}
    final_report = graph_state.get("final_report")
    if not final_report:
        raise HTTPException(status_code=409, detail="Interview graph has not produced a final report yet")

    session.status = "completed"
    session.ended_at = session.ended_at or datetime.utcnow()
    evaluation_data = {
        "score": final_report.get("overall_score", 0.0),
        "summary": final_report.get("summary", ""),
        "strengths": "\n".join(final_report.get("strengths", [])),
        "areas_of_improvement": "\n".join(final_report.get("gaps", [])),
        "recommendation": final_report.get("recommendation", "needs_review"),
        "model_used": f"anthropic:{session.graph_state_json.get('model', 'claude')}" if session.graph_state_json else "anthropic:claude",
    }
    if evaluation is None:
        evaluation = models.Evaluation(session_id=session.id, **evaluation_data)
        db.add(evaluation)
    else:
        for key, value in evaluation_data.items():
            setattr(evaluation, key, value)
        evaluation.evaluated_at = datetime.utcnow()

    db.commit()
    db.refresh(session)
    db.refresh(evaluation)

    return schemas.PublicInterviewResult(
        interview=session,
        evaluation=evaluation,
        transcript=_build_transcript(session, questions),
    )


@router.get("/interviews/{interview_id}/result", response_model=schemas.PublicInterviewResult)
def get_public_interview_result(
    interview_id: str,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    session = _resolve_candidate_session(db, interview_id, token)
    if session.evaluation is None:
        raise HTTPException(status_code=404, detail="Interview result not available yet")

    questions = _get_session_questions(db, session)
    return schemas.PublicInterviewResult(
        interview=session,
        evaluation=session.evaluation,
        transcript=_build_transcript(session, questions),
    )
