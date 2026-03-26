from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app import models, schemas

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("", response_model=schemas.QuestionRead, status_code=status.HTTP_201_CREATED)
def create_question(payload: schemas.QuestionCreate, db: Session = Depends(get_db)):
    question = models.QuestionBank(role_id=payload.role_id, text=payload.text, category=payload.category)
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.get("", response_model=list[schemas.QuestionRead])
def list_questions(role_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(models.QuestionBank)
    if role_id:
        query = query.filter(models.QuestionBank.role_id == role_id)
    return query.order_by(models.QuestionBank.id).all()
