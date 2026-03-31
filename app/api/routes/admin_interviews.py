from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from app.api.deps import get_db
from app import models, schemas
from app.security.rbac import require_roles

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


@router.get("", response_model=list[schemas.InterviewRead])
def list_interviews_admin(db: Session = Depends(get_db)):
    return (
        db.query(models.InterviewSession)
        .order_by(models.InterviewSession.started_at.desc())
        .all()
    )


@router.get("/{interview_id}", response_model=schemas.InterviewDetail)
def get_interview_admin(interview_id: str, db: Session = Depends(get_db)):
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


@router.patch("/{interview_id}", response_model=schemas.InterviewRead)
def update_interview_admin(
    interview_id: str, payload: schemas.InterviewUpdate, db: Session = Depends(get_db)
):
    session = db.query(models.InterviewSession).filter(models.InterviewSession.id == interview_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "candidate_id" in update_data:
        candidate = db.query(models.Candidate).filter(models.Candidate.id == update_data["candidate_id"]).first()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
    if "job_role_id" in update_data:
        job_role = db.query(models.JobRole).filter(models.JobRole.id == update_data["job_role_id"]).first()
        if not job_role:
            raise HTTPException(status_code=404, detail="Job role not found")
    if "template_id" in update_data:
        template = db.query(models.InterviewTemplate).filter(models.InterviewTemplate.id == update_data["template_id"]).first()
        if not template:
            raise HTTPException(status_code=404, detail="Interview template not found")

    for field, value in update_data.items():
        setattr(session, field, value)

    if session.status == "completed" and session.ended_at is None:
        session.ended_at = datetime.utcnow()

    db.commit()
    db.refresh(session)
    return session


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview_admin(interview_id: str, db: Session = Depends(get_db)):
    session = db.query(models.InterviewSession).filter(models.InterviewSession.id == interview_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Interview not found")
    db.delete(session)
    db.commit()
    return None
