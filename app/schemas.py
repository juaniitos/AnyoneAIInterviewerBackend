from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
    evaluation: "EvaluationRead | None" = None

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


class PublicJobSummary(BaseModel):
    id: str
    title: str
    department: str | None = None
    description: str | None = None
    seniority: str | None = None
    location: str = "Remote / Hybrid"
    employment_type: str = "Full-time"
    salary_range: str = "Competitive"
    skills_required: list[str] = []
    posted_time: str = "Recently added"
    ai_insight: str | None = None


class PublicJobDetail(PublicJobSummary):
    question_count: int = 0
    mission_highlight: str
    responsibilities: list[str] = []
    technical_core: str
    design_literacy: str
    benefits: list[dict[str, str]] = []


class PublicApplicationCreate(BaseModel):
    job_role_id: str
    full_name: str
    email: EmailStr
    phone: str | None = None
    cv_summary: str | None = None
    skills: list[str] | None = None
    years_experience: int | None = None
    interview_language: str | None = "en"


class PublicApplicationResponse(BaseModel):
    candidate: CandidateRead
    interview: InterviewRead
    interview_token: str


class PublicInterviewState(BaseModel):
    interview_id: str
    candidate_name: str
    job_title: str
    status: str
    interview_language: str = "en"
    current_question: SessionQuestion | None = None
    total_questions: int
    answered_questions: int
    clarification_count: int = 0
    skip_count: int = 0
    is_complete: bool


class EvaluationRead(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        from_attributes=True,
    )

    id: str
    session_id: str
    score: float
    summary: str
    strengths: str | None = None
    areas_of_improvement: str | None = None
    recommendation: str
    model_used: str
    reviewed_by: str | None = None
    evaluated_at: datetime

class PublicInterviewResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    interview: InterviewRead
    evaluation: EvaluationRead
    transcript: InterviewTranscript


class InterviewTurnRequest(BaseModel):
    question_id: str
    intent: str = Field(pattern="^(answer|clarify|skip|pass|idk)$")
    utterance: str | None = None
    question_number: int | None = None
    interview_language: str | None = None
    audio_url: str | None = None
    audio_duration_sec: float | None = None
    stt_confidence: float | None = None


class InterviewTurnResponse(BaseModel):
    event_type: str
    message: str
    status: str
    interview_language: str = "en"
    current_question: SessionQuestion | None = None
    answered_questions: int
    total_questions: int
    candidate_answer_saved: bool = False
    evaluation: dict | None = None
    is_complete: bool = False


class InterviewSocketEvent(BaseModel):
    type: str
    interview_language: str = "en"
    status: str | None = None
    message: str | None = None
    current_question: SessionQuestion | None = None
    answered_questions: int | None = None
    total_questions: int | None = None
    candidate_answer_saved: bool = False
    evaluation: dict | None = None
    transcript: str | None = None
    question_id: str | None = None
    audio_format: str | None = None
    is_complete: bool = False


class AdminInterviewSummary(BaseModel):
    id: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    candidate_name: str
    candidate_email: EmailStr
    role_name: str
    score: float | None = None
    recommendation: str | None = None
    answers_count: int = 0
