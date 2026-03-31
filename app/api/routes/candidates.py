from datetime import datetime, timedelta
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app import models, schemas
from app.core.config import settings
from app.security.rbac import require_roles

router = APIRouter(
    prefix="/candidates",
    tags=["candidates"],
    dependencies=[Depends(require_roles("recruiter"))],
)


@router.post("", response_model=schemas.CandidateRead, status_code=status.HTTP_201_CREATED)
def create_candidate(payload: schemas.CandidateCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Candidate).filter(models.Candidate.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Candidate already exists")
    access_token = secrets.token_urlsafe(48)[:64]
    token_expires_at = datetime.utcnow() + timedelta(days=settings.candidate_token_days)
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
    db.commit()
    db.refresh(candidate)
    return candidate


@router.get("", response_model=list[schemas.CandidateRead])
def list_candidates(db: Session = Depends(get_db)):
    return db.query(models.Candidate).order_by(models.Candidate.full_name).all()
