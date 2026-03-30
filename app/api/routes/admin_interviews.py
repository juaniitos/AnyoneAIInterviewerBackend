from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from app.api.deps import get_db
from app import models, schemas
from app.core.config import settings
from app.security.rbac import require_roles
from app.services.question_generation import generate_questions

router = APIRouter(
    prefix="/admin/interviews",
    tags=["admin-interviews"],
    dependencies=[Depends(require_roles("admin"))],
)


@router.post("", response_model=schemas.InterviewRead, status_code=status.HTTP_201_CREATED)
def create_interview_admin(payload: schemas.InterviewCreate, db: Session = Depends(get_db)):
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


@router.get("", response_model=list[schemas.InterviewRead])
def list_interviews_admin(db: Session = Depends(get_db)):
    return (
        db.query(models.Interview)
        .options(selectinload(models.Interview.questions))
        .order_by(models.Interview.started_at.desc())
        .all()
    )


@router.get("/{interview_id}", response_model=schemas.InterviewDetail)
def get_interview_admin(interview_id: int, db: Session = Depends(get_db)):
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


@router.patch("/{interview_id}", response_model=schemas.InterviewRead)
def update_interview_admin(
    interview_id: int, payload: schemas.InterviewUpdate, db: Session = Depends(get_db)
):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "candidate_id" in update_data:
        candidate = db.query(models.Candidate).filter(models.Candidate.id == update_data["candidate_id"]).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

    for field, value in update_data.items():
        setattr(interview, field, value)

    if interview.status == "completed" and interview.finished_at is None:
        interview.finished_at = datetime.utcnow()

    db.commit()
    db.refresh(interview)
    return interview


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview_admin(interview_id: int, db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    db.delete(interview)
    db.commit()
    return None
