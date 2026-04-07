from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api.deps import get_db
from app.core.config import settings
from app.db.base import Base
from app.main import app


@pytest.fixture()
def client_and_session(monkeypatch, tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'test_public_flow.db'}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(settings, "anthropic_api_key", "")

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def seed_interview_data(session_local):
    db = session_local()
    try:
        role = models.JobRole(
            name="Backend Engineer",
            description="Build resilient AI backend services.",
            seniority="mid",
            department="Engineering",
            skills_required=["Python", "FastAPI", "LangGraph"],
        )
        db.add(role)
        db.flush()

        template = models.InterviewTemplate(
            job_role_id=role.id,
            name="Default Backend Loop",
            question_count=2,
            max_time_per_question_sec=120,
            system_prompt="Interview the candidate with concise technical questions.",
            evaluation_criteria="Depth, clarity, tradeoffs.",
        )
        db.add(template)
        db.flush()

        questions = [
            models.Question(
                job_role_id=role.id,
                text="How would you design a resilient FastAPI service?",
                category="system_design",
                difficulty="medium",
                is_active=True,
            ),
            models.Question(
                job_role_id=role.id,
                text="How would you monitor failures in production?",
                category="operations",
                difficulty="medium",
                is_active=True,
            ),
        ]
        db.add_all(questions)
        db.commit()
        return role.id
    finally:
        db.close()


def test_public_interview_flow_supports_language_and_completion(client_and_session):
    client, session_local = client_and_session
    job_role_id = seed_interview_data(session_local)

    application = client.post(
        "/public/applications",
        json={
            "job_role_id": job_role_id,
            "full_name": "Juan Solorzano",
            "email": "juan@example.com",
            "skills": ["Python", "FastAPI"],
            "interview_language": "es",
        },
    )
    assert application.status_code == 201, application.text
    application_payload = application.json()
    interview_id = application_payload["interview"]["id"]
    token = application_payload["interview_token"]

    started = client.post(f"/public/interviews/{interview_id}/start", params={"token": token, "language": "es"})
    assert started.status_code == 200, started.text
    started_payload = started.json()
    assert started_payload["interview_language"] == "es"
    assert started_payload["current_question"] is not None
    assert started_payload["current_question"]["text"] != "How would you design a resilient FastAPI service?"
    assert started_payload["current_question"]["text"].startswith("¿") or "Cuenta" in started_payload["current_question"]["text"] or "Cuénta" in started_payload["current_question"]["text"] or "Como" in started_payload["current_question"]["text"]

    clarification = client.post(
        f"/public/interviews/{interview_id}/turn",
        params={"token": token},
        json={
            "question_id": started_payload["current_question"]["id"],
            "intent": "clarify",
            "interview_language": "es",
        },
    )
    assert clarification.status_code == 200, clarification.text
    clarification_payload = clarification.json()
    assert clarification_payload["event_type"] == "clarification"
    assert clarification_payload["interview_language"] == "es"
    assert clarification_payload["current_question"]["id"] == started_payload["current_question"]["id"]

    first_answer = client.post(
        f"/public/interviews/{interview_id}/turn",
        params={"token": token},
        json={
            "question_id": started_payload["current_question"]["id"],
            "intent": "answer",
            "utterance": "Usaria retries, observabilidad y despliegues graduales para aumentar resiliencia.",
            "question_number": 1,
            "interview_language": "es",
        },
    )
    assert first_answer.status_code == 200, first_answer.text
    first_answer_payload = first_answer.json()
    assert first_answer_payload["candidate_answer_saved"] is True
    assert first_answer_payload["interview_language"] == "es"
    assert first_answer_payload["current_question"] is not None
    assert first_answer_payload["is_complete"] is False

    skip_second = client.post(
        f"/public/interviews/{interview_id}/turn",
        params={"token": token},
        json={
            "question_id": first_answer_payload["current_question"]["id"],
            "intent": "skip",
            "question_number": 2,
            "interview_language": "es",
        },
    )
    assert skip_second.status_code == 200, skip_second.text
    skip_payload = skip_second.json()
    assert skip_payload["candidate_answer_saved"] is True
    assert skip_payload["is_complete"] is True

    finished = client.post(f"/public/interviews/{interview_id}/finish", params={"token": token})
    assert finished.status_code == 200, finished.text
    finished_payload = finished.json()
    assert finished_payload["interview"]["status"] == "completed"
    assert finished_payload["evaluation"]["summary"]
    assert len(finished_payload["transcript"]["transcripts"]) == 2


def test_public_interview_defaults_to_english_when_language_is_missing(client_and_session):
    client, session_local = client_and_session
    job_role_id = seed_interview_data(session_local)

    application = client.post(
        "/public/applications",
        json={
            "job_role_id": job_role_id,
            "full_name": "Alex Candidate",
            "email": "alex@example.com",
        },
    )
    interview_id = application.json()["interview"]["id"]
    token = application.json()["interview_token"]

    started = client.post(f"/public/interviews/{interview_id}/start", params={"token": token})
    assert started.status_code == 200, started.text
    assert started.json()["interview_language"] == "en"
