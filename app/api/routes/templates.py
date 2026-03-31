from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app import models, schemas
from app.security.rbac import require_roles

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(require_roles("admin"))],
)


@router.post("", response_model=schemas.InterviewTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(payload: schemas.InterviewTemplateCreate, db: Session = Depends(get_db)):
    job_role = db.query(models.JobRole).filter(models.JobRole.id == payload.job_role_id).first()
    if not job_role:
        raise HTTPException(status_code=404, detail="Job role not found")

    template = models.InterviewTemplate(
        job_role_id=payload.job_role_id,
        name=payload.name,
        question_count=payload.question_count,
        max_time_per_question_sec=payload.max_time_per_question_sec,
        system_prompt=payload.system_prompt,
        evaluation_criteria=payload.evaluation_criteria,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.get("", response_model=list[schemas.InterviewTemplateRead])
def list_templates(job_role_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(models.InterviewTemplate)
    if job_role_id:
        query = query.filter(models.InterviewTemplate.job_role_id == job_role_id)
    return query.order_by(models.InterviewTemplate.name).all()


@router.get("/{template_id}", response_model=schemas.InterviewTemplateRead)
def get_template(template_id: str, db: Session = Depends(get_db)):
    template = db.query(models.InterviewTemplate).filter(models.InterviewTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Interview template not found")
    return template
