from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from app.api.deps import get_db
from app import models, schemas
from app.core.config import settings
from app.services.question_generation import generate_questions
from app.services.evaluation import evaluate_answer
from app.security.rbac import require_roles

router = APIRouter(prefix="/interviews", tags=["interviews"])


def _get_next_question(db: Session, interview_id: int) -> models.InterviewQuestion | None:
    answered_subq = (
        db.query(models.Answer.interview_question_id)
        .join(models.InterviewQuestion)
        .filter(models.InterviewQuestion.interview_id == interview_id)
        .subquery()
    )
    return (
        db.query(models.InterviewQuestion)
        .filter(models.InterviewQuestion.interview_id == interview_id)
        .filter(~models.InterviewQuestion.id.in_(answered_subq))
        .order_by(models.InterviewQuestion.order_index)
        .first()
    )


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

    if not payload.role_id and not payload.custom_role:
        raise HTTPException(status_code=400, detail="role_id or custom_role is required")

    interview = models.Interview(
        candidate_id=payload.candidate_id,
        role_id=payload.role_id,
        custom_role=payload.custom_role,
        skills=payload.skills,
    )
    db.add(interview)
    db.flush()

    question_count = payload.question_count or settings.default_question_count

    if payload.role_id:
        questions = (
            db.query(models.QuestionBank)
            .filter(models.QuestionBank.role_id == payload.role_id)
            .order_by(models.QuestionBank.id)
            .limit(question_count)
            .all()
        )
        if not questions:
            raise HTTPException(status_code=400, detail="No questions for this role")
        for index, q in enumerate(questions, start=1):
            db.add(
                models.InterviewQuestion(
                    interview_id=interview.id,
                    question_id=q.id,
                    question_text=q.text,
                    order_index=index,
                )
            )
    else:
        generated = generate_questions(payload.custom_role, payload.skills)
        for index, text in enumerate(generated[:question_count], start=1):
            db.add(
                models.InterviewQuestion(
                    interview_id=interview.id,
                    question_text=text,
                    order_index=index,
                )
            )

    db.commit()
    db.refresh(interview)
    return interview


@router.get(
    "",
    response_model=list[schemas.InterviewRead],
    dependencies=[Depends(require_roles("recruiter", "interviewer"))],
)
def list_interviews(db: Session = Depends(get_db)):
    return (
        db.query(models.Interview)
        .options(selectinload(models.Interview.questions))
        .order_by(models.Interview.started_at.desc())
        .all()
    )


@router.get(
    "/{interview_id}",
    response_model=schemas.InterviewDetail,
    dependencies=[Depends(require_roles("recruiter", "interviewer"))],
)
def get_interview(interview_id: int, db: Session = Depends(get_db)):
    interview = (
        db.query(models.Interview)
        .options(
            selectinload(models.Interview.questions),
            selectinload(models.Interview.candidate),
            selectinload(models.Interview.role),
        )
        .filter(models.Interview.id == interview_id)
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    answers = (
        db.query(models.Answer)
        .join(models.InterviewQuestion)
        .filter(models.InterviewQuestion.interview_id == interview_id)
        .order_by(models.Answer.created_at)
        .all()
    )

    return schemas.InterviewDetail(
        id=interview.id,
        candidate=interview.candidate,
        role=interview.role,
        custom_role=interview.custom_role,
        skills=interview.skills,
        status=interview.status,
        started_at=interview.started_at,
        finished_at=interview.finished_at,
        questions=interview.questions,
        answers=answers,
    )


@router.get(
    "/{interview_id}/transcript",
    response_model=schemas.InterviewTranscript,
    dependencies=[Depends(require_roles("recruiter", "interviewer"))],
)
def get_interview_transcript(interview_id: int, db: Session = Depends(get_db)):
    interview = (
        db.query(models.Interview)
        .options(
            selectinload(models.Interview.candidate),
            selectinload(models.Interview.role),
        )
        .filter(models.Interview.id == interview_id)
        .first()
    )
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    answers = (
        db.query(models.Answer, models.InterviewQuestion)
        .join(models.InterviewQuestion)
        .filter(models.InterviewQuestion.interview_id == interview_id)
        .order_by(models.Answer.created_at)
        .all()
    )

    transcripts = [
        schemas.TranscriptItem(
            interview_question_id=answer.interview_question_id,
            question_text=question.question_text,
            transcript=answer.transcript,
            score=answer.score,
            feedback=answer.feedback,
            created_at=answer.created_at,
        )
        for answer, question in answers
    ]

    return schemas.InterviewTranscript(
        id=interview.id,
        candidate=interview.candidate,
        role=interview.role,
        custom_role=interview.custom_role,
        skills=interview.skills,
        status=interview.status,
        started_at=interview.started_at,
        finished_at=interview.finished_at,
        transcripts=transcripts,
    )


@router.post(
    "/{interview_id}/start",
    response_model=schemas.InterviewSessionState,
    dependencies=[Depends(require_roles("interviewer"))],
)
def start_interview_session(interview_id: int, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    if interview.status != "completed":
        interview.status = "in_progress"
        db.commit()
        db.refresh(interview)

    next_question = _get_next_question(db, interview_id)
    is_complete = next_question is None

    return schemas.InterviewSessionState(
        interview_id=interview.id,
        status=interview.status,
        question=next_question,
        is_complete=is_complete,
    )


@router.get(
    "/{interview_id}/next-question",
    response_model=schemas.InterviewSessionState,
    dependencies=[Depends(require_roles("interviewer"))],
)
def get_next_question(interview_id: int, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    next_question = _get_next_question(db, interview_id)
    is_complete = next_question is None

    return schemas.InterviewSessionState(
        interview_id=interview.id,
        status=interview.status,
        question=next_question,
        is_complete=is_complete,
    )


@router.post(
    "/{interview_id}/submit-answer",
    response_model=schemas.InterviewSessionAnswer,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("interviewer"))],
)
def submit_session_answer(interview_id: int, payload: schemas.AnswerCreate, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    interview_question = (
        db.query(models.InterviewQuestion)
        .filter(
            models.InterviewQuestion.id == payload.interview_question_id,
            models.InterviewQuestion.interview_id == interview_id,
        )
        .first()
    )
    if not interview_question:
        raise HTTPException(status_code=404, detail="Interview question not found")

    score, feedback = evaluate_answer(interview_question.question_text, payload.transcript)
    answer = models.Answer(
        interview_question_id=payload.interview_question_id,
        transcript=payload.transcript,
        score=score,
        feedback=feedback,
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)

    next_question = _get_next_question(db, interview_id)
    is_complete = next_question is None

    return schemas.InterviewSessionAnswer(
        answer=answer,
        next_question=next_question,
        is_complete=is_complete,
        status=interview.status,
    )


@router.post(
    "/{interview_id}/end",
    response_model=schemas.InterviewRead,
    dependencies=[Depends(require_roles("interviewer"))],
)
def end_interview_session(interview_id: int, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    interview.status = "completed"
    interview.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(interview)
    return interview


@router.post(
    "/{interview_id}/answers",
    response_model=schemas.AnswerRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("interviewer"))],
)
def submit_answer(interview_id: int, payload: schemas.AnswerCreate, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    interview_question = (
        db.query(models.InterviewQuestion)
        .filter(
            models.InterviewQuestion.id == payload.interview_question_id,
            models.InterviewQuestion.interview_id == interview_id,
        )
        .first()
    )
    if not interview_question:
        raise HTTPException(status_code=404, detail="Interview question not found")

    score, feedback = evaluate_answer(interview_question.question_text, payload.transcript)
    answer = models.Answer(
        interview_question_id=payload.interview_question_id,
        transcript=payload.transcript,
        score=score,
        feedback=feedback,
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
def finish_interview(interview_id: int, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    interview.status = "completed"
    interview.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(interview)
    return interview
