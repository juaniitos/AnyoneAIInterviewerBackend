from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app import models, schemas

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("", response_model=schemas.CandidateRead, status_code=status.HTTP_201_CREATED)
def create_candidate(payload: schemas.CandidateCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Candidate).filter(models.Candidate.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Candidate already exists")
    candidate = models.Candidate(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


@router.get("", response_model=list[schemas.CandidateRead])
def list_candidates(db: Session = Depends(get_db)):
    return db.query(models.Candidate).order_by(models.Candidate.created_at.desc()).all()
