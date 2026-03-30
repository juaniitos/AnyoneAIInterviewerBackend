from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class RoleCreate(BaseModel):
    name: str
    description: str | None = None


class RoleRead(RoleCreate):
    id: int

    class Config:
        from_attributes = True


class QuestionCreate(BaseModel):
    role_id: int | None = None
    text: str
    category: str | None = None


class QuestionRead(QuestionCreate):
    id: int

    class Config:
        from_attributes = True


class CandidateCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr


class CandidateRead(CandidateCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class InterviewCreate(BaseModel):
    candidate_id: int
    role_id: int | None = None
    custom_role: str | None = None
    skills: str | None = None
    question_count: int | None = Field(default=None, ge=1, le=20)


class InterviewUpdate(BaseModel):
    candidate_id: int | None = None
    role_id: int | None = None
    custom_role: str | None = None
    skills: str | None = None
    status: str | None = None
    finished_at: datetime | None = None


class InterviewQuestionRead(BaseModel):
    id: int
    question_id: int | None = None
    question_text: str
    order_index: int

    class Config:
        from_attributes = True


class AnswerCreate(BaseModel):
    interview_question_id: int
    transcript: str


class AnswerRead(BaseModel):
    id: int
    interview_question_id: int
    transcript: str
    score: int | None = None
    feedback: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class InterviewRead(BaseModel):
    id: int
    candidate_id: int
    role_id: int | None = None
    custom_role: str | None = None
    skills: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    questions: list[InterviewQuestionRead] = []

    class Config:
        from_attributes = True


class InterviewDetail(BaseModel):
    id: int
    candidate: CandidateRead
    role: RoleRead | None = None
    custom_role: str | None = None
    skills: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    questions: list[InterviewQuestionRead] = []
    answers: list[AnswerRead] = []

    class Config:
        from_attributes = True


class TranscriptItem(BaseModel):
    interview_question_id: int
    question_text: str
    transcript: str
    score: int | None = None
    feedback: str | None = None
    created_at: datetime


class InterviewTranscript(BaseModel):
    id: int
    candidate: CandidateRead
    role: RoleRead | None = None
    custom_role: str | None = None
    skills: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    transcripts: list[TranscriptItem] = []

    class Config:
        from_attributes = True


class InterviewSessionState(BaseModel):
    interview_id: int
    status: str
    question: InterviewQuestionRead | None = None
    is_complete: bool


class InterviewSessionAnswer(BaseModel):
    answer: AnswerRead
    next_question: InterviewQuestionRead | None = None
    is_complete: bool
    status: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str | None = None


class UserRead(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True
