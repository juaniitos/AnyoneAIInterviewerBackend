from datetime import datetime
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload
from app.api.deps import get_db
from app import models, schemas
from app.security.rbac import require_roles

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas
except ImportError:  # pragma: no cover
    letter = None  # type: ignore[assignment]
    stringWidth = None  # type: ignore[assignment]
    canvas = None  # type: ignore[assignment]

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


def _build_admin_interviews_query(db: Session):
    return (
        db.query(models.InterviewSession)
        .options(
            selectinload(models.InterviewSession.candidate),
            selectinload(models.InterviewSession.job_role),
            selectinload(models.InterviewSession.evaluation),
            selectinload(models.InterviewSession.answers),
        )
    )


def _apply_admin_interview_filters(
    query,
    *,
    status_filter: str | None = None,
    role_filter: str | None = None,
    search: str | None = None,
    score_min: float | None = None,
    score_max: float | None = None,
):
    if status_filter:
        query = query.filter(models.InterviewSession.status == status_filter)

    if role_filter:
        query = query.join(models.InterviewSession.job_role).filter(
            models.JobRole.name.ilike(f"%{role_filter}%")
        )

    if search:
        query = query.join(models.InterviewSession.candidate).filter(
            (models.Candidate.full_name.ilike(f"%{search}%"))
            | (models.Candidate.email.ilike(f"%{search}%"))
        )

    if score_min is not None or score_max is not None:
        query = query.outerjoin(models.InterviewSession.evaluation)
        if score_min is not None:
            query = query.filter(models.Evaluation.score >= score_min)
        if score_max is not None:
            query = query.filter(models.Evaluation.score <= score_max)

    return query


@router.get("", response_model=list[schemas.AdminInterviewSummary])
def list_interviews_admin(
    status_filter: str | None = Query(None, alias="status"),
    role: str | None = None,
    search: str | None = None,
    score_min: float | None = None,
    score_max: float | None = None,
    db: Session = Depends(get_db),
):
    sessions = (
        _apply_admin_interview_filters(
            _build_admin_interviews_query(db),
            status_filter=status_filter,
            role_filter=role,
            search=search,
            score_min=score_min,
            score_max=score_max,
        )
        .order_by(models.InterviewSession.started_at.desc())
        .all()
    )
    return [
        schemas.AdminInterviewSummary(
            id=session.id,
            status=session.status,
            started_at=session.started_at,
            ended_at=session.ended_at,
            candidate_name=session.candidate.full_name,
            candidate_email=session.candidate.email,
            role_name=session.job_role.name,
            score=float(session.evaluation.score) if session.evaluation else None,
            recommendation=session.evaluation.recommendation if session.evaluation else None,
            answers_count=len(session.answers),
        )
        for session in sessions
    ]


@router.get("/export.csv")
def export_interviews_admin(
    status_filter: str | None = Query(None, alias="status"),
    role: str | None = None,
    search: str | None = None,
    score_min: float | None = None,
    score_max: float | None = None,
    db: Session = Depends(get_db),
):
    sessions = (
        _apply_admin_interview_filters(
            _build_admin_interviews_query(db),
            status_filter=status_filter,
            role_filter=role,
            search=search,
            score_min=score_min,
            score_max=score_max,
        )
        .order_by(models.InterviewSession.started_at.desc())
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "interview_id",
            "candidate_name",
            "candidate_email",
            "role_name",
            "status",
            "score",
            "recommendation",
            "answers_count",
            "started_at",
            "ended_at",
        ]
    )

    for session in sessions:
        writer.writerow(
            [
                session.id,
                session.candidate.full_name,
                session.candidate.email,
                session.job_role.name,
                session.status,
                float(session.evaluation.score) if session.evaluation else "",
                session.evaluation.recommendation if session.evaluation else "",
                len(session.answers),
                session.started_at.isoformat() if session.started_at else "",
                session.ended_at.isoformat() if session.ended_at else "",
            ]
        )

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="interviews-export.csv"'
        },
    )


@router.get("/export.pdf")
def export_interviews_admin_pdf(
    status_filter: str | None = Query(None, alias="status"),
    role: str | None = None,
    search: str | None = None,
    score_min: float | None = None,
    score_max: float | None = None,
    db: Session = Depends(get_db),
):
    if canvas is None or letter is None or stringWidth is None:
        raise HTTPException(status_code=503, detail="PDF export dependency is not installed")

    sessions = (
        _apply_admin_interview_filters(
            _build_admin_interviews_query(db),
            status_filter=status_filter,
            role_filter=role,
            search=search,
            score_min=score_min,
            score_max=score_max,
        )
        .order_by(models.InterviewSession.started_at.desc())
        .all()
    )

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 48

    def draw_line(text: str, *, font: str = "Helvetica", size: int = 10, indent: int = 0):
        nonlocal y
        max_width = width - 72 - indent
        current = ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if stringWidth(candidate, font, size) <= max_width:
                current = candidate
                continue
            pdf.setFont(font, size)
            pdf.drawString(36 + indent, y, current)
            y -= size + 4
            current = word
            if y < 72:
                pdf.showPage()
                y = height - 48
        if current:
            pdf.setFont(font, size)
            pdf.drawString(36 + indent, y, current)
            y -= size + 4
            if y < 72:
                pdf.showPage()
                y = height - 48

    pdf.setTitle("AI Interviewer Export")
    draw_line("AI Interviewer - Interviews Export", font="Helvetica-Bold", size=16)
    draw_line(f"Generated at: {datetime.utcnow().isoformat()} UTC", size=9)
    draw_line(f"Total interviews: {len(sessions)}", size=9)
    y -= 8

    for session in sessions:
        recommendation = session.evaluation.recommendation if session.evaluation else "pending"
        score = f"{float(session.evaluation.score):.1f}" if session.evaluation else "-"
        draw_line(
            f"{session.candidate.full_name} | {session.candidate.email} | {session.job_role.name}",
            font="Helvetica-Bold",
            size=11,
        )
        draw_line(
            f"Status: {session.status} | Score: {score} | Recommendation: {recommendation} | Answers: {len(session.answers)}",
            size=9,
        )
        if session.evaluation and session.evaluation.summary:
            draw_line(f"Summary: {session.evaluation.summary}", size=9, indent=12)
        y -= 6
        if y < 72:
            pdf.showPage()
            y = height - 48

    pdf.save()
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="interviews-export.pdf"'
        },
    )


@router.get("/{interview_id}", response_model=schemas.InterviewDetail)
def get_interview_admin(interview_id: str, db: Session = Depends(get_db)):
    session = (
        db.query(models.InterviewSession)
        .options(
            selectinload(models.InterviewSession.candidate),
            selectinload(models.InterviewSession.job_role),
            selectinload(models.InterviewSession.template),
            selectinload(models.InterviewSession.evaluation),
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
        evaluation=session.evaluation,
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
