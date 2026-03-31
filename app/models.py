from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Boolean, Numeric, Float
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator
from app.db.base import Base


def uuid_str() -> str:
    return str(uuid4())


class StringArray(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text()))
        return dialect.type_descriptor(JSON())


class FloatArray(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Float()))
        return dialect.type_descriptor(JSON())


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    evaluations = relationship("Evaluation", back_populates="reviewer")


class JobRole(Base):
    __tablename__ = "job_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skills_required: Mapped[list[str] | None] = mapped_column(StringArray, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    templates = relationship("InterviewTemplate", back_populates="job_role")
    questions = relationship("Question", back_populates="job_role")
    sessions = relationship("InterviewSession", back_populates="job_role")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    job_role_id: Mapped[str] = mapped_column(ForeignKey("job_roles.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))
    difficulty: Mapped[str] = mapped_column(String(10))
    embedding: Mapped[list[float] | None] = mapped_column(FloatArray, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    job_role = relationship("JobRole", back_populates="questions")
    answers = relationship("Answer", back_populates="question")


class InterviewTemplate(Base):
    __tablename__ = "interview_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    job_role_id: Mapped[str] = mapped_column(ForeignKey("job_roles.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    question_count: Mapped[int] = mapped_column(Integer)
    max_time_per_question_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text)
    evaluation_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)

    job_role = relationship("JobRole", back_populates="templates")
    sessions = relationship("InterviewSession", back_populates="template")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cv_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(StringArray, nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    access_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime)

    sessions = relationship("InterviewSession", back_populates="candidate")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    job_role_id: Mapped[str] = mapped_column(ForeignKey("job_roles.id"), index=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("interview_templates.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    candidate = relationship("Candidate", back_populates="sessions")
    job_role = relationship("JobRole", back_populates="sessions")
    template = relationship("InterviewTemplate", back_populates="sessions")
    answers = relationship("Answer", back_populates="session", cascade="all, delete-orphan")
    evaluation = relationship("Evaluation", back_populates="session", uselist=False, cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    question_number: Mapped[int] = mapped_column(Integer)
    transcript: Mapped[str] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_duration_sec: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    stt_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("InterviewSession", back_populates="answers")
    question = relationship("Question", back_populates="answers")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id"), unique=True, index=True)
    score: Mapped[float] = mapped_column(Numeric(4, 1))
    summary: Mapped[str] = mapped_column(Text)
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    areas_of_improvement: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str] = mapped_column(String(20))
    model_used: Mapped[str] = mapped_column(String(50))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session = relationship("InterviewSession", back_populates="evaluation")
    reviewer = relationship("AdminUser", back_populates="evaluations")
