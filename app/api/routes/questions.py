from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app import models, schemas
from app.security.rbac import require_roles
from app.services.semantic_questions import ensure_question_embedding

router = APIRouter(
    prefix="/questions",
    tags=["questions"],
    dependencies=[Depends(require_roles("admin"))],
)


@router.post("", response_model=schemas.QuestionRead, status_code=status.HTTP_201_CREATED)
def create_question(payload: schemas.QuestionCreate, db: Session = Depends(get_db)):
    job_role = db.query(models.JobRole).filter(models.JobRole.id == payload.job_role_id).first()
    if not job_role:
        raise HTTPException(status_code=404, detail="Job role not found")
    question = models.Question(
        job_role_id=payload.job_role_id,
        text=payload.text,
        category=payload.category,
        difficulty=payload.difficulty,
        embedding=payload.embedding,
        is_active=payload.is_active if payload.is_active is not None else True,
    )
    if not question.embedding:
        ensure_question_embedding(question, job_role)
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.get("", response_model=list[schemas.QuestionRead])
def list_questions(job_role_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.Question)
    if job_role_id:
        query = query.filter(models.Question.job_role_id == job_role_id)
    return query.order_by(models.Question.id).all()
