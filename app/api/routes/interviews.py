from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from app.api.deps import get_db
from app import models, schemas
from app.security.rbac import require_roles

router = APIRouter(prefix="/interviews", tags=["interviews"])


def _get_next_question(db: Session, session: models.InterviewSession) -> models.Question | None:
    answered_subq = (
        db.query(models.Answer.question_id)
        .filter(models.Answer.session_id == session.id)
        .subquery()
    )
    query = (
        db.query(models.Question)
        .filter(models.Question.job_role_id == session.job_role_id)
        .filter(models.Question.is_active.is_(True))
        .filter(~models.Question.id.in_(answered_subq))
        .order_by(models.Question.id)
    )
    if session.template and session.template.question_count:
        query = query.limit(session.template.question_count)
    return query.first()


def _session_questions(db: Session, session: models.InterviewSession) -> list[models.Question]:
    query = (
        db.query(models.Question)
        .filter(models.Question.job_role_id == session.job_role_id)
        .filter(models.Question.is_active.is_(True))
        .order_by(models.Question.id)
    )
    if session.template and session.template.question_count:
        query = query.limit(session.template.question_count)
    return query.all()


@router.post(
    "",
    response_model=schemas.InterviewRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("recruiter"))],
)
def create_interview(payload: schemas.InterviewCreate, db: Session = Depends(get_db)):
    candidate = db.query(models.Candidate).filter(models.Candidate.id == payload.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job_role = db.query(models.JobRole).filter(models.JobRole.id == payload.job_role_id).first()
    if not job_role:
        raise HTTPException(status_code=404, detail="Job role not found")

    template = None
    if payload.template_id:
        template = (
            db.query(models.InterviewTemplate)
            .filter(models.InterviewTemplate.id == payload.template_id)
            .first()
        )
        if not template:
            raise HTTPException(status_code=404, detail="Interview template not found")
        if template.job_role_id != payload.job_role_id:
            raise HTTPException(status_code=400, detail="Template does not match job role")
    else:
        template = (
            db.query(models.InterviewTemplate)
            .filter(models.InterviewTemplate.job_role_id == payload.job_role_id)
            .order_by(models.InterviewTemplate.name)
            .first()
        )
        if not template:
            raise HTTPException(status_code=400, detail="No interview template for this job role")

    session = models.InterviewSession(
        candidate_id=payload.candidate_id,
        job_role_id=payload.job_role_id,
        template_id=template.id,
        status="pending",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get(
    "",
    response_model=list[schemas.InterviewRead],
    dependencies=[Depends(require_roles("recruiter", "interviewer"))],
)
def list_interviews(db: Session = Depends(get_db)):
    return (
        db.query(models.InterviewSession)
        .order_by(models.InterviewSession.started_at.desc())
        .all()
    )


@router.get(
    "/{interview_id}",
    response_model=schemas.InterviewDetail,
    dependencies=[Depends(require_roles("recruiter", "interviewer"))],
)
def get_interview(interview_id: str, db: Session = Depends(get_db)):
    session = (
        db.query(models.InterviewSession)
        .options(
            selectinload(models.InterviewSession.candidate),
            selectinload(models.InterviewSession.job_role),
            selectinload(models.InterviewSession.template),
        )
        .filter(models.InterviewSession.id == interview_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")

    answers = (
        db.query(models.Answer)
        .filter(models.Answer.session_id == interview_id)
        .order_by(models.Answer.created_at)
        .all()
    )

    return schemas.InterviewDetail(
        id=session.id,
        candidate=session.candidate,
        job_role=session.job_role,
        template=session.template,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        answers=answers,
    )


@router.get(
    "/{interview_id}/transcript",
    response_model=schemas.InterviewTranscript,
    dependencies=[Depends(require_roles("recruiter", "interviewer"))],
)
def get_interview_transcript(interview_id: str, db: Session = Depends(get_db)):
    session = (
        db.query(models.InterviewSession)
        .options(
            selectinload(models.InterviewSession.candidate),
            selectinload(models.InterviewSession.job_role),
            selectinload(models.InterviewSession.template),
        )
        .filter(models.InterviewSession.id == interview_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")

    answers = (
        db.query(models.Answer, models.Question)
        .join(models.Question, models.Answer.question_id == models.Question.id)
        .filter(models.Answer.session_id == interview_id)
        .order_by(models.Answer.created_at)
        .all()
    )

    transcripts = [
        schemas.TranscriptItem(
            question_id=answer.question_id,
            question_text=question.text,
            question_number=answer.question_number,
            transcript=answer.transcript,
            audio_url=answer.audio_url,
            audio_duration_sec=answer.audio_duration_sec,
            stt_confidence=answer.stt_confidence,
            created_at=answer.created_at,
        )
        for answer, question in answers
    ]

    return schemas.InterviewTranscript(
        id=session.id,
        candidate=session.candidate,
        job_role=session.job_role,
        template=session.template,
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        transcripts=transcripts,
    )


@router.post(
    "/{interview_id}/start",
    response_model=schemas.InterviewSessionState,
    dependencies=[Depends(require_roles("interviewer"))],
)
def start_interview_session(interview_id: str, db: Session = Depends(get_db)):
    session = (
        db.query(models.InterviewSession)
        .options(selectinload(models.InterviewSession.template))
        .filter(models.InterviewSession.id == interview_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")

    if session.status != "completed":
        session.status = "in_progress"
        if session.started_at is None:
            session.started_at = datetime.utcnow()
        db.commit()
        db.refresh(session)

    next_question = _get_next_question(db, session)
    is_complete = next_question is None

    return schemas.InterviewSessionState(
        interview_id=session.id,
        status=session.status,
        question=schemas.SessionQuestion.model_validate(next_question) if next_question else None,
        is_complete=is_complete,
    )


@router.get(
    "/{interview_id}/next-question",
    response_model=schemas.InterviewSessionState,
    dependencies=[Depends(require_roles("interviewer"))],
)
def get_next_question(interview_id: str, db: Session = Depends(get_db)):
    session = (
        db.query(models.InterviewSession)
        .options(selectinload(models.InterviewSession.template))
        .filter(models.InterviewSession.id == interview_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")

    next_question = _get_next_question(db, session)
    is_complete = next_question is None

    return schemas.InterviewSessionState(
        interview_id=session.id,
        status=session.status,
        question=schemas.SessionQuestion.model_validate(next_question) if next_question else None,
        is_complete=is_complete,
    )


@router.post(
    "/{interview_id}/submit-answer",
    response_model=schemas.InterviewSessionAnswer,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("interviewer"))],
)
def submit_session_answer(interview_id: str, payload: schemas.AnswerCreate, db: Session = Depends(get_db)):
    session = (
        db.query(models.InterviewSession)
        .options(selectinload(models.InterviewSession.template))
        .filter(models.InterviewSession.id == interview_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")

    questions = _session_questions(db, session)
    question_map = {question.id: index + 1 for index, question in enumerate(questions)}
    if payload.question_id not in question_map:
        raise HTTPException(status_code=404, detail="Question not found for this interview")

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

    question_number = payload.question_number or question_map[payload.question_id]
    answer = models.Answer(
        session_id=interview_id,
        question_id=payload.question_id,
        question_number=question_number,
        transcript=payload.transcript,
        audio_url=payload.audio_url,
        audio_duration_sec=payload.audio_duration_sec,
        stt_confidence=payload.stt_confidence,
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)

    next_question = _get_next_question(db, session)
    is_complete = next_question is None

    return schemas.InterviewSessionAnswer(
        answer=answer,
        next_question=schemas.SessionQuestion.model_validate(next_question) if next_question else None,
        is_complete=is_complete,
        status=session.status,
    )


@router.post(
    "/{interview_id}/end",
    response_model=schemas.InterviewRead,
    dependencies=[Depends(require_roles("interviewer"))],
)
def end_interview_session(interview_id: str, db: Session = Depends(get_db)):
    session = db.query(models.InterviewSession).filter(models.InterviewSession.id == interview_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")
    session.status = "completed"
    session.ended_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session


@router.post(
    "/{interview_id}/answers",
    response_model=schemas.AnswerRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("interviewer"))],
)
def submit_answer(interview_id: str, payload: schemas.AnswerCreate, db: Session = Depends(get_db)):
    session = (
        db.query(models.InterviewSession)
        .options(selectinload(models.InterviewSession.template))
        .filter(models.InterviewSession.id == interview_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")

    questions = _session_questions(db, session)
    question_map = {question.id: index + 1 for index, question in enumerate(questions)}
    if payload.question_id not in question_map:
        raise HTTPException(status_code=404, detail="Question not found for this interview")

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

    question_number = payload.question_number or question_map[payload.question_id]
    answer = models.Answer(
        session_id=interview_id,
        question_id=payload.question_id,
        question_number=question_number,
        transcript=payload.transcript,
        audio_url=payload.audio_url,
        audio_duration_sec=payload.audio_duration_sec,
        stt_confidence=payload.stt_confidence,
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)
    return answer


@router.post(
    "/{interview_id}/finish",
    response_model=schemas.InterviewRead,
    dependencies=[Depends(require_roles("interviewer"))],
)
def finish_interview(interview_id: str, db: Session = Depends(get_db)):
    session = db.query(models.InterviewSession).filter(models.InterviewSession.id == interview_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")
    session.status = "completed"
    session.ended_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session
