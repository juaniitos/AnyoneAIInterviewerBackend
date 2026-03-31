from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    seniority: str | None = None
    department: str | None = None
    skills_required: list[str] | None = None


class RoleRead(RoleCreate):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class QuestionCreate(BaseModel):
    job_role_id: str
    text: str
    category: str
    difficulty: str
    embedding: list[float] | None = None
    is_active: bool | None = True


class QuestionRead(QuestionCreate):
    id: str

    class Config:
        from_attributes = True


class CandidateCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    cv_summary: str | None = None
    skills: list[str] | None = None
    years_experience: int | None = None


class CandidateRead(CandidateCreate):
    id: str
    access_token: str
    token_expires_at: datetime

    class Config:
        from_attributes = True


class InterviewTemplateCreate(BaseModel):
    job_role_id: str
    name: str
    question_count: int = Field(ge=1, le=50)
    max_time_per_question_sec: int | None = None
    system_prompt: str
    evaluation_criteria: str | None = None


class InterviewTemplateRead(InterviewTemplateCreate):
    id: str

    class Config:
        from_attributes = True


class InterviewCreate(BaseModel):
    candidate_id: str
    job_role_id: str
    template_id: str | None = None


class InterviewUpdate(BaseModel):
    candidate_id: str | None = None
    job_role_id: str | None = None
    template_id: str | None = None
    status: str | None = None
    ended_at: datetime | None = None


class AnswerCreate(BaseModel):
    question_id: str
    transcript: str
    question_number: int | None = None
    audio_url: str | None = None
    audio_duration_sec: float | None = None
    stt_confidence: float | None = None


class AnswerRead(BaseModel):
    id: str
    session_id: str
    question_id: str
    question_number: int
    transcript: str
    audio_url: str | None = None
    audio_duration_sec: float | None = None
    stt_confidence: float | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class InterviewRead(BaseModel):
    id: str
    candidate_id: str
    job_role_id: str
    template_id: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None

    class Config:
        from_attributes = True


class InterviewDetail(BaseModel):
    id: str
    candidate: CandidateRead
    job_role: RoleRead
    template: InterviewTemplateRead
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    answers: list[AnswerRead] = []

    class Config:
        from_attributes = True


class TranscriptItem(BaseModel):
    question_id: str
    question_text: str
    question_number: int
    transcript: str
    audio_url: str | None = None
    audio_duration_sec: float | None = None
    stt_confidence: float | None = None
    created_at: datetime


class InterviewTranscript(BaseModel):
    id: str
    candidate: CandidateRead
    job_role: RoleRead
    template: InterviewTemplateRead
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    transcripts: list[TranscriptItem] = []

    class Config:
        from_attributes = True


class SessionQuestion(BaseModel):
    id: str
    text: str
    category: str
    difficulty: str

    class Config:
        from_attributes = True


class InterviewSessionState(BaseModel):
    interview_id: str
    status: str
    question: SessionQuestion | None = None
    is_complete: bool


class InterviewSessionAnswer(BaseModel):
    answer: AnswerRead
    next_question: SessionQuestion | None = None
    is_complete: bool
    status: str


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class AdminUserRead(BaseModel):
    id: str
    email: EmailStr
    name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
